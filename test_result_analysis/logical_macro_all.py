"""Logical macro and repair cost for R0-R4 on the whole test set (subset_test, 30 queries).

Three panels with a shared x axis (one column per strategy):
  - logical macro: % of final plans that pass every PC (ChinaTravel eval_exp; the same as
    table 1's "Final plans with 0 failed PC" as a %)
  - avg tokens spent per query
  - avg repair time per query

Data: the "All" columns of test_result_analysis/merged/table3_repair_process.csv and
table4_eval_exp.csv (from scripts/result_analysis/build_test_result_tables.py).
Writes logical_macro_all.png next to this script.

Usage: python test_result_analysis/logical_macro_all.py  (needs matplotlib)
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
MERGED = HERE / "merged"
OUT = HERE / "logical_macro_all.png"
METHODS = ["R0", "R1", "R2", "R3", "R4"]
TOKENS = "[per query] Avg tokens spent per query (queries with complete token data)"
TIME = "[per query] Avg repair time per query (s)"

## Same colours as difficulty_comparison_ALL.py (checked with the dataviz palette validator).
COLOR = {"R0": "#2a78d6", "R1": "#1baf7a", "R2": "#eda100", "R3": "#e87ba4", "R4": "#6250d6"}
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
    "axes.titleweight": "bold", "axes.titlesize": 11, "axes.axisbelow": True,
})


def load_table(name):
    with open(MERGED / name, encoding="utf-8") as stream:
        return {row["metric"]: row for row in csv.DictReader(stream)}


def value(table, metric, method, group="All"):
    if metric not in table:  ## a unique prefix is accepted (the table 4 names are long)
        matches = [m for m in table if m.startswith(metric)]
        assert len(matches) == 1, (metric, matches)
        metric = matches[0]
    return float(table[metric][f"{group} {method}"])


def main():
    t3 = load_table("table3_repair_process.csv")
    t4 = load_table("table4_eval_exp.csv")
    x = range(len(METHODS))
    colors = [COLOR[m] for m in METHODS]
    fig, axes = plt.subplots(3, 1, figsize=(7, 9.4), sharex=True, height_ratios=(1.3, 1, 1))

    macro = [value(t4, "Logical macro (%)", m) for m in METHODS]
    bars = axes[0].bar(x, macro, width=0.6, color=colors)
    for bar, v in zip(bars, macro):
        axes[0].annotate(f"{v:.1f}", (bar.get_x() + bar.get_width() / 2, v), xytext=(0, 3),
                         textcoords="offset points", ha="center", fontsize=9, color=INK2)
    axes[0].set_ylim(0, 100)
    axes[0].set_ylabel("Logical macro\n(% of final plans)")

    for ax, metric, scale, fmt, label in (
            (axes[1], TOKENS, 1000, "{:.0f}k", "Avg tokens per query\n(thousands)"),
            (axes[2], TIME, 1, "{:.0f}s", "Avg repair time\nper query (s)")):
        values = [value(t3, metric, m) / scale for m in METHODS]
        ax.vlines(x, 0, values, color=GRID, lw=1.2, zorder=1)  ## thin stem, ties the point to the bar
        ax.scatter(x, values, s=90, color=colors, edgecolor=SURFACE, linewidth=1.5, zorder=3)
        for xi, v in zip(x, values):
            ax.annotate(fmt.format(v), (xi, v), xytext=(0, 8), textcoords="offset points", ha="center",
                        fontsize=9, color=INK2)
        ax.set_ylim(0, max(values) * 1.22)
        ax.set_ylabel(label)

    for ax in axes:
        ax.grid(axis="x", visible=False)
    axes[2].set_xticks(list(x), METHODS)
    axes[2].tick_params(axis="x", labelsize=11)
    fig.suptitle("Logical macro and repair cost, whole test set (n=30)", x=0.01, ha="left",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT, dpi=150)
    plt.close(fig)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
