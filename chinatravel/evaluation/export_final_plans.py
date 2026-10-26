"""Offline accepted-final export and benchmark post-processing for paired runs."""
from copy import deepcopy
import json
from pathlib import Path

from chinatravel.evaluation.repair_comparison import _component, _save, pair_path


def export_final_plans(run_dir, queries=None, *, trial_diagnostics=False):
    """Export native UID.json plans, reference queries, and statuses per strategy.

    Missing/failed plans are represented by {}, never removed from the population.
    Queries from saved initial states take precedence over optional runner inputs.
    """
    root = Path(run_dir)
    manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
    population = manifest["query_uids"]
    if not population or len(set(population)) != len(population):
        raise ValueError("Benchmark population must contain nonempty, unique query IDs")
    split = manifest.get("split_query_source")
    partition = manifest.get("partition")
    if partition is None and split and split.endswith(("_train", "_test")):
        partition = split.rsplit("_", 1)[1]
    metadata_path = root / "r4_run_metadata.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        synthetic_runtime = metadata.get("synthetic_runtime", bool(
            metadata.get("synthetic") and not metadata.get("synthetic_matrix_fixture")))
        if synthetic_runtime:
            raise ValueError("Synthetic smoke runs have no real benchmark scores")
        from r4.safety import split_uids
        if metadata.get("split") != split or not set(population) <= split_uids(split):
            raise ValueError("R4 evaluation population must match its named train/test split")
        if set(metadata.get("selected_query_ids", [])) != set(population):
            raise ValueError("R4 metadata and run manifest have different query populations")
    references = deepcopy(queries or {})
    for uid in population:
        query_path = root / "queries" / _component(uid) / "reference" / "query.json"
        if query_path.exists():
            references[uid] = json.loads(query_path.read_text(encoding="utf-8"))
        initial = root / "queries" / _component(uid) / "initial_state.json"
        if initial.exists():
            references[uid] = json.loads(initial.read_text(encoding="utf-8"))["state"]["problem"]
    if any(uid not in references for uid in population):
        raise ValueError("Missing reference queries for benchmark population")
    references = {uid: references[uid] for uid in population}
    exports = {}
    for strategy in manifest["repair_strategies_requested"]:
        directory = root / "benchmark_eval" / _component(strategy)
        if trial_diagnostics:
            directory = root / "benchmark_eval" / "trials" / strategy
        plans, statuses = {}, {}
        for uid in population:
            path = pair_path(root, uid, strategy)
            pair = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            verification = pair.get("final_verification") or {}
            plan = verification.get("translated_plan")
            # Never fall back to a candidate, including a rejected final attempt.
            plans[uid] = deepcopy(plan) if isinstance(plan, dict) else {}
            statuses[uid] = pair.get("execution_status", "initial_generation_failed")
            _save(directory / "plans" / (uid + ".json"), plans[uid])
        _save(directory / "evaluation_population.json", dict(
            run_id=manifest["run_id"], repair_strategy=strategy,
            language=manifest["language"], query_uids=population, statuses=statuses,
            split=split, partition=partition, outcome_policy="final_accepted",
            plan_source="final_verification.translated_plan", queries=references))
        exports[strategy] = (directory, plans)
    return references, exports


def evaluate_repair_run(run_dir, queries=None, *, evaluator=None, preference=False, trial_diagnostics=False):
    """Reuse eval_exp's benchmark definitions; do not invoke generation/repair."""
    if evaluator is None:
        from eval_exp import evaluate_final_plans
        evaluator = evaluate_final_plans
    references, exports = export_final_plans(run_dir, queries, trial_diagnostics=trial_diagnostics)
    manifest = json.loads((Path(run_dir) / "run_manifest.json").read_text(encoding="utf-8"))
    results = {}
    for strategy, (directory, plans) in exports.items():
        try:
            results[strategy] = evaluator(references, plans, directory,
                                          lang=manifest["language"], preference=preference)
        except Exception as exc:
            _save(directory / "benchmark_failure.json", {"exception": f"{type(exc).__name__}: {exc}"})
            raise
        else:
            (directory / "benchmark_failure.json").unlink(missing_ok=True)
            summary_path = directory / "benchmark_summary.json"
            if summary_path.is_file():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                population = json.loads((directory / "evaluation_population.json").read_text(encoding="utf-8"))
                summary.update(outcome_policy="final_accepted", split=population["split"],
                               partition=population["partition"])
                _save(summary_path, summary)
                results[strategy] = summary
                print(f"Final accepted {strategy} scores: {summary_path.resolve()}")
    return results
