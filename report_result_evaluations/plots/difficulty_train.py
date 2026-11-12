"""Figure fig5: plans passing all PC and repair cost for R0-R3 on Easy / Medium / Human (subset_train, 20 per group).

Copied from the "plot" step of train_result_analysis/difficulty_comparisons/difficulty_comparison_r0-3.py;
only the paths changed. Same layout as fig4 (the test split).

Data (read only):
  R0, R2, R3  train_result_analysis/merged/table1_pc.csv, table3_repair_process.csv, table4_eval_exp.csv
  R1          experiments/subset_train-r1: attempts.jsonl (tokens, time) and benchmark_eval/R1-*/logical_py.csv
              (plans passing all PC)
The R1 train run kept only attempts.jsonl. Its queries/ and benchmark_eval/ folders were rebuilt and scored once,
offline, by the "score" step of the original script (its docstring gives the method and its check on R1 test).
That step writes into experiments/subset_train-r1, so it is not copied here; this script only reads its output.
Known gap: h20241029143754236194 (Human) has no attempts and no saved initial plan, so it is scored as an empty
plan (fail), and R1 Human may be 1 plan (5 pp) too low.

Writes report_result_evaluations/figures/fig5_train_difficulty.png.

Usage: python report_result_evaluations/plots/difficulty_train.py   (needs matplotlib and numpy)
"""
import collections
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent  ## report_result_evaluations/plots
REPO = HERE.parents[1]
OUT = HERE.parent / "figures"
MERGED = REPO / "train_result_analysis" / "merged"  ## read only
R1_RUN = REPO / "experiments" / "subset_train-r1"  ## read only
GROUPS = ["Easy", "Medium", "Human"]
METHODS = ["R0", "R1", "R2", "R3"]
MACRO = "Logical macro (%)"
TOKENS = "[per query] Avg tokens spent per query (queries with complete token data)"
TIME = "[per query] Avg repair time per query (s)"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))



def group_metrics(attempts_run, scored_run):
    """Per group: plans passing all PC (count, %), avg tokens and avg repair time per query."""
    origin = load_json(REPO / "chinatravel/evaluation/splits/subset_origin.json")["origin"]
    uids = load_json(Path(attempts_run) / "run_manifest.json")["query_uids"]
    tokens, time = collections.Counter(), collections.Counter()
    for line in open(Path(attempts_run) / "attempts.jsonl", encoding="utf-8"):
        row = json.loads(line)
        tokens[row["query_uid"]] += row["total_tokens_delta"] or 0
        time[row["query_uid"]] += row["repair_time_seconds"] or 0
    found = list((Path(scored_run) / "benchmark_eval").glob("*/logical_py.csv"))
    if len(found) != 1:
        sys.exit(f"{scored_run}: expected one benchmark_eval/*/logical_py.csv, found {len(found)}. "
                 "Run the score step of train_result_analysis/difficulty_comparisons/difficulty_comparison_r0-3.py first.")
    passed = {}
    with open(found[0], encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            cells = [v for k, v in row.items() if k.startswith("logic_py_") and v not in ("", None)]
            passed[row["data_id"]] = all(float(v) == 1 for v in cells)
    result = {}
    for group in GROUPS + ["All"]:
        members = [u for u in uids if group == "All" or origin[u] == group.lower()]
        result[group] = dict(n=len(members), all_pc=sum(passed[u] for u in members),
                             pct=round(100 * sum(passed[u] for u in members) / len(members), 2),
                             tokens=round(sum(tokens[u] for u in members) / len(members)),
                             time=round(sum(time[u] for u in members) / len(members), 1))
    return result


def load_table(folder, name):
    with open(Path(folder) / name, encoding="utf-8") as stream:
        return {row["metric"]: row for row in csv.DictReader(stream)}


def table_value(table, metric, group, method):
    if metric not in table:  ## a unique prefix is accepted (the table 4 names are long)
        matches = [m for m in table if m.startswith(metric)]
        assert len(matches) == 1, (metric, matches)
        metric = matches[0]
    return float(table[metric][f"{group} {method}"])



def plot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    ## Same colours as the test plots (dataviz palette validator: all checks pass).
    color = {"R0": "#2a78d6", "R1": "#1baf7a", "R2": "#eda100", "R3": "#e87ba4"}
    surface, ink, ink2, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9"
    plt.rcParams.update({
        "figure.facecolor": surface, "axes.facecolor": surface, "savefig.facecolor": surface,
        "axes.edgecolor": grid, "axes.labelcolor": ink2, "xtick.color": ink2, "ytick.color": ink2,
        "text.color": ink, "axes.grid": True, "grid.color": grid, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
        "axes.titleweight": "bold", "axes.titlesize": 11, "axes.axisbelow": True,
    })
    r1 = group_metrics(R1_RUN, R1_RUN)
    t1, t3, t4 = (load_table(MERGED, n) for n in ("table1_pc.csv", "table3_repair_process.csv", "table4_eval_exp.csv"))
    n = int(table_value(t1, "Queries (n)", "Easy", "R0"))

    def value(table, metric, group, method):  ## R1 from its run folder, the others from the merged tables
        if method == "R1":
            return r1[group][{MACRO: "pct", TOKENS: "tokens", TIME: "time"}[metric]]
        return table_value(table, metric, group, method)

    for g in GROUPS:  ## the bars must equal table 1's count of plans with 0 failed PC, as a %
        for m in METHODS:
            if m != "R1":
                assert abs(value(t4, MACRO, g, m) - 100 * table_value(t1, "Final plans with 0 failed PC", g, m) / n) < 0.01

    width = 0.8 / len(METHODS)
    fig, axes = plt.subplots(3, 1, figsize=(10, 9.4), sharex=True, height_ratios=(1.3, 1, 1))
    for i, m in enumerate(METHODS):
        x = np.arange(3) + (i - (len(METHODS) - 1) / 2) * width
        macro = [value(t4, MACRO, g, m) for g in GROUPS]
        bars = axes[0].bar(x, macro, width=width - 0.02, color=color[m])
        for bar, v in zip(bars, macro):
            axes[0].annotate(f"{v:.0f}", (bar.get_x() + bar.get_width() / 2, v), xytext=(0, 2),
                             textcoords="offset points", ha="center", fontsize=10, color=ink2)
        for ax, metric, scale in ((axes[1], TOKENS, 1000), (axes[2], TIME, 1)):
            values = [value(t3, metric, g, m) / scale for g in GROUPS]
            ax.vlines(x, 0, values, color=grid, lw=1.2, zorder=1)  ## thin stem, ties the point to the bar
            ax.scatter(x, values, s=90, color=color[m], edgecolor=surface, linewidth=1.5, zorder=3)
    axes[0].set_ylim(0, 100)
    axes[0].set_ylabel("Final plans passing\nall PC (%)")
    axes[1].set_ylim(0, 260)
    axes[1].set_ylabel("Avg tokens per query\n(thousands)")
    axes[2].set_ylim(0, 260)
    axes[2].set_ylabel("Avg repair time\nper query (s)")
    for ax in axes:
        ax.grid(axis="x", visible=False)
        for x in (0.5, 1.5):  ## separate the difficulty groups across all three panels
            ax.axvline(x, color=grid, lw=1)
    axes[2].set_xticks(range(3), GROUPS)
    axes[2].tick_params(axis="x", labelsize=11)
    handles = [plt.Rectangle((0, 0), 1, 1, color=color[m]) for m in METHODS]
    fig.legend(handles, METHODS, frameon=False, ncols=len(METHODS), loc="upper right", bbox_to_anchor=(0.99, 0.955))
    fig.suptitle(f"TRAIN: plans passing all PC and repair cost by difficulty (n={n} per group)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    path = OUT / "fig5_train_difficulty.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("wrote", path)



if __name__ == "__main__":
    plot()
