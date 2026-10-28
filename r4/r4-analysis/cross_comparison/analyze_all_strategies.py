"""Compare R0-R4 on paired TEST queries and write inferential CSV outputs."""

import argparse
import csv
import hashlib
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.stats import friedmanchisquare


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]
DEFAULT_OUTPUT_DIR = HERE
STRATEGIES = ("R0", "R1", "R2", "R3", "R4")
DIFFICULTIES = (("All", None), ("Easy", "easy"), ("Medium", "medium"), ("Human", "human"))
METRICS = ("combined", "personal", "commonsense")
CS_CHECK_COUNT = 28
N_RESAMPLES = 100_000
RNG_SEED = 4213
ALPHA = 0.05


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"Refusing to write an empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def holm_adjust(p_values):
    """Holm step-down adjustment, preserving the supplied order."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted = [0.0] * len(p_values)
    running_max = 0.0
    count = len(p_values)
    for rank, index in enumerate(order):
        running_max = max(running_max, (count - rank) * p_values[index])
        adjusted[index] = min(1.0, running_max)
    return adjusted


def paired_swap_test(differences, rng):
    """Two-sided paired label-swap test of the mean difference."""
    differences = np.asarray(differences, dtype=float)
    n = len(differences)
    observed = float(np.mean(differences))
    total = 2 ** n
    tolerance = np.finfo(float).eps * max(1.0, abs(observed)) * 100
    if total <= N_RESAMPLES:
        bit_positions = np.arange(n, dtype=np.uint64)
        assignments = np.arange(total, dtype=np.uint64)[:, None]
        signs = np.where((assignments >> bit_positions) & 1, 1.0, -1.0)
        permuted = np.mean(signs * differences, axis=1)
        p_value = float(np.mean(np.abs(permuted) >= abs(observed) - tolerance))
        return p_value, "exhaustive", total

    extreme = 0
    remaining = N_RESAMPLES
    batch_size = 10_000
    while remaining:
        size = min(batch_size, remaining)
        signs = rng.integers(0, 2, size=(size, n), dtype=np.int8) * 2 - 1
        permuted = np.mean(signs * differences, axis=1)
        extreme += int(np.sum(np.abs(permuted) >= abs(observed) - tolerance))
        remaining -= size
    # The plus-one correction prevents a zero Monte Carlo p-value.
    p_value = (extreme + 1) / (N_RESAMPLES + 1)
    return float(p_value), "Monte Carlo", N_RESAMPLES


def load_and_validate(project_root):
    by_strategy = {}
    audit = []
    for strategy in STRATEGIES:
        path = project_root / "test_result_analysis" / strategy / "per_query.csv"
        if not path.is_file():
            raise FileNotFoundError(f"Missing saved per-query source for {strategy}: {path}")
        rows = read_csv(path)
        uid_map = {row["query_uid"]: row for row in rows}
        if len(uid_map) != len(rows):
            raise ValueError(f"Duplicate query IDs in {path}")
        if len(uid_map) != 30:
            raise ValueError(f"Expected 30 TEST queries for {strategy}; found {len(uid_map)}")
        for row in rows:
            if row["repair_strategy"].upper() != strategy:
                raise ValueError(f"Strategy label mismatch in {path} for {row['query_uid']}")
            if row["cs_evaluator_exception_final"].lower() == "true":
                raise ValueError(f"Commonsense evaluator exception for {strategy}/{row['query_uid']}")
            pc_total = int(row["pc_total"])
            cs_total = int(row["cs_total"])
            if pc_total <= 0 or cs_total != CS_CHECK_COUNT:
                raise ValueError(f"Unexpected scoring denominator for {strategy}/{row['query_uid']}")
            if not 0 <= int(row["pc_passed_final"]) <= pc_total:
                raise ValueError(f"Invalid PC count for {strategy}/{row['query_uid']}")
            if not 0 <= int(row["cs_passed_final"]) <= cs_total:
                raise ValueError(f"Invalid CS count for {strategy}/{row['query_uid']}")
        by_strategy[strategy] = uid_map
        group_counts = {name: sum(row["group"].lower() == key for row in rows) for name, key in DIFFICULTIES[1:]}
        audit.append({
            "strategy": strategy,
            "source_file": str(path),
            "sha256": sha256(path),
            "query_rows": len(rows),
            "unique_query_ids": len(uid_map),
            "easy_queries": group_counts["Easy"],
            "medium_queries": group_counts["Medium"],
            "human_queries": group_counts["Human"],
            "commonsense_checks_per_query": CS_CHECK_COUNT,
        })

    uid_sets = [set(by_strategy[s]) for s in STRATEGIES]
    if any(uids != uid_sets[0] for uids in uid_sets[1:]):
        raise ValueError("The five strategies do not contain identical TEST query IDs.")
    query_ids = sorted(uid_sets[0])
    for uid in query_ids:
        groups = {by_strategy[s][uid]["group"].lower() for s in STRATEGIES}
        pc_denominators = {int(by_strategy[s][uid]["pc_total"]) for s in STRATEGIES}
        if len(groups) != 1 or len(pc_denominators) != 1:
            raise ValueError(f"Difficulty or PC scoring denominator differs across strategies for {uid}.")
    return by_strategy, query_ids, audit


def build_scores(by_strategy, query_ids):
    scores = {metric: {strategy: {} for strategy in STRATEGIES} for metric in METRICS}
    rows = []
    for uid in query_ids:
        first = by_strategy["R0"][uid]
        row = {"query_uid": uid, "difficulty": first["group"].capitalize()}
        for strategy in STRATEGIES:
            source = by_strategy[strategy][uid]
            pc_total = int(source["pc_total"])
            cs_total = int(source["cs_total"])
            pc_passed = int(source["pc_passed_final"])
            cs_passed = int(source["cs_passed_final"])
            personal = 100 * pc_passed / pc_total
            commonsense = 100 * cs_passed / cs_total
            combined = 100 * (pc_passed + cs_passed) / (pc_total + cs_total)
            scores["personal"][strategy][uid] = personal
            scores["commonsense"][strategy][uid] = commonsense
            scores["combined"][strategy][uid] = combined
            row.update({
                f"{strategy}_personal_satisfaction_pct": personal,
                f"{strategy}_commonsense_satisfaction_pct": commonsense,
                f"{strategy}_combined_satisfaction_pct": combined,
            })
        rows.append(row)
    return scores, rows


def metric_label(metric):
    return {
        "combined": "Combined satisfaction (personal constraints + commonsense checks)",
        "personal": "Personal-constraint satisfaction",
        "commonsense": "Commonsense-constraint satisfaction",
    }[metric]


def get_values(scores, metric, cohort_key):
    values = {}
    for strategy in STRATEGIES:
        selected = []
        for uid, score in scores[metric][strategy].items():
            if cohort_key is None or scores["_difficulty"][uid] == cohort_key:
                selected.append((uid, score))
        values[strategy] = dict(selected)
    return values


def build_tests(scores, paired_rows):
    scores["_difficulty"] = {row["query_uid"]: row["difficulty"].lower() for row in paired_rows}
    omnibus_rows = []
    comparison_rows = []
    permutation_rng = np.random.default_rng(RNG_SEED)

    for cohort_label, cohort_key in DIFFICULTIES:
        for metric in METRICS:
            vals = get_values(scores, metric, cohort_key)
            query_ids = sorted(vals[STRATEGIES[0]])
            samples = [np.asarray([vals[strategy][uid] for uid in query_ids], dtype=float) for strategy in STRATEGIES]
            if len(query_ids) < 2:
                raise ValueError(f"Not enough paired queries for {cohort_label}/{metric}")
            friedman = friedmanchisquare(*samples)
            omnibus_rows.append({
                "cohort": cohort_label,
                "outcome_key": metric,
                "outcome": metric_label(metric),
                "n_paired_queries": len(query_ids),
                "strategies_compared": ";".join(STRATEGIES),
                "test": "Friedman repeated-measures test",
                "question_tested": f"Do any of the five strategies differ in {metric_label(metric).lower()} for {cohort_label} queries?",
                "chi_square_statistic": float(friedman.statistic),
                "degrees_freedom": len(STRATEGIES) - 1,
                "p_value": float(friedman.pvalue),
            })

            for left, right in combinations(STRATEGIES, 2):
                x = np.asarray([vals[left][uid] for uid in query_ids], dtype=float)
                y = np.asarray([vals[right][uid] for uid in query_ids], dtype=float)

                difference = y - x
                p_value, permutation_method, permutation_count = paired_swap_test(difference, permutation_rng)
                wins = int(np.sum(difference > 0))
                ties = int(np.sum(difference == 0))
                losses = int(np.sum(difference < 0))
                comparison_rows.append({
                    "cohort": cohort_label,
                    "outcome_key": metric,
                    "outcome": metric_label(metric),
                    "left_strategy": left,
                    "right_strategy": right,
                    "delta_convention": f"{right} minus {left}",
                    "n_paired_queries": len(query_ids),
                    "right_better_queries": wins,
                    "tied_queries": ties,
                    "right_worse_queries": losses,
                    "left_mean_satisfaction_pct": float(np.mean(x)),
                    "right_mean_satisfaction_pct": float(np.mean(y)),
                    "mean_difference_percentage_points": float(np.mean(difference)),
                    "test": "paired label-swap permutation test on mean difference",
                    "permutation_method": permutation_method,
                    "permutations": permutation_count,
                    "random_seed": "" if permutation_method == "exhaustive" else RNG_SEED,
                    "p_value_two_sided": p_value,
                    "omnibus_friedman_p_value": float(friedman.pvalue),
                })

    omnibus_adjusted = holm_adjust([row["p_value"] for row in omnibus_rows])
    for row, p_adjusted in zip(omnibus_rows, omnibus_adjusted):
        row["p_value_holm_adjusted_across_12_omnibus"] = p_adjusted
        row["alpha"] = ALPHA
        row["omnibus_significant_after_holm"] = p_adjusted < ALPHA
        row["interpretation_scope"] = "Exploratory subgroup" if row["cohort"] != "All" else "Overall"

    pairwise_adjusted = holm_adjust([row["p_value_two_sided"] for row in comparison_rows])
    omnibus_by_group = {(row["cohort"], row["outcome_key"]): row for row in omnibus_rows}
    for row, p_adjusted in zip(comparison_rows, pairwise_adjusted):
        omnibus = omnibus_by_group[(row["cohort"], row["outcome_key"])]
        row["p_value_holm_adjusted_across_120_pairwise"] = p_adjusted
        row["alpha"] = ALPHA
        row["significant_after_holm"] = p_adjusted < ALPHA
        row["omnibus_significant_after_holm"] = omnibus["omnibus_significant_after_holm"]
        row["posthoc_gate_passed"] = omnibus["omnibus_significant_after_holm"]
        row["interpretation_scope"] = "Exploratory subgroup" if row["cohort"] != "All" else "Overall"
    return omnibus_rows, comparison_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    by_strategy, query_ids, audit = load_and_validate(args.project_root.resolve())
    scores, paired_rows = build_scores(by_strategy, query_ids)
    omnibus, comparisons = build_tests(scores, paired_rows)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "source_audit.csv", audit)
    write_csv(output / "paired_scores.csv", paired_rows)
    write_csv(output / "omnibus_tests.csv", omnibus)
    write_csv(output / "pairwise_tests.csv", comparisons)
    print(f"Validated {len(query_ids)} shared TEST queries across {len(STRATEGIES)} strategies.")
    print(f"Wrote {len(omnibus)} omnibus tests and {len(comparisons)} pairwise tests to {output}")


if __name__ == "__main__":
    main()
