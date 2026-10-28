"""Effectiveness of R0-R4 on Easy / Medium / Human queries (subset_test, 10 queries per group).

Data (benchmark scoring): test_result_analysis/merged/table1_pc.csv, table2_cs.csv,
table3_repair_process.csv and table4_eval_exp.csv. These tables come from
scripts/result_analysis/build_test_result_tables.py.

Writes three PNG files to test_result_analysis/difficulty_comparison_graphs/:
  change_bars.png                     change from initial to final plan in % PC and % CS checks passed
  logical_macro_with_cost.png         bars of final plans passing all PC (= logical macro), with avg
                                      tokens and avg repair time per query
                                      under each bar (report version, all values labelled)
  logical_macro_with_cost_slide.png   the same, without value labels in the cost panels (slides)
Commonsense macro and all-pass ratio (0-10% everywhere) are printed, not plotted.

Usage: python test_result_analysis/difficulty_comparison_graphs/difficulty_comparison_ALL.py
(needs matplotlib and numpy)
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent  ## test_result_analysis/difficulty_comparison_graphs
MERGED = HERE.parent / "merged"
OUT = HERE  ## the PNG files go next to this script
GROUPS = ["Easy", "Medium", "Human"]
METHODS = ["R0", "R1", "R2", "R3", "R4"]

## Colours go around the colour wheel (blue -> aqua -> amber -> pink -> violet), so the bars flow,
## and neighbouring bars stay easy to tell apart. All checks of the dataviz palette validator
## pass (light mode). Aqua, amber and pink are below 3:1 contrast, so every bar has a value label.
COLOR = {"R0": "#2a78d6", "R1": "#1baf7a", "R2": "#eda100", "R3": "#e87ba4", "R4": "#6250d6"}
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9"
WIDTH = 0.16

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


def value(table, metric, group, method):
    if metric not in table:  ## a unique prefix is accepted (the table 4 names are long)
        matches = [m for m in table if m.startswith(metric)]
        assert len(matches) == 1, (metric, matches)
        metric = matches[0]
    return float(table[metric][f"{group} {method}"])


def title(fig, text):
    fig.suptitle(text, x=0.01, ha="left", fontsize=12, fontweight="bold")


def method_legend(fig, y=0.99):
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOR[m]) for m in METHODS]
    fig.legend(handles, METHODS, frameon=False, ncols=5, loc="upper right", bbox_to_anchor=(0.99, y))


def grouped_bars(ax, table, metric, fmt="{:+.1f}", fontsize=7):
    for i, method in enumerate(METHODS):
        values = [value(table, metric, g, method) for g in GROUPS]
        bars = ax.bar(np.arange(3) + (i - 2) * WIDTH, values, width=WIDTH - 0.02, color=COLOR[method])
        for bar, v in zip(bars, values):
            ax.annotate(fmt.format(v), (bar.get_x() + bar.get_width() / 2, v),
                        xytext=(0, 2 if v >= 0 else -2), textcoords="offset points", ha="center",
                        va="bottom" if v >= 0 else "top", fontsize=fontsize, color=INK2)
    ax.set_xticks(range(3), GROUPS)


def change_bars(t1, t2):
    """Change from initial to final plan (pp) in % PC passed and % CS checks passed."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    for ax, table, metric, label in (
            (axes[0], t1, "Avg % PC passed per query - change (percentage points)", "Change in % PC passed"),
            (axes[1], t2, "Avg % CS checks passed per query - change (percentage points)",
             "Change in % CS checks passed")):
        grouped_bars(ax, table, metric)
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_title(label)
        ax.set_ylabel("pp, final − initial (higher = better)")
    axes[0].set_ylim(-3, 6.5)
    axes[1].set_ylim(-4, 12.5)
    method_legend(fig)
    title(fig, "Improvement from initial to final plan, by difficulty")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT / "change_bars.png", dpi=150)
    plt.close(fig)


TOKENS = "[per query] Avg tokens spent per query (queries with complete token data)"
TIME = "[per query] Avg repair time per query (s)"


def cost_points(ax, table, metric, scale, fmt, label, labels=True):
    """One point per strategy and group, at the same x as its bar in the panel above."""
    top = 0
    for i, method in enumerate(METHODS):
        x = np.arange(3) + (i - 2) * WIDTH
        values = [value(table, metric, g, method) / scale for g in GROUPS]
        ax.vlines(x, 0, values, color=GRID, lw=1.2, zorder=1)  ## thin stem, ties the point to the bar
        ax.scatter(x, values, s=70 if labels else 90, color=COLOR[method], edgecolor=SURFACE,
                   linewidth=1.5, zorder=3)
        if labels:
            for xi, v in zip(x, values):
                ax.annotate(fmt.format(v), (xi, v), xytext=(0, 7), textcoords="offset points", ha="center",
                            fontsize=7, color=INK2)
        top = max(top, *values)
    ax.set_ylim(0, top * (1.22 if labels else 1.1))
    ax.set_ylabel(label)


def logical_macro_with_cost(t1, t3, t4, path, labels=True):
    """Bars of final plans passing all PC (%) on top; avg tokens and avg repair time per query below.

    The bars are ChinaTravel's logical macro (eval_exp). It is the same as table 1's
    "Final plans with 0 failed PC" as a %, so the plot uses the group's name for it.
    Shared x axis: each strategy's cost points are directly under its bar. Commonsense macro
    and all-pass ratio are only 0-10% (0 or 1 plan of 10), so they are printed, not plotted.
    labels=False leaves out the value labels in the cost panels (slide version)."""
    for g in GROUPS:  ## logical macro must equal table 1's count of plans with 0 failed PC
        for m in METHODS:
            assert value(t4, "Logical macro (%)", g, m) == 10 * value(t1, "Final plans with 0 failed PC", g, m), (g, m)
    fig, axes = plt.subplots(3, 1, figsize=(10, 9.4), sharex=True, height_ratios=(1.3, 1, 1))
    grouped_bars(axes[0], t4, "Logical macro (%)", fmt="{:.0f}", fontsize=8 if labels else 10)
    axes[0].set_ylim(0, 100)
    axes[0].set_ylabel("Final plans passing\nall PC (%)")
    cost_points(axes[1], t3, TOKENS, 1000, "{:.0f}k", "Avg tokens per query\n(thousands)", labels)
    cost_points(axes[2], t3, TIME, 1, "{:.0f}s", "Avg repair time\nper query (s)", labels)
    for ax in axes:
        ax.grid(axis="x", visible=False)
        for x in (0.5, 1.5):  ## separate the difficulty groups across all three panels
            ax.axvline(x, color=GRID, lw=1)
    axes[2].set_xticks(range(3), GROUPS)
    axes[2].tick_params(axis="x", labelsize=11)
    method_legend(fig, y=0.955)
    title(fig, "Plans passing all PC and repair cost by difficulty (n=10 per group)")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def print_other_macros(t4):
    """Print commonsense macro and all-pass ratio (not plotted) for the report text."""
    for metric in ("Commonsense macro (%)", "All-pass ratio (%)"):
        cells = {(g, m): value(t4, metric, g, m) for g in GROUPS for m in METHODS}
        nonzero = ", ".join(f"{g} {m} {v:.0f}%" for (g, m), v in cells.items() if v)
        print(f"{metric}: range {min(cells.values()):.0f}-{max(cells.values()):.0f}%; non-zero: {nonzero or 'none'}")
    for g in GROUPS:  ## all-pass can not be higher than either macro
        for m in METHODS:
            both = min(value(t4, "Commonsense macro (%)", g, m), value(t4, "Logical macro (%)", g, m))
            assert value(t4, "All-pass ratio (%)", g, m) <= both, (g, m)


def main():
    t1, t2, t3, t4 = (load_table(n) for n in ("table1_pc.csv", "table2_cs.csv", "table3_repair_process.csv",
                                               "table4_eval_exp.csv"))
    OUT.mkdir(exist_ok=True)
    (OUT / "logical_macro.png").unlink(missing_ok=True)  ## replaced by the joint figure below
    change_bars(t1, t2)
    logical_macro_with_cost(t1, t3, t4, OUT / "logical_macro_with_cost.png", labels=True)  ## report version
    logical_macro_with_cost(t1, t3, t4, OUT / "logical_macro_with_cost_slide.png", labels=False)  ## slide
    print_other_macros(t4)
    print("wrote", sorted(p.name for p in OUT.glob("*.png")), "to", OUT)


if __name__ == "__main__":
    main()
