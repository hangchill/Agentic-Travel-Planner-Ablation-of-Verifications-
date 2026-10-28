"""R3 vs R0: effect of R3's scope ladder on PC and CS fulfillment, by round window.

R3's scope follows the round number (rounds 1-2 slot, 3-4 day, 5-6 plan). R0 edits the
whole plan in every round, so R0's windows show the same rounds without the scope ladder.
The two runs start from different initial plans, so compare the change rows, not the levels.

Writes to <output-dir> (default test_result_analysis/R3/):
  R3_vs_R0_pc.csv      PC fulfillment: subset, row, Start, After rounds 1-2, 3-4, 5-6
  R3_vs_R0_cs.csv      CS checks, same columns
  R3_vs_R0_effectiveness.csv
                       the effectiveness table: per subset, the PC rows, then the CS rows
                       (same columns; the same rows as the two files above)
  R3_vs_R0_tables.md   both tables as Markdown

Subsets: all queries; Easy / Medium / Human (chinatravel/evaluation/splits/subset_origin.json);
and the phase pattern of each query ("CS phase from round 1" = all PC passed at the start, so
the shared loop repaired commonsense errors from round 1; "PC phase first" = personal rounds
came first).

Definitions:
  - State after a window: the accepted plan in place after the last round of the window
    (checkpoint repair_history; verification.translated_plan). A query that stopped
    earlier keeps its last plan for the later windows.
  - Scoring: the benchmark functions eval_exp.py uses (score_plans in
    scripts/result_analysis/build_test_result_tables.py, as in tables 1-2 and 6), with the
    constraints of benchmark_eval/<strategy>-*/evaluation_population.json (named places in
    English). A PC the evaluator cannot evaluate counts as failed.
  - Change in % PC passed, per-query average: the difference of the per-query average
    % PC passed between this column and the column before (from unrounded values).
  - Net PC fixed (fixed / broken): PC failing at the column before and passing at this
    column, minus PC passing before and failing now; one constraint at a time.

Needs: each run's checkpoints and benchmark_eval/ folder (scripts/result_analysis/
evaluate_repair_run.py). Reads only saved run files (no model calls, no changes to the runs).

Usage:
  python test_result_analysis/R3/R3_VS_R0_scoping_effect.py
  python test_result_analysis/R3/R3_VS_R0_scoping_effect.py \
      --run R0=experiments/subset_test-r0 --run R3=experiments/subset_test-r3 \
      --output-dir test_result_analysis/R3
"""
import argparse
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import scripts.result_analysis.build_test_result_tables as builder  # noqa: E402
from chinatravel.evaluation.repair_comparison import pair_path  # noqa: E402

## score_plans reads builder.REPO to find output_schema.json.
builder.REPO = REPO

WINDOWS = {"w12": (1, 2), "w34": (3, 4), "w56": (5, 6)}
STAGES = ("initial", *WINDOWS)
STAGE_NAMES = {"initial": "Start", "w12": "After rounds 1-2", "w34": "After rounds 3-4",
               "w56": "After rounds 5-6"}
GROUPS = ("all", "easy", "medium", "human")
PATTERNS = ("cs_first", "pc_first")
HEADINGS = {"all": "All queries", "easy": "Easy", "medium": "Medium", "human": "Human",
            "cs_first": "CS phase from round 1", "pc_first": "PC phase first (personal rounds before CS)"}
DESCRIPTIONS = {"R0": " (always whole plan)", "R1": " (always slot)", "R3": " (slot → day → plan)"}

AIM = ("Aim: show whether R3's scope ladder changes PC and CS fulfillment compared with whole-plan "
       "regeneration (R0, the baseline). R3 uses slot scope in rounds 1-2, day scope in rounds 3-4 and "
       "plan scope in rounds 5-6; R0 edits the whole plan in every round.")


## ---------- loading and scoring ----------

def states_by_window(checkpoint):
    """Loop verification of the accepted plan at the start and after each window, and the
    phase letter of each round ('p' personal, 'c' commonsense)."""
    history = checkpoint["repair_history"]
    current = history[0].get("verification") or {}
    states, last, phases = {"initial": current}, {}, []
    for entry in history[1:]:
        attempt = entry.get("repair_attempt") or {}
        if entry.get("accepted"):
            current = entry.get("verification") or {}
        step = attempt.get("step", entry.get("step"))
        window = next((name for name, steps in WINDOWS.items() if step in steps), None)
        if window is None:
            raise SystemExit(f"Round step {step!r} is outside rounds 1-6; this script expects a 6-round budget")
        last[window] = current
        phases.append((attempt.get("repair_phase") or "?")[0])
    previous = states["initial"]
    for window in WINDOWS:
        states[window] = previous = last.get(window, previous)
    return states, "".join(phases)


def load_run(label, root, origin):
    """One row per query: benchmark PC results and failed CS checks at each stage."""
    root = Path(root)
    manifest = builder.load_json(root / "run_manifest.json")
    strategy = manifest["repair_strategies_requested"][0]
    references = builder.load_json(builder.benchmark_dir(root, strategy) / "evaluation_population.json")["queries"]
    ids = manifest["query_uids"]
    missing = [uid for uid in ids if uid not in origin]
    if missing:
        raise SystemExit(f"{label}: no difficulty group for {missing}")
    states, phases = {}, {}
    for uid in ids:
        states[uid], phases[uid] = states_by_window(builder.load_json(pair_path(root, uid, strategy)))
    language = manifest.get("language", "en")
    scores = {stage: builder.score_plans(
                  ids, references,
                  {uid: builder.plan_or_empty(states[uid][stage].get("translated_plan")) for uid in ids},
                  language)
              for stage in STAGES}
    rows = []
    for uid in ids:
        pattern = "cs_first" if phases[uid][:1] == "c" else ("pc_first" if phases[uid] else "none")
        row = dict(method=label, query_uid=uid, group=origin[uid], pattern=pattern)
        for stage in STAGES:
            row[f"pc_{stage}"] = [bool(x) for x in scores[stage][uid]["pc"]]
            row[f"cs_failed_{stage}"] = set(scores[stage][uid]["cs_failed"])
        rows.append(row)
    return rows


## ---------- tables ----------

def share(states):
    return sum(states) / len(states) if states else 1.0


def pc_transitions(rows, before, after):
    pairs = [(a, b) for r in rows for a, b in zip(r[f"pc_{before}"], r[f"pc_{after}"])]
    return sum(not a and b for a, b in pairs), sum(a and not b for a, b in pairs)


def pc_table(rows):
    """(row template, Start, w12, w34, w56); '{m}' = method, '{desc}' = its description."""
    if not rows:
        return []
    pct = [100 * sum(share(r[f"pc_{s}"]) for r in rows) / len(rows) for s in STAGES]
    moves = [pc_transitions(rows, a, b) for a, b in zip(STAGES, STAGES[1:])]
    return [
        ("Avg % PC passed, {m}{desc}", *[round(value, 1) for value in pct]),
        ("Change in % PC passed in {m}, per-query average", "",
         *[f"{b - a:+.2f} pp" for a, b in zip(pct, pct[1:])]),
        ("Plans with all PC passed, {m}", *[sum(all(r[f"pc_{s}"]) for r in rows) for s in STAGES]),
        ("Net PC fixed (fixed / broken), {m}", "", *[f"{f - b:+d} ({f}/{b})" for f, b in moves]),
    ]


def cs_table(rows):
    if not rows:
        return []
    moves = [(sum(len(r[f"cs_failed_{a}"] - r[f"cs_failed_{b}"]) for r in rows),
              sum(len(r[f"cs_failed_{b}"] - r[f"cs_failed_{a}"]) for r in rows))
             for a, b in zip(STAGES, STAGES[1:])]
    return [
        ("Avg CS checks failed per query, {m}{desc}",
         *[round(sum(len(r[f"cs_failed_{s}"]) for r in rows) / len(rows), 2) for s in STAGES]),
        ("Net CS checks fixed (fixed / broken), {m}", "", *[f"{f - b:+d} ({f}/{b})" for f, b in moves]),
    ]


def subset(rows, name):
    if name == "all":
        return rows
    if name in GROUPS:
        return [r for r in rows if r["group"] == name]
    return [r for r in rows if r["pattern"] == name]


def build(data, builder_fn):
    """Per subset: its heading and the table rows, ordered by metric, then by method."""
    out = []
    for name in (*GROUPS, *PATTERNS):
        parts = {label: subset(rows, name) for label, rows in data.items()}
        sizes = ", ".join(f"{label} n={len(members)}" for label, members in parts.items())
        built = {label: builder_fn(members) for label, members in parts.items()}
        table = []
        for index in range(max(len(rows) for rows in built.values())):
            for label, rows in built.items():
                if index < len(rows):
                    template, *cells = rows[index]
                    table.append([template.format(m=label, desc=DESCRIPTIONS.get(label, "")), *cells])
        out.append((name, sizes, table))
    return out


## ---------- main ----------

def main(argv=None, baseline="R0", aim=AIM, description=__doc__, script=Path(__file__).name):
    """Compare R3 with <baseline>. R3_VS_R1_scoping_effect.py calls this with baseline="R1"."""
    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="append", metavar="LABEL=DIR",
                        help=f"default: {baseline}=experiments/subset_test-{baseline.lower()} and "
                             "R3=experiments/subset_test-r3")
    parser.add_argument("--origin", type=Path, default=REPO / "chinatravel/evaluation/splits/subset_origin.json")
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args(argv)
    specs = args.run or [f"{baseline}={REPO / 'experiments' / f'subset_test-{baseline.lower()}'}",
                         f"R3={REPO / 'experiments/subset_test-r3'}"]
    runs = []
    for spec in specs:
        label, sep, directory = spec.partition("=")
        if not sep or not label or not directory:
            raise SystemExit(f"--run expects LABEL=DIR, got {spec!r}")
        runs.append((label, Path(directory)))
    origin = builder.load_json(args.origin)["origin"]
    data = {label: load_run(label, root, origin) for label, root in runs}

    args.output_dir.mkdir(parents=True, exist_ok=True)
    columns = [STAGE_NAMES[s] for s in STAGES]
    prefix = f"R3_vs_{baseline}"
    methods = "; ".join(f"{label}{DESCRIPTIONS.get(label, '')}" for label, _ in runs)
    markdown = [f"# R3 vs {baseline}: scope ladder effect by round window", "",
                f"Generated by `test_result_analysis/R3/{script}`. Do not edit by hand; rerun the script.", "",
                aim, "",
                f"Methods: {methods}. "
                "All values use the benchmark scoring (eval_exp functions, named places in English). "
                "Change and net values compare with the column before. The runs start from different "
                "initial plans, so compare the changes, not the levels.", ""]
    by_subset = {}  ## subset label -> PC rows, then CS rows (for <prefix>_effectiveness.csv)
    for kind, title, builder_fn in (("pc", "PC fulfillment", pc_table), ("cs", "CS checks", cs_table)):
        csv_rows = []
        for name, sizes, table in build(data, builder_fn):
            csv_rows += [[f"{name} ({sizes})", *row] for row in table]
            by_subset.setdefault(f"{name} ({sizes})", []).extend(table)
            markdown += [f"## {title}: {HEADINGS[name]} ({sizes})", "",
                         "| | " + " | ".join(columns) + " |", "|---|" + "---|" * len(columns),
                         *["| " + " | ".join(str(cell) for cell in row) + " |" for row in table], ""]
        with open(args.output_dir / f"{prefix}_{kind}.csv", "w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["subset", "row", *columns])
            writer.writerows(csv_rows)
    with open(args.output_dir / f"{prefix}_effectiveness.csv", "w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["subset", "row", *columns])
        writer.writerows([label, *row] for label, rows in by_subset.items() for row in rows)
    (args.output_dir / f"{prefix}_tables.md").write_text("\n".join(markdown), encoding="utf-8")
    print(f"Wrote {prefix}_pc.csv, {prefix}_cs.csv, {prefix}_effectiveness.csv and {prefix}_tables.md "
          f"to {args.output_dir}")


if __name__ == "__main__":
    main()
