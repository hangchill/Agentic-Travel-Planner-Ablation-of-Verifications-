"""Benchmark selected R4 plans against saved references for their train/test split."""

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def evaluate_selected(run_dir, evaluator=None, *, preference=False):
    root = Path(run_dir)
    metadata = json.loads((root / "r4_run_metadata.json").read_text(encoding="utf-8"))
    # Older runs used one flag for both fabricated matrices and mock runtimes.
    synthetic_runtime = metadata.get("synthetic_runtime", bool(
        metadata.get("synthetic") and not metadata.get("synthetic_matrix_fixture")))
    if synthetic_runtime:
        raise ValueError("Synthetic smoke runs have no real benchmark scores")
    from r4.safety import split_uids
    split = metadata["split"]
    allowed = split_uids(split)
    selected = metadata["selected_query_ids"]
    if not selected or len(set(selected)) != len(selected) or not set(selected) <= allowed:
        raise ValueError(f"Selected evaluation population must contain unique query IDs from {split}")
    partition = "test" if split.endswith("_test") else "train"
    if metadata.get("evaluation_split_partition", partition) != partition:
        raise ValueError("Evaluation partition does not match the selected split")
    rows = json.loads((root / "r4_selection_and_costs.json").read_text(encoding="utf-8"))
    references = {}
    for path in (root / "queries").glob("*/reference/query.json"):
        problem = json.loads(path.read_text(encoding="utf-8"))
        if problem["uid"] in selected:
            references[problem["uid"]] = problem
    if set(references) != set(selected):
        raise ValueError("Missing saved reference queries for the selected evaluation population")
    references = {uid: references[uid] for uid in selected}
    plans = {uid: {} for uid in selected}
    seen = set()
    for row in rows:
        uid = row["query_uid"]
        if uid not in plans or uid in seen:
            raise ValueError("Selected outcomes contain an unexpected or duplicate query ID")
        seen.add(uid)
        plans[uid] = (row.get("selected_verification") or {}).get("translated_plan") or {}
    destination = root / "benchmark_eval" / "selected"
    destination.mkdir(parents=True, exist_ok=True)
    for uid, plan in plans.items():
        (destination / "plans").mkdir(exist_ok=True)
        (destination / "plans" / (uid + ".json")).write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "evaluation_population.json").write_text(json.dumps({
        "query_uids": list(plans), "partition": partition, "split": split,
        "language": metadata["language"],
        "selection": "r4_selection_and_costs.json", "queries": references,
        "synthetic_matrix_fixture": bool(metadata.get("synthetic_matrix_fixture")),
        "synthetic_runtime": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if evaluator is None:
        from eval_exp import evaluate_final_plans
        evaluator = evaluate_final_plans
    failure = destination / "benchmark_failure.json"
    try:
        result = evaluator(references, plans, destination, lang=metadata["language"], preference=preference)
    except Exception as exc:
        failure.write_text(json.dumps({"exception": f"{type(exc).__name__}: {exc}"}) + "\n", encoding="utf-8")
        raise
    failure.unlink(missing_ok=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    evaluate_selected(args.run_dir)


if __name__ == "__main__":
    sys.path.insert(0, str(PROJECT_ROOT.parent))
    main()
