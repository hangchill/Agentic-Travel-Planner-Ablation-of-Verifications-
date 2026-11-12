"""Figures of docs/report/overleaf/evaluation_and_results.tex (Part 2), in its appendix order.

The figure list in FIGURES decides the file names and manifest IDs: the first entry is fig1 / F1, and so on.
The names are the same as in docs/report/overleaf/figures/.

fig1  effectiveness vs cost      2 x 2 bubbles: macro and per-query pass rates against repair tokens, size = repair
                                 time (tables/t1_headline.csv, t5_efficiency.csv); built here
fig2  change by difficulty       plots/difficulty_test.py
fig3  effectiveness vs cost,     the fig1 design on the train split, R0 to R3 (tables/t7b_train_headline.csv);
      train                      built here
fig4  difficulty with cost       plots/difficulty_test.py
fig5  train difficulty           plots/difficulty_train.py
fig6  R1 vs R3 scope effect      plots/r1_vs_r3_scope_effect.py (project environment, see run_all.py)

This script builds fig1 and fig3, checks that the plot scripts wrote the other four, and writes
figures/manifest_figures.csv. It removes figure files that are not in FIGURES.

Usage:  python report_result_evaluations/make_figures.py [--tables-dir DIR] [--output-dir DIR]
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STRATS = ["R0", "R1", "R2", "R3", "R4"]
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#75746e"
ACCENT = "#2a78d6"  # validated with MUTED: CVD and normal-vision separation pass, both >= 3:1 on white
SHOW_INITIAL = False  # True draws each strategy's initial-plan value as a hollow marker below its final value


# ---------------------------------------------------------------- figure builders
def effectiveness_vs_cost(fid, t1, t5, out):
    """2 x 2 bubbles: y = pass rate, x = repair tokens per query, marker size = repair time per query (binned)."""
    offsets = [{"R0": (-10, 8), "R1": (-7, -8), "R2": (9, 4), "R3": (-10, 10), "R4": (9, 5)},
               {"R0": (-10, 8), "R1": (9, 4), "R2": (9, 8), "R3": (-10, 10), "R4": (9, 5)},
               {"R0": (-10, 8), "R1": (-7, -8), "R2": (9, 4), "R3": (-10, 10), "R4": (9, 4)},
               {"R0": (-10, 8), "R1": (9, -3), "R2": (9, -8), "R3": (-10, 10), "R4": (9, 4)}]
    _bubbles(t1.set_index("strategy").loc[STRATS], t5.set_index("strategy").loc[STRATS], STRATS, offsets,
             f"Effectiveness against cost (test, 30 queries per strategy); up and left is better", out)


def effectiveness_vs_cost_train(fid, t7b, out):
    """The F1 design on the train split (R0 to R3; R4 has no train run)."""
    strats = ["R0", "R1", "R2", "R3"]
    t = t7b.set_index("strategy").loc[strats]
    offsets = [{"R0": (-10, 0), "R1": (-9, 8), "R2": (9, 8), "R3": (-10, 8)},
               {"R0": (-10, 8), "R1": (-9, 8), "R2": (9, 4), "R3": (-10, 8)},
               {"R0": (-10, 0), "R1": (-9, 6), "R2": (9, 6), "R3": (-10, 8)},
               {"R0": (-10, 0), "R1": (-9, 0), "R2": (9, 6), "R3": (-10, 8)}]
    _bubbles(t, t, strats, offsets,
             f"Effectiveness against cost (train, 60 queries per strategy); up and left is better", out)


def _bubbles(t1, t5, strats, offsets, title, out):
    x = t5.tokens_per_query.astype(float) / 1000
    # R0 and R2 spend almost the same tokens (92.5k and 92.6k); nudge them apart so neither hides the other
    if abs(x["R0"] - x["R2"]) < 3:
        x = x.copy()
        x["R0"] -= 1.6
        x["R2"] += 1.6
    secs = t5.repair_time_s_per_query.astype(float)
    bins = [(50, "< 50 s", 70), (150, "about 100 s", 210), (np.inf, "> 150 s", 420)]

    def size(v):
        return next(area for upper, _, area in bins if v < upper)

    panels = [("lpr_macro_pct", "lpr_macro_initial_pct", "Proportion of plans passing every personal constraint (%)"),
              ("epr_macro_pct", "epr_macro_initial_pct", "Proportion of plans passing every commonsense check (%)"),
              ("avg_pc_pass_pct", "avg_pc_pass_initial_pct", "Average % of personal constraints passed per query"),
              ("epr_micro_pct", "epr_micro_initial_pct", "Average % of commonsense checks passed per query")]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.2), sharex=True)
    for ax, (ycol, icol, ptitle), offs in zip(axes.flat, panels, offsets):
        y, yi = t1[ycol].astype(float), t1[icol].astype(float)
        ax.axhline(y["R0"], color=MUTED, lw=0.8, ls="--", zorder=1)
        ax.axvline(x["R0"], color=MUTED, lw=0.8, ls="--", zorder=1)
        for s in strats:
            if SHOW_INITIAL:
                ax.plot([x[s], x[s]], [yi[s], y[s]], color=MUTED, lw=1, zorder=2)
                ax.scatter(x[s], yi[s], s=28, facecolors="white", edgecolors=MUTED, linewidths=1.2, zorder=3)
            ax.scatter(x[s], y[s], s=size(secs[s]), color=INK_2 if s == "R0" else ACCENT,
                       edgecolors="white", linewidths=2, zorder=4)
            dx, dy = offs[s]
            ax.annotate(s, (x[s], y[s]), textcoords="offset points", xytext=(dx, dy), fontsize=9, color=INK,
                        ha="right" if dx < 0 else "left", va="center", weight="bold" if s == "R0" else "normal")
        ax.set_title(ptitle, fontsize=10, color=INK)
        ax.grid(alpha=0.25, lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        lo = min(y.min(), yi.min() if SHOW_INITIAL and yi.notna().all() else y.min())
        hi = y.max()
        pad = max(1.0, 0.18 * (hi - lo))
        ax.set_ylim(lo - pad, hi + pad)
        ax.tick_params(labelsize=8, colors=INK_2)
    for ax in axes[1]:
        ax.set_xlabel("Repair tokens per query (thousands)", fontsize=9, color=INK_2)
    axes[0, 0].set_xlim(x.min() - 15, x.max() + 15)

    handles = [Line2D([], [], marker="o", ls="", markersize=np.sqrt(area) / 1.25, markerfacecolor=ACCENT,
                      markeredgecolor="white", label=f"repair time {label}") for _, label, area in bins]
    handles.append(Line2D([], [], marker="o", ls="", markersize=8, markerfacecolor=INK_2, markeredgecolor="white",
                          label="R0, the baseline (dashed lines)"))
    if SHOW_INITIAL:
        handles.append(Line2D([], [], marker="o", ls="-", lw=1, color=MUTED, markersize=5, markerfacecolor="white",
                              markeredgecolor=MUTED, label="initial plan, before repair"))
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False, fontsize=8.5,
               bbox_to_anchor=(0.5, 0.0), handletextpad=0.4, columnspacing=1.4)
    fig.suptitle(title, fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(out, dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------- the ordered figure list
# (slug, kind, how, caption). kind: "build" = function(fid, *tables, out); "script" = written by that plot script.
FIGURES = [
    ("effectiveness_vs_cost", "build", (effectiveness_vs_cost, ["t1_headline", "t5_efficiency"]),
     "Macro and per-query pass rates against repair tokens; marker size = repair time per query. "
     "R0 and R2 (92.5k and 92.6k tokens) are drawn 1.6k tokens apart so neither hides the other."),
    ("change_by_difficulty", "script", "report_result_evaluations/plots/difficulty_test.py",
     "Change in personal and commonsense share passed, initial to final plan, by difficulty (test)."),
    ("effectiveness_vs_cost_train", "build", (effectiveness_vs_cost_train, ["t7b_train_headline"]),
     "The Figure F1 design on the train split, R0 to R3."),
    ("difficulty_with_cost", "script", "report_result_evaluations/plots/difficulty_test.py",
     "Final pass rate, tokens and repair time by difficulty (test)."),
    ("train_difficulty", "script", "report_result_evaluations/plots/difficulty_train.py",
     "Train split: final pass rate, tokens and repair time by difficulty, R0 to R3."),
    ("r1_vs_r3_scope_effect", "script", "report_result_evaluations/plots/r1_vs_r3_scope_effect.py",
     "R1 against R3: change since the start in % personal constraints and % commonsense checks passed, per round, "
     "by query group; bands are 95 % bootstrap CIs."),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tables-dir", type=Path, default=HERE / "tables")
    ap.add_argument("--output-dir", type=Path, default=HERE / "figures")
    args = ap.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    T = lambda name: pd.read_csv(args.tables_dir / f"{name}.csv")
    manifest = []
    for n, (slug, kind, how, caption) in enumerate(FIGURES, start=1):
        fid, name = f"F{n}", f"fig{n}_{slug}.png"
        path = out / name
        if kind == "build":
            fn, tables = how
            fn(fid, *[T(t) for t in tables], path)
            script = "report_result_evaluations/make_figures.py"
            print("wrote", path)
        else:
            script = how
            if not path.exists():
                print(f"missing: {path} (run {how} first)")
                continue
        manifest.append(dict(report_id=fid, kind="figure", path=f"figures/{name}", source_script=script,
                             has_ci=slug == "r1_vs_r3_scope_effect", caption=caption))
    current = {f"fig{n}_{slug}.png" for n, (slug, *_rest) in enumerate(FIGURES, start=1)}
    for old in out.glob("*.*"):
        if old.name not in current and old.name != "manifest_figures.csv":
            old.unlink()
            print("removed", old.name)
    pd.DataFrame(manifest).to_csv(out / "manifest_figures.csv", index=False)


if __name__ == "__main__":
    main()
