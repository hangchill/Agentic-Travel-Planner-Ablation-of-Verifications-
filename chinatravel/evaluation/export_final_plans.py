"""Offline accepted-final export and benchmark post-processing for paired runs."""
from copy import deepcopy
import json
from pathlib import Path

from chinatravel.evaluation.repair_comparison import _component, _save


def export_final_plans(run_dir, queries=None):
    """Export native UID.json plans, reference queries, and statuses per strategy.

    Missing/failed plans are represented by {}, never removed from the population.
    Queries from saved initial states take precedence over optional runner inputs.
    """
    root = Path(run_dir)
    manifest = json.loads((root / "run_manifest.json").read_text())
    population = manifest["query_uids"]
    references = deepcopy(queries or {})
    for uid in population:
        query_path = root / "queries" / _component(uid) / "reference" / "query.json"
        if query_path.exists():
            references[uid] = json.loads(query_path.read_text())
        initial = root / "queries" / _component(uid) / "initial_state.json"
        if initial.exists():
            references[uid] = json.loads(initial.read_text())["state"]["problem"]
    if any(uid not in references for uid in population):
        raise ValueError("Missing reference queries for benchmark population")
    references = {uid: references[uid] for uid in population}
    exports = {}
    for strategy in manifest["repair_strategies_requested"]:
        directory = root / "benchmark_eval" / _component(strategy)
        plans, statuses = {}, {}
        for uid in population:
            path = root / "queries" / _component(uid) / (_component(strategy) + ".json")
            pair = json.loads(path.read_text()) if path.exists() else {}
            verification = pair.get("final_verification") or {}
            plan = verification.get("translated_plan")
            # Never fall back to a candidate, including a rejected final attempt.
            plans[uid] = deepcopy(plan) if isinstance(plan, dict) else {}
            statuses[uid] = pair.get("execution_status", "initial_generation_failed")
            _save(directory / "plans" / (uid + ".json"), plans[uid])
        _save(directory / "evaluation_population.json", dict(
            run_id=manifest["run_id"], repair_strategy=strategy,
            language=manifest["language"], query_uids=population, statuses=statuses,
            partition=manifest.get("partition"), queries=references))
        exports[strategy] = (directory, plans)
    return references, exports


def evaluate_repair_run(run_dir, queries=None, *, evaluator=None, preference=False):
    """Reuse eval_exp's benchmark definitions; do not invoke generation/repair."""
    if evaluator is None:
        from eval_exp import evaluate_final_plans
        evaluator = evaluate_final_plans
    references, exports = export_final_plans(run_dir, queries)
    manifest = json.loads((Path(run_dir) / "run_manifest.json").read_text())
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
    return results
