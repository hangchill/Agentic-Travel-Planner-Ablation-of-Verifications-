"""Run paired significance analyses for R0 versus R4 TEST satisfaction."""

import argparse
import csv
from pathlib import Path

from scipy.stats import binomtest, t as student_t, ttest_rel


HERE = Path(__file__).resolve().parent
ANALYSIS_DIR = HERE.parent
DEFAULT_OUTPUT = HERE / "significance_tests.csv"
DEFAULT_DIFFICULTY_OUTPUT = HERE / "difficulty_significance_tests.csv"
CS_CHECK_COUNT = 28
ALPHA = 0.05
DIFFICULTY_GROUPS = (("easy", "Easy"), ("medium", "Medium"), ("human", "Human"))


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return {row["query_uid"]: row for row in rows}


def mean(values):
    return sum(values) / len(values)


def paired_t_summary(r0_values, r4_values):
    diffs = [b - a for a, b in zip(r0_values, r4_values)]
    result = ttest_rel(r4_values, r0_values, alternative="two-sided")
    df = len(diffs) - 1
    se = (sum((d - mean(diffs)) ** 2 for d in diffs) / df / len(diffs)) ** 0.5
    critical = student_t.ppf(1 - ALPHA / 2, df)
    return float(result.statistic), float(result.pvalue), df, mean(diffs), (
        mean(diffs) - critical * se,
        mean(diffs) + critical * se,
    )


def exact_sign_summary(r0_values, r4_values):
    diffs = [b - a for a, b in zip(r0_values, r4_values)]
    wins = sum(d > 0 for d in diffs)
    losses = sum(d < 0 for d in diffs)
    ties = sum(d == 0 for d in diffs)
    n_non_tied = wins + losses
    p_value = float(binomtest(wins, n_non_tied, 0.5, alternative="two-sided").pvalue) if n_non_tied else 1.0
    return wins, ties, losses, n_non_tied, p_value, mean(diffs)


def holm_adjust(p_values):
    """Holm step-down adjusted p-values, returned in original order."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted = [0.0] * len(p_values)
    running_max = 0.0
    m = len(p_values)
    for rank, index in enumerate(order):
        running_max = max(running_max, (m - rank) * p_values[index])
        adjusted[index] = min(1.0, running_max)
    return adjusted


def build_difficulty_rows(paired_scores):
    """Run the same three paired tests separately within each difficulty group."""
    rows = []
    raw_p = []
    for difficulty_key, difficulty_label in DIFFICULTY_GROUPS:
        group = [row for row in paired_scores if row["difficulty"].lower() == difficulty_key]
        if len(group) != 10:
            raise ValueError(f"Expected 10 {difficulty_label} query pairs, found {len(group)}.")
        metrics = (
            ("combined", "Primary", "Combined satisfaction", "R0_combined_satisfaction_pct", "R4_combined_satisfaction_pct", "paired t-test"),
            ("personal", "Secondary", "Personal-constraint satisfaction", "R0_personal_satisfaction_pct", "R4_personal_satisfaction_pct", "exact paired sign test"),
            ("commonsense", "Secondary", "Commonsense-constraint satisfaction", "R0_commonsense_satisfaction_pct", "R4_commonsense_satisfaction_pct", "exact paired sign test"),
        )
        for key, role, outcome, before_col, after_col, test_name in metrics:
            before = [float(row[before_col]) for row in group]
            after = [float(row[after_col]) for row in group]
            wins, ties, losses, n_non_tied, sign_p, mean_diff = exact_sign_summary(before, after)
            if key == "combined":
                statistic, p_value, df, mean_diff, ci = paired_t_summary(before, after)
                statistic_name = "t_statistic"
                question = f"Is mean per-request combined satisfaction different between R4 and R0 for {difficulty_label} requests?"
                df_out = df
                ci_low, ci_high = ci
            else:
                statistic, p_value = wins, sign_p
                statistic_name = "R4_improvements_among_non_ties"
                question = f"Among non-tied {difficulty_label} requests, are R4 improvements and declines equally likely?"
                df_out = ""
                ci_low = ci_high = ""
            raw_p.append(p_value)
            rows.append({
                "difficulty": difficulty_label,
                "outcome_key": key,
                "role": role,
                "outcome": outcome,
                "test": test_name,
                "question_tested": question,
                "alternative": "two-sided",
                "n_paired_requests": len(group),
                "n_non_tied_requests": n_non_tied,
                "R4_better_requests": wins,
                "tied_requests": ties,
                "R4_worse_requests": losses,
                "R0_mean_satisfaction_pct": mean(before),
                "R4_mean_satisfaction_pct": mean(after),
                "mean_R4_minus_R0_percentage_points": mean_diff,
                "test_statistic_name": statistic_name,
                "test_statistic": statistic,
                "degrees_freedom": df_out,
                "mean_difference_95CI_low_pp": ci_low,
                "mean_difference_95CI_high_pp": ci_high,
                "p_value_two_sided": p_value,
            })
    adjusted = holm_adjust(raw_p)
    for row, p_adj in zip(rows, adjusted):
        row["p_value_holm_adjusted_across_9_tests"] = p_adj
        row["alpha"] = ALPHA
        row["significant_after_holm_at_alpha"] = p_adj < ALPHA
    return rows


def build_rows(r0, r4):
    if set(r0) != set(r4):
        raise ValueError("R0 and R4 per-query files must contain the same query IDs.")
    if len(r0) != 30:
        raise ValueError(f"Expected the 30 TEST query pairs, found {len(r0)}.")

    query_ids = sorted(r0)
    r0_pc, r4_pc, r0_cs, r4_cs, r0_all, r4_all = [], [], [], [], [], []
    paired_scores = []
    for uid in query_ids:
        a, b = r0[uid], r4[uid]
        if int(a["pc_total"]) != int(b["pc_total"]):
            raise ValueError(f"PC denominators differ for {uid}.")
        if a["cs_evaluator_exception"].lower() == "true" or b["cs_evaluator_exception"].lower() == "true":
            raise ValueError(f"Commonsense scoring failed for {uid}.")
        for row, label in ((a, "R0"), (b, "R4")):
            total = int(row["pc_total"])
            if total <= 0 or not 0 <= int(row["pc_final_passed"]) <= total:
                raise ValueError(f"Invalid PC score for {label} {uid}.")
            if not 0 <= int(row["cs_final_failed"]) <= CS_CHECK_COUNT:
                raise ValueError(f"Invalid CS score for {label} {uid}.")

        pc_total = int(a["pc_total"])
        pc_r0 = 100 * int(a["pc_final_passed"]) / pc_total
        pc_r4 = 100 * int(b["pc_final_passed"]) / pc_total
        cs_r0 = 100 * (CS_CHECK_COUNT - int(a["cs_final_failed"])) / CS_CHECK_COUNT
        cs_r4 = 100 * (CS_CHECK_COUNT - int(b["cs_final_failed"])) / CS_CHECK_COUNT
        all_r0 = 100 * (int(a["pc_final_passed"]) + CS_CHECK_COUNT - int(a["cs_final_failed"])) / (pc_total + CS_CHECK_COUNT)
        all_r4 = 100 * (int(b["pc_final_passed"]) + CS_CHECK_COUNT - int(b["cs_final_failed"])) / (pc_total + CS_CHECK_COUNT)
        r0_pc.append(pc_r0)
        r4_pc.append(pc_r4)
        r0_cs.append(cs_r0)
        r4_cs.append(cs_r4)
        r0_all.append(all_r0)
        r4_all.append(all_r4)
        paired_scores.append({
            "query_uid": uid,
            "difficulty": a["difficulty"],
            "personal_constraints_total": pc_total,
            "commonsense_checks_total": CS_CHECK_COUNT,
            "R0_personal_satisfaction_pct": pc_r0,
            "R4_personal_satisfaction_pct": pc_r4,
            "personal_R4_minus_R0_pp": pc_r4 - pc_r0,
            "R0_commonsense_satisfaction_pct": cs_r0,
            "R4_commonsense_satisfaction_pct": cs_r4,
            "commonsense_R4_minus_R0_pp": cs_r4 - cs_r0,
            "R0_combined_satisfaction_pct": all_r0,
            "R4_combined_satisfaction_pct": all_r4,
            "combined_R4_minus_R0_pp": all_r4 - all_r0,
        })

    specs = [
        ("combined", "Primary", "Combined satisfaction: personal constraints and 28 commonsense checks", r0_all, r4_all, "paired t-test"),
        ("personal", "Secondary", "Personal-constraint satisfaction", r0_pc, r4_pc, "exact paired sign test"),
        ("commonsense", "Secondary", "Commonsense-constraint satisfaction across 28 checks", r0_cs, r4_cs, "exact paired sign test"),
    ]
    rows = []
    raw_p = []
    for key, role, outcome, before, after, test_name in specs:
        n = len(before)
        wins, ties, losses, n_non_tied, sign_p, mean_diff = exact_sign_summary(before, after)
        if key == "combined":
            statistic, p_value, df, mean_diff, ci = paired_t_summary(before, after)
            statistic_label = "t_statistic"
            df_out = df
            ci_low, ci_high = ci
            question = "Is mean per-request combined satisfaction different between R4 and R0?"
        else:
            statistic, p_value = wins, sign_p
            statistic_label = "R4_improvements_among_non_ties"
            df_out = ""
            ci_low = ci_high = ""
            question = "Among non-tied requests, are R4 improvements and declines equally likely?"
        raw_p.append(p_value)
        rows.append({
            "outcome_key": key,
            "role": role,
            "outcome": outcome,
            "test": test_name,
            "question_tested": question,
            "alternative": "two-sided",
            "n_paired_requests": n,
            "n_non_tied_requests": n_non_tied,
            "R4_better_requests": wins,
            "tied_requests": ties,
            "R4_worse_requests": losses,
            "R0_mean_satisfaction_pct": mean(before),
            "R4_mean_satisfaction_pct": mean(after),
            "mean_R4_minus_R0_percentage_points": mean_diff,
            "test_statistic_name": statistic_label,
            "test_statistic": statistic,
            "degrees_freedom": df_out,
            "mean_difference_95CI_low_pp": ci_low,
            "mean_difference_95CI_high_pp": ci_high,
            "p_value_two_sided": p_value,
        })

    adjusted = holm_adjust(raw_p)
    for row, p_adj in zip(rows, adjusted):
        row["p_value_holm_adjusted"] = p_adj
        row["alpha"] = ALPHA
        row["significant_after_holm_at_alpha"] = p_adj < ALPHA
    return rows, paired_scores


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    r0 = read_rows(args.analysis_dir / "r0_vs_r4" / "r0_details" / "per_query.csv")
    r4 = read_rows(args.analysis_dir / "r4" / "per_query.csv")
    rows, paired_scores = build_rows(r0, r4)
    difficulty_rows = build_difficulty_rows(paired_scores)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.output, rows)
    pair_output = args.output.with_name("paired_scores.csv")
    write_csv(pair_output, paired_scores)
    difficulty_output = args.output.with_name(DEFAULT_DIFFICULTY_OUTPUT.name)
    write_csv(difficulty_output, difficulty_rows)
    print(f"Wrote {len(rows)} paired test results to {args.output}")
    print(f"Wrote {len(paired_scores)} paired query scores to {pair_output}")
    print(f"Wrote {len(difficulty_rows)} difficulty-stratified test results to {difficulty_output}")


if __name__ == "__main__":
    main()
