"""Plot benchmark constraint counts and gains through six R0-R4 repair attempts.

Reads saved TEST checkpoints and evaluates accepted translated plans locally.
No model calls are made and experiment artifacts are never modified.
"""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from chinatravel.evaluation.repair_comparison import pair_path
from scripts.result_analysis import build_test_result_tables as evaluator

STRATEGIES = ("R0", "R1", "R2", "R3", "R4")
STEPS = range(7)
COLORS = {"personal": "#245C91", "commonsense": "#CE731F"}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_strategy(strategy, project_root):
    root = project_root / "experiments" / f"subset_test-{strategy.lower()}"
    manifest = load_json(root / "run_manifest.json")
    ids = manifest["query_uids"]
    if len(ids) != 30 or len(set(ids)) != 30:
        raise ValueError(f"{strategy}: expected 30 unique TEST query IDs")
    bench = evaluator.benchmark_dir(root, strategy)
    references = load_json(bench / "evaluation_population.json")["queries"]
    table_path = project_root / "test_result_analysis" / strategy / "per_query.csv"
    with table_path.open(encoding="utf-8-sig", newline="") as stream:
        table_rows = list(csv.DictReader(stream))
    reported = {row["query_uid"]: row for row in table_rows}
    if set(ids) != set(references) or set(ids) != set(reported):
        raise ValueError(f"{strategy}: source populations disagree")
    with (bench / "commonsense.csv").open(encoding="utf-8-sig", newline="") as stream:
        checks = [name for name in csv.DictReader(stream).fieldnames
                  if name not in ("data_id", evaluator.CS_EXCEPTION_COLUMN)]
    if len(checks) != 28:
        raise ValueError(f"{strategy}: expected 28 standard CS categories")

    states = {step: {} for step in STEPS}
    metadata = {}
    for uid in ids:
        checkpoint_path = pair_path(root, uid, strategy)
        checkpoint = load_json(checkpoint_path)
        if checkpoint.get("execution_status") != "completed":
            raise ValueError(f"{strategy}/{uid}: incomplete execution")
        history = checkpoint.get("repair_history") or []
        entries = {entry["step"]: entry for entry in history if entry["step"] > 0}
        if len(entries) != len(history) - sum(entry["step"] == 0 for entry in history):
            raise ValueError(f"{strategy}/{uid}: duplicate attempt numbers")
        if sorted(entries) != list(range(1, len(entries) + 1)) or len(entries) > 6:
            raise ValueError(f"{strategy}/{uid}: attempts are not contiguous within 1-6")
        if len(entries) != len(checkpoint.get("repair_attempts") or []):
            raise ValueError(f"{strategy}/{uid}: history/attempt count mismatch")
        initial_report = checkpoint.get("initial_verification") or next(
            entry["verification"] for entry in history if entry["step"] == 0)
        current = initial_report.get("translated_plan")
        if not isinstance(current, dict):
            raise ValueError(f"{strategy}/{uid}: missing initial translated plan")
        states[0][uid] = current
        for step in range(1, 7):
            entry = entries.get(step)
            if entry is not None and entry.get("accepted") is True:
                current = (entry.get("verification") or {}).get("translated_plan")
                if not isinstance(current, dict):
                    raise ValueError(f"{strategy}/{uid}/{step}: missing accepted translated plan")
            states[step][uid] = current
        saved_final = load_json(bench / "plans" / f"{uid}.json")
        if digest(current) != digest(saved_final):
            raise ValueError(f"{strategy}/{uid}: retained attempt endpoint differs from scored final export")
        metadata[uid] = {
            "difficulty": reported[uid]["group"],
            "checkpoint": str(checkpoint_path.relative_to(project_root)),
            "entries": {step: bool(entry.get("accepted")) for step, entry in entries.items()},
        }
    return manifest, references, reported, checks, states, metadata, table_path


def score_strategy(strategy, loaded, cache, evaluator_fingerprint):
    manifest, references, reported, checks, states, metadata, _ = loaded
    language = manifest.get("language", "en")
    rows = []
    baseline = {}
    for step in STEPS:
        keys = {uid: digest([evaluator_fingerprint, uid, language, references[uid], plan])
                for uid, plan in states[step].items()}
        missing = [uid for uid, key in keys.items() if key not in cache]
        if missing:
            results = evaluator.score_plans(missing, references,
                                           {uid: states[step][uid] for uid in missing}, language)
            for uid in missing:
                score = results[uid]
                if not set(score["cs_failed"]).issubset(checks):
                    raise ValueError(f"{strategy}/{uid}/{step}: unknown CS category")
                cache[keys[uid]] = {
                    "personal_satisfied": sum(score["pc"]),
                    "personal_total": len(score["pc"]),
                    "commonsense_satisfied": 0 if score["cs_exception"] else 28 - len(score["cs_failed"]),
                    "commonsense_total": 28,
                    "cs_evaluator_exception": bool(score["cs_exception"]),
                }
        for uid in sorted(states[step]):
            score = cache[keys[uid]]
            if step == 0:
                baseline[uid] = score
            info = metadata[uid]
            actual = step in info["entries"]
            row = dict(strategy=strategy, query_uid=uid, difficulty=info["difficulty"],
                       attempt=step, actual_attempt=actual,
                       accepted_this_attempt=info["entries"].get(step, ""),
                       carried_forward_after_stopping=step > 0 and not actual,
                       **score,
                       personal_gain_from_initial=score["personal_satisfied"] - baseline[uid]["personal_satisfied"],
                       commonsense_gain_from_initial=score["commonsense_satisfied"] - baseline[uid]["commonsense_satisfied"],
                       source_checkpoint=info["checkpoint"])
            rows.append(row)
            if step in (0, 6):
                suffix = "initial" if step == 0 else "final"
                for field, column in (("personal_satisfied", f"pc_passed_{suffix}"),
                                      ("commonsense_satisfied", f"cs_passed_{suffix}")):
                    if score[field] != int(reported[uid][column]):
                        raise ValueError(f"{strategy}/{uid}: {suffix} {field} disagrees with saved results")
        print(f"{strategy}: scored attempt {step}/6 ({len(missing)} uncached plans)", flush=True)
    return rows


def aggregate(rows):
    out = []
    for strategy in STRATEGIES:
        for step in STEPS:
            selected = [row for row in rows if row["strategy"] == strategy and row["attempt"] == step]
            if len(selected) != 30:
                raise ValueError(f"{strategy}/{step}: changing cohort size")
            out.append(dict(
                strategy=strategy, attempt=step, cohort_queries=len(selected),
                actual_attempt_queries=sum(row["actual_attempt"] for row in selected),
                carried_forward_queries=sum(row["carried_forward_after_stopping"] for row in selected),
                mean_personal_satisfied=statistics.mean(row["personal_satisfied"] for row in selected),
                mean_commonsense_satisfied=statistics.mean(row["commonsense_satisfied"] for row in selected),
                mean_personal_gain_from_initial=statistics.mean(row["personal_gain_from_initial"] for row in selected),
                mean_commonsense_gain_from_initial=statistics.mean(row["commonsense_gain_from_initial"] for row in selected),
                total_personal_satisfied=sum(row["personal_satisfied"] for row in selected),
                total_commonsense_satisfied=sum(row["commonsense_satisfied"] for row in selected),
                cs_evaluator_exceptions=sum(row["cs_evaluator_exception"] for row in selected),
            ))
    return out


def plot_graphs(summary, output):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12,
                         "axes.titlesize": 18, "axes.labelsize": 12,
                         "svg.fonttype": "none", "savefig.facecolor": "white"})
    gain_values = [row[field] for row in summary for field in
                   ("mean_personal_gain_from_initial", "mean_commonsense_gain_from_initial")]
    gain_min = min(-0.5, math.floor(min(gain_values) * 2) / 2 - 0.3)
    gain_max = max(0.5, math.ceil(max(gain_values) * 2) / 2 + 0.3)
    for strategy in STRATEGIES:
        selected = [row for row in summary if row["strategy"] == strategy and row["attempt"] > 0]
        for kind in ("satisfied_counts", "net_change"):
            fig, ax = plt.subplots(figsize=(9.6, 5.7))
            fig.subplots_adjust(left=0.11, right=0.95, bottom=0.20, top=0.77)
            count = kind == "satisfied_counts"
            fields = ("mean_personal_satisfied", "mean_commonsense_satisfied") if count else (
                "mean_personal_gain_from_initial", "mean_commonsense_gain_from_initial")
            for field, name, color, marker, linestyle in zip(fields,
                    ("Personal constraints", "Commonsense constraints"),
                    (COLORS["personal"], COLORS["commonsense"]), ("o", "s"), ("-", "--")):
                values = [row[field] for row in selected]
                ax.plot(range(1, 7), values, label=name, color=color, marker=marker,
                        markersize=7, linewidth=2.4, linestyle=linestyle)
                ax.annotate(f"{values[-1]:+.2f}" if not count else f"{values[-1]:.2f}",
                            (6, values[-1]), xytext=(9, 0), textcoords="offset points",
                            color=color, va="center", fontsize=11, fontweight="bold")
            ax.set_xlim(0.85, 6.5)
            ax.set_xticks(range(1, 7))
            ax.set_xlabel("Repair attempt")
            if count:
                ax.set_ylim(0, 28.5)
                ax.set_ylabel("Mean number satisfied per query")
                title = f"{strategy}: constraints satisfied"
                note = "Personal constraints vary by request; commonsense has 28 benchmark checks."
            else:
                ax.set_ylim(gain_min, gain_max)
                ax.axhline(0, color="#66717E", linewidth=1.0)
                ax.set_ylabel("Mean change from initial plan\n(constraints per query)")
                ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
                title = f"{strategy}: net change in constraints satisfied"
                note = "Positive = more constraints satisfied than before attempt 1; negative = fewer."
            fig.text(0.11, 0.93, title, ha="left", fontsize=18, fontweight="bold", color="#243548")
            ax.legend(loc="lower left", bbox_to_anchor=(-0.01, 1.02), frameon=False,
                      ncol=2, fontsize=11, borderaxespad=0)
            ax.grid(axis="y", color="#DCE2E8", linewidth=0.7)
            ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)
            ax.spines[["left", "bottom"]].set_color("#9CA7B3")
            fig.text(0.11, 0.085, "30 TEST queries; last accepted plan carried forward after a query stops.",
                     fontsize=9.2, color="#526171")
            fig.text(0.11, 0.046, note, fontsize=9.2, color="#526171")
            for extension in ("png", "svg"):
                fig.savefig(output / f"{strategy.lower()}_{kind}.{extension}", dpi=240)
            plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--refresh-scores", action="store_true")
    args = parser.parse_args()
    project_root, output = args.project_root.resolve(), args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evaluator_files = [project_root / "scripts/result_analysis/build_test_result_tables.py",
                       *sorted((project_root / "chinatravel/evaluation").glob("*.py")),
                       *sorted((project_root / "chinatravel/symbol_verification").glob("*.py"))]
    fingerprint = digest([(str(path.relative_to(project_root)), file_hash(path)) for path in evaluator_files])
    cache_path = output / "benchmark_score_cache.json"
    cache = load_json(cache_path) if cache_path.exists() and not args.refresh_scores else {}
    all_rows, source_rows = [], []
    canonical_ids = None
    for strategy in STRATEGIES:
        loaded = load_strategy(strategy, project_root)
        manifest, references = loaded[:2]
        ids = set(manifest["query_uids"])
        if canonical_ids is None:
            canonical_ids = ids
        elif ids != canonical_ids:
            raise ValueError("The five strategies do not share the same TEST queries")
        print(f"{strategy}: validated 30 queries; scoring saved accepted states", flush=True)
        all_rows.extend(score_strategy(strategy, loaded, cache, fingerprint))
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        source_rows.append(dict(strategy=strategy, per_query_results=str(loaded[-1]),
                                per_query_sha256=file_hash(loaded[-1]),
                                queries=len(ids), evaluator_fingerprint=fingerprint))
    summary = aggregate(all_rows)
    write_csv(output / "per_query_attempt_scores.csv", all_rows)
    write_csv(output / "attempt_summary.csv", summary)
    write_csv(output / "source_manifest.csv", source_rows)
    plot_graphs(summary, output)
    print(f"Saved 10 graphs (PNG + SVG) and supporting CSVs in {output}", flush=True)


if __name__ == "__main__":
    main()
