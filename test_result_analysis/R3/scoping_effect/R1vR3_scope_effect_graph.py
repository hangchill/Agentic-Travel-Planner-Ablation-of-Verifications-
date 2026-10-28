"""R1 vs R3 scope effect graph: change in % PC and % CS passed since Start, per round.

R1 edits at slot scope in every round. R3 edits at slot scope in rounds 1-2, day scope in
rounds 3-4 and plan scope in rounds 5-6. Rounds 1-2 thus compare two slot-scope strategies.

Layout (2 x 2): rows are PC and CS; columns are the phase pattern of each query.
  - cs_first: all PCs passed at Start, so the loop repairs CS errors from round 1
    (shared_repair_loop.run_repair_loop picks the phase per round; PC has priority only
    when a PC fails). Only the scope changes between rounds.
  - pc_first: some PC failed at Start, so PC rounds come first. For most of these queries,
    round 6 is the first CS round, so the scope and the phase change in the same round.
  Queries with no repair rounds (the initial plan passed) are excluded.

Definitions (the same as R3_VS_R0_scoping_effect.py):
  - State after a round: the accepted plan after that round (checkpoint repair_history;
    verification.translated_plan). A query that stopped earlier keeps its last plan.
  - Scoring: the benchmark functions eval_exp.py uses (score_plans in
    scripts/result_analysis/build_test_result_tables.py), with the constraints of
    benchmark_eval/<strategy>-*/evaluation_population.json. A PC the evaluator cannot
    evaluate counts as failed. CS % passed = 1 - failed / 28 (every plan has the same 28 checks).
  - Line: per-query mean change since Start (pp). Band: 95% bootstrap CI over queries
    (4000 resamples, fixed seed).

Reads only saved run files (no model calls). matplotlib is not a project dependency, so run:
  uv run --no-sync --with matplotlib python test_result_analysis/R3/scoping_effect/R1vR3_scope_effect_graph.py
  (--no-sync keeps uv from changing the project venv.)
Output: R1vR3_scope_effect_graph.png in the same folder as this script.
"""
import argparse
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import scripts.result_analysis.build_test_result_tables as builder  # noqa: E402
from chinatravel.evaluation.repair_comparison import pair_path  # noqa: E402

## score_plans reads builder.REPO to find output_schema.json.
builder.REPO = REPO

ROUNDS = list(range(7))  # 0 = Start
R3_SCOPE = ["", "slot", "slot", "day", "day", "plan", "plan"]
CS_TOTAL = 28
PATTERNS = {"cs_first": "All PCs passed at Start", "pc_first": "Some PCs failed at Start"}

R1_COLOR, R3_COLOR = "#2a78d6", "#eb6834"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURF = "#e1e0d9", "#c3c2b7", "#fcfcfb"


## ---------- loading and scoring ----------

def states_by_round(checkpoint):
    """Loop verification of the accepted plan after each round 0..6, and the phase letters
    ('p' personal, 'c' commonsense) of the rounds that ran."""
    history = checkpoint["repair_history"]
    current = history[0].get("verification") or {}
    states, phases = {0: current}, []
    for entry in history[1:]:
        attempt = entry.get("repair_attempt") or {}
        if entry.get("accepted"):
            current = entry.get("verification") or {}
        step = attempt.get("step", entry.get("step"))
        if step not in ROUNDS[1:]:
            raise SystemExit(f"Round step {step!r} is outside rounds 1-6; this script expects a 6-round budget")
        states[step] = current
        phases.append((attempt.get("repair_phase") or "?")[0])
    for r in ROUNDS[1:]:
        states.setdefault(r, states[r - 1])
    return states, "".join(phases)


def load_run(root):
    """One row per query: phase pattern, first CS round, and change since Start of % PC / % CS passed."""
    manifest = builder.load_json(root / "run_manifest.json")
    strategy = manifest["repair_strategies_requested"][0]
    references = builder.load_json(builder.benchmark_dir(root, strategy) / "evaluation_population.json")["queries"]
    ids = manifest["query_uids"]
    states, phases = {}, {}
    for uid in ids:
        states[uid], phases[uid] = states_by_round(builder.load_json(pair_path(root, uid, strategy)))
    language = manifest.get("language", "en")
    scores = {r: builder.score_plans(
                  ids, references,
                  {uid: builder.plan_or_empty(states[uid][r].get("translated_plan")) for uid in ids}, language)
              for r in ROUNDS}
    rows = []
    for uid in ids:
        pc = [scores[r][uid]["pc"] for r in ROUNDS]
        pc = [100 * sum(map(bool, p)) / len(p) if p else 100.0 for p in pc]
        cs = [100 * (1 - len(scores[r][uid]["cs_failed"]) / CS_TOTAL) for r in ROUNDS]
        ph = phases[uid]
        rows.append(dict(
            pattern="cs_first" if ph[:1] == "c" else ("pc_first" if ph else "none"),
            first_cs=(ph.find("c") + 1) if "c" in ph else None,
            pc=[v - pc[0] for v in pc], cs=[v - cs[0] for v in cs]))
    return rows


def mean_ci(values, n_boot=4000, seed=0):
    """Mean and 95% percentile bootstrap CI."""
    mean = sum(values) / len(values)
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(n_boot))
    return mean, boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]


## ---------- plot ----------

def plot(data, out_path):
    plt.rcParams.update({
        "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.facecolor": SURF, "figure.facecolor": SURF, "axes.spines.top": False, "axes.spines.right": False,
    })
    fig, axes = plt.subplots(2, 2, figsize=(12, 9.4), sharex=True, sharey=True)
    colors = {"R1": R1_COLOR, "R3": R3_COLOR}
    for col, pattern in enumerate(PATTERNS):
        for row_i, (key, name) in enumerate((("pc", "PC"), ("cs", "CS"))):
            ax = axes[row_i, col]
            ax.axhline(0, color=AXIS, lw=1, zorder=1)
            ## Light lines where R3's scope phase starts: slot (round 1), day (round 3), plan (round 5).
            for x, scope in ((0.5, "slot"), (2.5, "day"), (4.5, "plan")):
                ax.axvline(x, color=AXIS, lw=1, ls=(0, (4, 3)), zorder=0)
                ax.text(x + 1, 0.985, scope, transform=ax.get_xaxis_transform(),
                        ha="center", va="top", fontsize=8, color=MUTED)
            ends = {}
            for label, color in colors.items():
                rows = [r for r in data[label] if r["pattern"] == pattern]
                stats = [mean_ci([row[key][r] for row in rows], seed=r) for r in ROUNDS]
                ax.fill_between(ROUNDS, [s[1] for s in stats], [s[2] for s in stats],
                                color=color, alpha=0.13, lw=0, zorder=1)
                ax.plot(ROUNDS, [s[0] for s in stats], color=color, lw=2, marker="o", ms=5.5,
                        mec=SURF, mew=1.2, zorder=3)
                ends[label] = stats[-1][0]
            ## End labels: move them apart when the two lines end close together.
            close = abs(ends["R1"] - ends["R3"]) < 1.2
            higher = max(ends, key=lambda k: (ends[k], k == "R3"))
            for label, value in ends.items():
                dy = (6 if label == higher else -6) if close else 0
                ax.annotate(f"{label} {value:+.1f}", (6, value), xytext=(8, dy), textcoords="offset points",
                            va="center", fontsize=8.5, color=INK, fontweight="bold")
            if key == "pc" and pattern == "cs_first":
                ax.text(3, 2.2, "No round broke a PC.", ha="center", fontsize=8.5, color=INK2)
            n1 = sum(r["pattern"] == pattern for r in data["R1"])
            n3 = sum(r["pattern"] == pattern for r in data["R3"])
            ax.set_title(f"{name} · {PATTERNS[pattern]}  (R1 n={n1}, R3 n={n3})",
                         loc="left", fontsize=10, color=INK)
            ax.grid(axis="y", color=GRID, lw=0.8)
            ax.set_axisbelow(True)
            ax.tick_params(length=0)
            ax.set_xlim(-0.3, 6.9)
            if col == 0:
                ax.set_ylabel(f"Change in % {name} passed\nsince Start (pp)")
    for ax in axes[1]:
        ax.set_xticks(ROUNDS, ["Start"] + [f"{r}\nR3: {R3_SCOPE[r]}" for r in ROUNDS[1:]], fontsize=8.5)
        ax.set_xlabel("Round   (R1: slot in every round)", fontsize=9)

    ## Mark where the CS phase starts for the pc_first queries.
    first_cs = {k: Counter(r["first_cs"] for r in rows if r["pattern"] == "pc_first") for k, rows in data.items()}
    ax = axes[1, 1]
    ax.axvline(6, color=MUTED, lw=1, ls=":", zorder=1)
    ax.text(5.9, 0.02, f"round 6 = first CS round\nfor {first_cs['R3'][6]} of {sum(first_cs['R3'].values())} R3 "
            f"and {first_cs['R1'][6]} of {sum(first_cs['R1'].values())} R1 queries",
            transform=ax.get_xaxis_transform(), ha="right", va="bottom", fontsize=8, color=INK2)

    h = fig.get_figheight()
    fig.suptitle("R1 vs R3: change in PC and CS passed, per round",
                 x=0.01, ha="left", va="top", fontsize=13, color=INK, fontweight="bold", y=1 - 0.12 / h)
    fig.text(0.01, 1 - 0.42 / h,
             "Shaded bands = 95% bootstrap confidence intervals.",
             ha="left", va="top", fontsize=9.5, color=INK2)
    excluded = ", ".join(f"{k}: {n}" for k in data if (n := sum(r["pattern"] == "none" for r in data[k])))
    fig.text(0.01, 0.012,
             f"One run per strategy, from different initial plans. CS % = passed / {CS_TOTAL} checks."
             + (f"\nExcludes queries with no repair rounds ({excluded})." if excluded else ""),
             ha="left", va="bottom", fontsize=8, color=MUTED)
    fig.legend(handles=[plt.Line2D([], [], color=R1_COLOR, lw=2, marker="o", label="R1 (always slot)"),
                        plt.Line2D([], [], color=R3_COLOR, lw=2, marker="o", label="R3 (slot → day → plan)")],
               loc="lower right", bbox_to_anchor=(0.99, 0.0), ncol=2, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1 - 0.62 / h))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--r1", type=Path, default=REPO / "experiments/subset_test-r1", help="R1 run directory")
    parser.add_argument("--r3", type=Path, default=REPO / "experiments/subset_test-r3", help="R3 run directory")
    parser.add_argument("--output", type=Path, default=HERE / "R1vR3_scope_effect_graph.png")
    args = parser.parse_args(argv)
    data = {"R1": load_run(args.r1), "R3": load_run(args.r3)}
    plot(data, args.output)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
