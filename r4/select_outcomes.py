"""Select the least unresolved outcome and account for every matrix trial."""

from copy import deepcopy
import json

from chinatravel.evaluation.repair_comparison import _save, _rebuild_indexes
from pathlib import Path


def violation_score(report):
    """Unknown checks cannot make an unverifiable plan appear better."""
    states = report.get("personal_constraints", [])
    failed = sum(state is False for state in states)
    unknown = sum(state is None for state in states)
    common = len(report.get("commonsense_errors") or [])
    schema = len(report.get("schema_errors") or [])
    unavailable = int(bool(report.get("verification_unavailable"))) + sum(
        len(report.get(key) or []) for key in ("verifier_errors", "translation_errors", "evaluation_errors")
    )
    # A non-passing report with no explanation still has one unresolved check.
    unresolved = failed + unknown + common + schema + unavailable
    if report.get("passed") is not True:
        unresolved = max(1, unresolved)
    return unresolved, unknown + unavailable, failed, common, schema


def complete_sum(values):
    return sum(values) if all(value is not None for value in values) else None


def write_query_exports(query_dir, selection, problem=None):
    root = Path(query_dir)
    cost_export = {
        "query_uid": selection["query_uid"],
        "mode": selection["mode"],
        "execution_status": selection.get("execution_status"),
        "repair_attempt_count_all_trials": selection["repair_attempt_count_all_trials"],
        "costs": selection["costs"],
        "monetary_cost": selection["monetary_cost"],
        "trial_statuses": selection.get("trial_statuses"),
    }
    (root / "computational_cost.json").write_text(
        json.dumps(cost_export, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    itinerary_export = None
    if selection.get("selected_plan") is not None:
        problem = problem or {}
        itinerary_export = {
            "query_uid": selection["query_uid"],
            "selected_source": selection.get("selected_source"),
            "selected_step": selection.get("selected_step"),
            "people_number": problem.get("people_number"),
            "start_city": problem.get("start_city"),
            "target_city": problem.get("target_city"),
            "itinerary": selection["selected_plan"],
        }
    (root / "final_itinerary.json").write_text(
        json.dumps(itinerary_export, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def matrix_details(root, metadata, strategy):
    """Human-readable provenance, with paths relative to the experiment."""
    info = deepcopy(metadata.get("matrices", {}).get(strategy, {}))
    info.setdefault("matrix_used", strategy.removeprefix("R4_") if strategy != "R4" else "pooled")
    if info.get("path"):
        path = Path(info["path"])
        if path.is_absolute() and path.is_relative_to(root.resolve()):
            info["path"] = path.relative_to(root.resolve()).as_posix()
        path = root / info["path"]
        manifest_path = path.with_name("main_matrix_manifest.json")
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            info["perspective"] = manifest.get("perspective")
            info["synthetic_matrix_fixture"] = manifest.get("fixture_type") == "synthetic_test_fixture"
    return info


def trial_paths(query_dir):
    # Derived exports also have execution_status/history; never treat them as trials.
    paths = sorted([*query_dir.glob("R4*.json"), *(query_dir / "trials").glob("*.json")])
    seen = set()
    for path in paths:
        trial = json.loads(path.read_text(encoding="utf-8"))
        name = trial.get("repair_strategy", "")
        if not name.startswith("R4") or not isinstance(trial.get("repair_history"), list):
            continue
        if name in seen:
            raise ValueError(f"Duplicate R4 trial checkpoint: {name}")
        seen.add(name)
        yield path, trial


def annotate_trial(trial, matrix):
    trial["matrix_used"] = matrix["matrix_used"]
    trial["matrix"] = matrix
    # Both serialized views of an attempt carry the same provenance.
    records = list(trial.get("repair_attempts", []))
    for entry in trial.get("repair_history", []):
        entry["matrix_used"] = matrix["matrix_used"] if entry.get("step") else None
        if entry.get("repair_attempt") is not None:
            records.append(entry["repair_attempt"])
    for record in records:
        record["repair_metadata"] = {
            **record.get("repair_metadata", {}),
            "matrix_used": matrix["matrix_used"], "matrix": matrix,
        }
        if matrix.get("path"):
            record["repair_metadata"]["risk_matrix_path"] = matrix["path"]
    for entry in trial.get("repair_history", [])[1:]:
        entry.setdefault("metadata", {}).update(matrix_used=matrix["matrix_used"], matrix=matrix)
        if matrix.get("path"):
            entry["metadata"]["risk_matrix_path"] = matrix["path"]
    return trial


def export_status(trials, metadata):
    if any(t["execution_status"] == "failed" for t in trials):
        return "failed"
    if any(t["execution_status"] == "running" for t in trials):
        return "running"
    expected = set(metadata.get("repair_budgets", {}))
    if not trials or expected - {t["repair_strategy"] for t in trials}:
        return "incomplete"
    return "completed" if any(t["execution_status"] == "completed" for t in trials) else "skipped"


def write_standard_exports(query_dir, selection, metadata, initial=None, trials=(), failure=None):
    """R2 checkpoint field names are the common R0-R4 artifact contract."""
    root = Path(query_dir)
    state = initial["state"] if initial else {}
    generation = state.get("generation_metadata", {})
    initial_report = state.get("initial_verification")
    initial_plan = state.get("raw_initial_plan")
    matrices = {name: matrix_details(root.parent.parent, metadata, name)
                for name in metadata.get("matrices", {})}
    # Include inferred labels in fixtures/older metadata too.
    matrices.update({t["repair_strategy"]: t["matrix"] for t in trials})
    history = [{"step": 0, "accepted": True, "verification": initial_report,
                "repair_strategy": "initial", "matrix_used": None}] if initial else []
    attempts = []
    for trial in trials:
        identity = {"repair_strategy": trial["repair_strategy"], "matrix_used": trial["matrix_used"]}
        history.extend({**entry, **identity} for entry in trial.get("repair_history", [])[1:])
        attempts.extend({**record, "repair_strategy": trial["repair_strategy"]}
                        for record in trial.get("repair_attempts", []))
    selected_trial = next((t for t in trials if t["repair_strategy"] == selection.get("selected_source")), None)
    costs = selection["costs"] or {}
    system_metrics = {
        "model_call_count": costs.get("all_trials_model_calls"),
        "prompt_tokens": costs.get("all_trials_input_tokens_delta"),
        "completion_tokens": costs.get("all_trials_output_tokens_delta"),
        "total_tokens": costs.get("all_trials_total_tokens_delta"),
        "tool_call_count": costs.get("all_trials_tool_call_count"),
        "successful_tool_call_count": costs.get("all_trials_successful_tool_call_count"),
        "failed_tool_call_count": costs.get("all_trials_failed_tool_call_count"),
        "repair_tool_calls": costs.get("all_trials_tool_call_count"),
        "repair_verification_count": costs.get("all_trials_verification_count"),
        "repair_verification_iterations": costs.get("all_trials_verification_count"),
        "strategy_execution_time_s": costs.get("all_trials_execution_time_seconds"),
        "total_execution_time_s": costs.get("all_trials_execution_time_seconds"),
        "initial_verification_count": generation.get("shared_initialization_system_metrics", {}).get("verification_count"),
        "verification_count_total": costs.get("including_initial_verification_count"),
    }
    type_counts = [t.get("system_metrics", {}).get("tool_call_counts_by_type") for t in trials]
    system_metrics["tool_call_counts_by_type"] = (
        {key: sum(counts.get(key, 0) for counts in type_counts)
         for key in sorted({key for counts in type_counts for key in counts})}
        if trials and all(isinstance(counts, dict) for counts in type_counts) else None)
    record = {
        "run_id": (initial or {}).get("run_id", root.parent.parent.name),
        "matrix_run_id": root.parent.parent.name + "/R4_selected",
        "query_uid": selection["query_uid"],
        "repair_strategy": "R4",
        "initial_plan_hash": (initial or {}).get("initial_plan_hash"),
        "initial_raw_plan": initial_plan,
        "initial_verification": initial_report,
        "final_accepted_plan": selection.get("selected_plan"),
        "final_verification": selection.get("selected_verification"),
        "repair_history": history,
        "repair_attempts": attempts,
        "execution_status": selection["execution_status"],
        "stop_reason": ("initial_generation_failed" if failure else
                        trials[0].get("stop_reason") if len(trials) == 1 else
                        "matrix_trials_finished" if trials else "missing_trials"),
        "exception": failure.get("exception") if failure else
            {t["repair_strategy"]: t["exception"] for t in trials if t.get("exception")} or None,
        "system_metrics": system_metrics,
        "reference_query": "reference/query.json",
        "initial_state_path": "initial_state.json" if initial else None,
        "mode": metadata["mode"],
        "matrices_used": matrices,
        "selected_matrix_used": selected_trial["matrix_used"] if selected_trial else None,
        "selected_source": selection.get("selected_source"),
        "selected_step": selection.get("selected_step"),
        "selection_score": selection.get("selection_score"),
        "selection_rule": selection.get("selection_rule"),
        "initial_generation_metadata": generation,
        "costs": selection["costs"],
        "monetary_cost": selection["monetary_cost"],
        "repair_attempt_count_all_trials": selection["repair_attempt_count_all_trials"],
        "trials": list(trials),
    }
    _save(root / "repair_history.json", record)
    _save(root / "final_state.json", {key: value for key, value in record.items()
          if key not in ("repair_history", "repair_attempts", "trials", "initial_generation_metadata")})
    # The selected final state supersedes the old partial export.
    (root / "r4_selected_outcome.json").unlink(missing_ok=True)


def select_outcomes(run_dir, metadata):
    root = Path(run_dir)
    selections = []
    # Preserve failed query cases in the population; their unavailable usage is
    # explicitly unknown, rather than silently dropping them from the totals.
    for failure_path in sorted((root / "queries").glob("*/initial_failure.json")):
        if failure_path.with_name("initial_state.json").exists():
            continue
        failure = json.loads(failure_path.read_text(encoding="utf-8"))
        selections.append({
            "query_uid": failure["query_uid"], "mode": metadata["mode"],
            "execution_status": "initial_generation_failed", "exception": failure.get("exception"),
            "selected_plan": None, "selected_verification": None,
            "repair_attempt_count_all_trials": 0, "costs": None, "monetary_cost": None,
        })
        write_query_exports(failure_path.parent, selections[-1])
        write_standard_exports(failure_path.parent, selections[-1], metadata, failure=failure)
    for initial_path in sorted((root / "queries").glob("*/initial_state.json")):
        initial = json.loads(initial_path.read_text(encoding="utf-8"))
        state = initial["state"]
        candidates = [{
            "source": "initial", "step": 0, "plan": state["raw_initial_plan"],
            "verification": state["initial_verification"],
        }]
        trials = []
        for path, trial in trial_paths(initial_path.parent):
            trial = annotate_trial(trial, matrix_details(root, metadata, trial["repair_strategy"]))
            _save(path, trial)
            trials.append(trial)
            for entry in trial.get("repair_history", [])[1:]:
                record = entry["repair_attempt"]
                if record.get("exception") is None and entry.get("candidate_plan") is not None:
                    candidates.append({
                        "source": trial["repair_strategy"], "step": entry["step"],
                        "plan": entry["candidate_plan"], "verification": entry["verification"],
                    })
        winner = min(candidates, key=lambda item: (violation_score(item["verification"]), item["step"], item["source"]))
        attempts = [attempt for trial in trials for attempt in trial.get("repair_attempts", [])]
        if len(attempts) > metadata["max_repairs_per_query_total"]:
            raise ValueError("Global R4 repair budget was exceeded")
        generation = state.get("generation_metadata", {})
        initial_system = generation.get("shared_initialization_system_metrics", {})
        # Do not turn missing provider usage into zero or infer dollar charges.
        costs = {}
        for key, initial_key in (("input_tokens_delta", "input_tokens"), ("output_tokens_delta", "output_tokens"),
                                 ("total_tokens_delta", "total_tokens"), ("model_calls", "model_calls"),
                                 ("failed_model_calls", "failed_model_calls")):
            repair_total = complete_sum([record.get(key) for record in attempts])
            costs["all_trials_" + key] = repair_total
            costs["including_initial_" + initial_key] = complete_sum([generation.get(initial_key), repair_total])
        for key in ("tool_call_count", "verification_count", "successful_tool_call_count", "failed_tool_call_count"):
            repair_total = complete_sum([record.get(key) for record in attempts])
            costs["all_trials_" + key] = repair_total
            costs["including_initial_" + key] = complete_sum([initial_system.get(key), repair_total])
        for key in ("repair_time_seconds", "verification_time_seconds", "attempt_time_seconds"):
            costs["all_trials_" + key] = complete_sum([record.get(key) for record in attempts])
        runtime = complete_sum([trial.get("system_metrics", {}).get("strategy_execution_time_s") for trial in trials])
        costs["all_trials_execution_time_seconds"] = runtime
        costs["including_initial_execution_time_seconds"] = complete_sum([
            generation.get("shared_initialization_time_s"), runtime,
        ])
        selection = {
            "query_uid": initial["query_uid"], "mode": metadata["mode"],
            "execution_status": export_status(trials, metadata),
            "matrices_used": {t["repair_strategy"]: t["matrix"] for t in trials},
            "selected_matrix_used": next((t["matrix_used"] for t in trials if t["repair_strategy"] == winner["source"]), None),
            "selection_score": list(violation_score(winner["verification"])),
            "selected_source": winner["source"], "selected_step": winner["step"],
            "selected_plan": winner["plan"], "selected_verification": winner["verification"],
            "repair_attempt_count_all_trials": len(attempts),
            "costs": costs, "monetary_cost": None,
            "trial_statuses": {trial["repair_strategy"]: trial["execution_status"] for trial in trials},
            "selection_rule": "min (unresolved checks, unknowns, personal failures, commonsense, schema); then earliest step, source",
        }
        write_standard_exports(initial_path.parent, selection, metadata, initial=initial, trials=trials)
        write_query_exports(initial_path.parent, selection, state.get("problem"))
        selections.append(selection)
    (root / "r4_selection_and_costs.json").write_text(
        json.dumps(selections, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    if (root / "run_manifest.json").is_file():
        _rebuild_indexes(root, raw_only=True)
    return selections
