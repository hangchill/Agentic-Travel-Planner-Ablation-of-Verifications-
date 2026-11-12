"""Table T14: how often each strategy repaired the constraints and checks that fail most (input of Table T16).

For every test run (R0 to R4) this script scores the initial plan and the final accepted plan of each
query with the benchmark functions (score_plans, the functions eval_exp.py uses), then counts, per
personal-constraint kind and per commonsense check:
  failing_initial   items that failed in the initial plan
  repaired          of those, items that pass in the final plan
  newly_failing     items that passed in the initial plan and fail in the final plan
  failing_final     items that fail in the final plan
The plan states come from the checkpoints, read with the R1-vs-R3 scope figure's own loader
(plots/r1_vs_r3_scope_effect.py, the script that draws fig6; imported, never changed).
Table T16 reads this table.
Personal-constraint kinds come from data/constraints.csv. A personal constraint the evaluator
cannot evaluate counts as failed, as in the benchmark.

The benchmark commonsense checker imports the sandbox tools (geopy), so run it in the project
environment:
  uv run --no-sync --with matplotlib python report_result_evaluations/failure_repair.py
Writes tables/t14_failure_repair.csv and tables/manifest_failure.csv.
"""
import argparse
import importlib.util
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
GRAPH = "report_result_evaluations/plots/r1_vs_r3_scope_effect.py"
RUNS = {"R0": "subset_test-r0", "R1": "subset_test-r1", "R2": "subset_test-r2", "R3": "subset_test-r3", "R4": "subset_test-r4"}


def load_graph_module(repo):
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    spec = importlib.util.spec_from_file_location("scope_graph", repo / GRAPH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def score_run(g, root, strategy):
    """Per query: (initial score, final score) from the benchmark functions."""
    b = g.builder
    manifest = b.load_json(root / "run_manifest.json")
    references = b.load_json(b.benchmark_dir(root, strategy) / "evaluation_population.json")["queries"]
    ids = manifest["query_uids"]
    states = {uid: g.states_by_round(b.load_json(g.pair_path(root, uid, strategy)))[0] for uid in ids}
    language = manifest.get("language", "en")
    plans = lambda r: {uid: b.plan_or_empty(states[uid][r].get("translated_plan")) for uid in ids}
    return ids, b.score_plans(ids, references, plans(0), language), b.score_plans(ids, references, plans(6), language)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", type=Path, default=HERE.parent)
    ap.add_argument("--data-dir", type=Path, default=HERE / "data")
    ap.add_argument("--output-dir", type=Path, default=HERE / "tables")
    args = ap.parse_args()
    g = load_graph_module(args.repo_root)
    C = pd.read_csv(args.data_dir / "constraints.csv")
    C = C[C.split == "test"]
    kind = {(r.strategy, r.query_uid, r.constraint_index): r.kind for r in C.itertuples()}
    bench_final = {(r.strategy, r.query_uid, r.constraint_index): r.benchmark_final for r in C.itertuples()}
    counts, mismatch = {}, 0

    def add(key, failed_initial, failed_final):
        c = counts.setdefault(key, dict(failing_initial=0, repaired=0, newly_failing=0, failing_final=0, items=0))
        c["items"] += 1
        c["failing_initial"] += failed_initial
        c["repaired"] += failed_initial and not failed_final
        c["newly_failing"] += (not failed_initial) and failed_final
        c["failing_final"] += failed_final

    for strategy, run in RUNS.items():
        ids, initial, final = score_run(g, args.repo_root / "experiments" / run, strategy)
        for uid in ids:
            for i, (p0, p1) in enumerate(zip(initial[uid]["pc"], final[uid]["pc"]), start=1):
                add(("personal", kind.get((strategy, uid, i), "Other"), strategy), not p0, not p1)
                mismatch += bench_final.get((strategy, uid, i)) not in (None, int(p1))
            f0, f1 = set(initial[uid]["cs_failed"]), set(final[uid]["cs_failed"])
            for check in sorted(f0 | f1):
                add(("commonsense", check, strategy), check in f0, check in f1)
        print(strategy, "scored", len(ids), "queries")
    rows = [dict(type=t, item=item, strategy=s, **c,
                 source=f"benchmark rescoring of initial and final plans ({GRAPH}: states_by_round; "
                        "scripts/result_analysis/build_test_result_tables.py: score_plans)")
            for (t, item, s), c in sorted(counts.items())]
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame(rows)
    table.to_csv(out / "t14_failure_repair.csv", index=False)
    pd.DataFrame([dict(report_id="T14", kind="table", path="tables/t14_failure_repair.csv", section="Ablation 3 (input of T16)",
                       source_script="report_result_evaluations/failure_repair.py", has_ci=False,
                       caption="Repair success per personal-constraint kind and commonsense check, per strategy. "
                               "Not shown in the report: Table T16 reads it.")]
                 ).to_csv(out / "manifest_failure.csv", index=False)
    print("final personal verdicts that differ from data/constraints.csv:", mismatch)
    print("wrote", out / "t14_failure_repair.csv")


if __name__ == "__main__":
    main()
