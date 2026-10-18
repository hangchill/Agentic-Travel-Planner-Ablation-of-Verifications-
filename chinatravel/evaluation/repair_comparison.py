"""Paired orchestration with atomic pair checkpoints and rebuildable indexes."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from time import perf_counter
from chinatravel.agent.system_usage import system_usage_scope, system_delta
from chinatravel.agent.model_usage import usage_snapshot, usage_delta
from urllib.parse import quote

from chinatravel.agent.nesy_verifier.initial_state import InitialRepairState
from chinatravel.agent.nesy_verifier.repair_strategies import STRATEGY_FACTORIES
from chinatravel.agent.nesy_verifier.shared_repair_loop import run_repair_loop
from chinatravel.evaluation.repair_metrics import summarize_repair_history
from chinatravel.evaluation.repair_attempt import coerce_repair_attempt


def stable_hash(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _save(path, value):
    _write(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _component(value):
    # Include a digest to avoid case-insensitive filesystem and escaped-name collisions.
    return quote(str(value), safe="")[:90] + "-" + stable_hash(str(value))[:12]


def _rebuild_indexes(root):
    """Pair checkpoints are authoritative; never append duplicate stream rows."""
    attempts, summaries = [], []
    for path in sorted((root / "queries").glob("*/*.json")):
        if path.name in ("initial_state.json", "initial_failure.json"):
            continue
        result = _load(path)
        if "execution_status" not in result:
            continue
        for record in result.get("repair_attempts", []):
            attempts.append({**coerce_repair_attempt(record).to_dict(), "run_id": result["run_id"],
                             "query_uid": result["query_uid"], "repair_strategy": result["repair_strategy"],
                             "matrix_run_id": result["matrix_run_id"]})
        if result.get("summary_metrics") is not None:
            summaries.append({**result["summary_metrics"], "run_id": result["run_id"],
                              "query_uid": result["query_uid"], "repair_strategy": result["repair_strategy"],
                              "initial_plan_hash": result["initial_plan_hash"],
                              "execution_status": result["execution_status"]})
    _write(root / "attempts.jsonl", "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in attempts))
    stream = io.StringIO(newline="")
    columns = sorted({key for row in summaries for key in row}) or [
        "run_id", "query_uid", "repair_strategy", "initial_plan_hash", "execution_status"]
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                     for key, value in row.items()} for row in summaries)
    _write(root / "summaries.csv", stream.getvalue())


@contextmanager
def _lock(root):
    path = root / ".comparison.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError("Run is locked; after a crashed process, inspect and remove its stale lock manually") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        yield
    finally:
        path.unlink()


def run_comparison(queries, *, run_id, output_root, config, prepare_initial_state,
                   runtime_factory, strategy_factories=None, skip_unavailable=False,
                   resume=False, retry_failed=False):
    """Generate once per query; runtime_factory(state, name) returns (llm, translator).

    The runtime factory MUST return a fresh isolated model/environment runtime
    per pair. Inputs to it, the preparation function, and the loop are detached
    snapshots. Strategies are constructed afresh. Completed attempts checkpoint
    before the next attempt, and indexes are atomically rebuilt from pair files.
    """
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be a nonempty single path component")
    factories = STRATEGY_FACTORIES if strategy_factories is None else strategy_factories
    requested = config["repair_strategies"]
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("Request at least one strategy, without duplicates")
    unavailable = [name for name in requested if name not in factories]
    if unavailable and not skip_unavailable:
        raise ValueError(f"Unavailable repair strategies: {unavailable}; available: {sorted(factories)}")
    if config["max_steps"] < 0:
        raise ValueError("max_steps must be nonnegative")
    for uid, problem in queries.items():
        if not isinstance(uid, str) or (problem.get("uid") is not None and problem["uid"] != uid):
            raise ValueError("Query mapping keys must be strings matching any available UID")
    root = Path(output_root) / run_id
    compatibility = {"config": config, "query_hashes": {str(uid): stable_hash(problem) for uid, problem in queries.items()},
                     "query_order": list(queries), "available_strategies": sorted(factories),
                     "skip_unavailable": skip_unavailable, "runner_format_version": 1}
    if root.exists() and not resume:
        raise ValueError("Run directory already exists; use --resume or a new run_id")
    if resume and not (root / "run_manifest.json").is_file():
        raise ValueError("Cannot resume without a run manifest")
    root.mkdir(parents=True, exist_ok=True)
    with _lock(root):
        manifest_path = root / "run_manifest.json"
        if resume:
            manifest = _load(manifest_path)
            if manifest["compatibility"] != compatibility:
                raise ValueError("Resume configuration/query/settings mismatch")
        else:
            manifest = {
                "run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat(),
                **deepcopy(config), "query_uids": list(queries),
                "repair_strategies_requested": requested,
                "repair_strategies_available": sorted(factories),
                "skipped_strategies": unavailable,
                "initial_plan_reuse_policy": "generate_once_persist_then_deepcopy_plan_context_and_verification",
                "reproducibility": "Shared initial inputs only; stochastic generation/repair and provider determinism are not guaranteed",
                "compatibility": compatibility,
            }
            _save(manifest_path, manifest)
        _rebuild_indexes(root)
        for uid, problem in queries.items():
            query_dir = root / "queries" / _component(uid)
            initial_path = query_dir / "initial_state.json"
            if initial_path.exists():
                stored = _load(initial_path)
                state = InitialRepairState.from_dict(stored["state"])
                if stored["initial_plan_hash"] != stable_hash(state.raw_initial_plan):
                    raise ValueError("Saved initial plan hash mismatch")
                if stored["initial_state_hash"] != stable_hash(state.to_dict()):
                    raise ValueError("Saved initial state was modified")
            else:
                if any(path.name != "initial_failure.json" for path in query_dir.glob("*.json")):
                    raise ValueError("Cannot regenerate missing initial state for existing pair checkpoints")
                try:
                    with system_usage_scope() as initial_usage:
                        initial_before = initial_usage.snapshot()
                        initial_started = perf_counter()
                        state = prepare_initial_state(deepcopy(problem))
                        state.generation_metadata["shared_initialization_time_s"] = perf_counter() - initial_started
                        state.generation_metadata["shared_initialization_system_metrics"] = system_delta(initial_before, initial_usage.snapshot())
                    if state.problem != problem or state.initial_verification is None:
                        raise ValueError("Preparation must retain the query and supply initial verification")
                    stored = {"run_id": run_id, "query_uid": uid, "state": state.to_dict(),
                              "initial_plan_hash": stable_hash(state.raw_initial_plan),
                              "initial_state_hash": stable_hash(state.to_dict())}
                    _save(initial_path, stored)
                except Exception as exc:
                    _save(query_dir / "initial_failure.json", {"query_uid": uid, "exception": f"{type(exc).__name__}: {exc}"})
                    continue
            plan_hash = stable_hash(state.raw_initial_plan)
            for name in requested:
                pair_path = query_dir / (_component(name) + ".json")
                if pair_path.exists():
                    old = _load(pair_path)
                    if old["initial_plan_hash"] != plan_hash:
                        raise ValueError("Pair checkpoint has a different initial plan")
                    if old["execution_status"] in ("completed", "skipped") or (
                        old["execution_status"] == "failed" and not retry_failed
                    ):
                        continue
                result = {
                    "run_id": run_id, "matrix_run_id": run_id + "/" + name,
                    "query_uid": uid, "repair_strategy": name, "initial_plan_hash": plan_hash,
                    "initial_raw_plan": deepcopy(state.raw_initial_plan),
                    "initial_verification": deepcopy(state.initial_verification),
                    "final_accepted_plan": deepcopy(state.raw_initial_plan),
                    "final_verification": deepcopy(state.initial_verification),
                    "repair_history": [{"step": 0, "accepted": True,
                                        "verification": deepcopy(state.initial_verification)}],
                    "repair_attempts": [], "summary_metrics": None,
                    "execution_status": "running", "stop_reason": None, "exception": None,
                }

                def checkpoint(history):
                    result["repair_history"] = deepcopy(history)
                    result["repair_attempts"] = [deepcopy(entry["repair_attempt"]) for entry in history[1:]]
                    accepted_entry = next(entry for entry in reversed(history) if entry["accepted"])
                    result["final_verification"] = deepcopy(accepted_entry["verification"])
                    result["final_accepted_plan"] = deepcopy(
                        accepted_entry["candidate_plan"] if accepted_entry["step"] else state.raw_initial_plan)
                    result["summary_metrics"] = summarize_repair_history(history)
                    result["summary_metrics"].update(result.get("system_metrics", {}))
                    result["summary_metrics"]["shared_initialization_time_s"] = state.generation_metadata.get("shared_initialization_time_s")
                    result["summary_metrics"]["initial_generation_time_s"] = state.generation_metadata.get("initial_generation_time_s")
                    result["summary_metrics"]["initial_generation_tool_calls"] = state.generation_metadata.get("initial_generation_tool_calls")
                    result["summary_metrics"]["shared_initialization_tool_calls"] = state.generation_metadata.get("shared_initialization_system_metrics", {}).get("tool_call_count")
                    _save(pair_path, result)
                    _rebuild_indexes(root)

                if name not in factories:
                    result.update(execution_status="skipped", stop_reason="strategy_unavailable")
                    checkpoint(result["repair_history"])
                    continue
                try:
                    detached = InitialRepairState.from_dict(state.to_dict())
                    llm, translator = runtime_factory(detached, name)
                    # Factory mutation must not change the input actually passed to the loop.
                    problem_copy, plan_copy, context_copy = deepcopy((state.problem, state.raw_initial_plan, state.repair_context))
                    if stable_hash(plan_copy) != plan_hash:
                        raise ValueError("Initial plan differs before strategy execution")
                    checkpoint(result["repair_history"])
                    with system_usage_scope() as strategy_usage:
                        system_before = strategy_usage.snapshot()
                        model_before = usage_snapshot(llm)
                        strategy_started = perf_counter()
                        try:
                            outcome = run_repair_loop(
                                problem_copy, plan_copy, factories[name](), context_copy, llm, translator,
                                max_steps=config["max_steps"], initial_verification=deepcopy(state.initial_verification),
                                history_callback=checkpoint,
                            )
                        finally:
                            metrics = system_delta(system_before, strategy_usage.snapshot())
                            metrics["total_execution_time_s"] = perf_counter() - strategy_started
                            metrics["strategy_execution_time_s"] = metrics["total_execution_time_s"]
                            metrics["repair_tool_calls"] = metrics["tool_call_count"]
                            metrics["repair_verification_count"] = metrics.pop("verification_count")
                            metrics["repair_verification_iterations"] = metrics["repair_verification_count"]
                            initial_count = state.generation_metadata.get("shared_initialization_system_metrics", {}).get("verification_count")
                            metrics["initial_verification_count"] = initial_count
                            metrics["verification_count_total"] = initial_count + metrics["repair_verification_count"] if initial_count is not None else None
                            model_after = usage_snapshot(llm)
                            for column, counter in (("model_call_count", "model_calls"), ("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens"), ("total_tokens", "total_tokens")):
                                metrics[column] = usage_delta(model_before, model_after, counter)
                            result["system_metrics"] = metrics
                    result.update(execution_status="completed", stop_reason=(
                        "verification_passed" if outcome["verification"]["passed"] else "repair_budget_exhausted"))
                    checkpoint(outcome["history"])
                except Exception as exc:
                    result.update(execution_status="failed", stop_reason="exception",
                                  exception=f"{type(exc).__name__}: {exc}")
                    checkpoint(result["repair_history"])
                if stable_hash(state.to_dict()) != stored["initial_state_hash"]:
                    raise ValueError("Shared initial snapshot mutated")
        _rebuild_indexes(root)
    return root
