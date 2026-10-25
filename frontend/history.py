"""Read previously saved planner results without invoking model APIs."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _read_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: {exc}")
        return None


def _sort_timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _request_from_query(query: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    query = query if isinstance(query, dict) else {}
    prompt = (
        query.get("nature_language_en")
        or query.get("nature_language")
        or fallback.get("prompt")
        or ""
    )
    return {
        **fallback,
        "prompt": prompt,
        "start_city": query.get("start_city", fallback.get("start_city")),
        "target_city": query.get("target_city", fallback.get("target_city")),
        "people_number": query.get("people_number", fallback.get("people_number")),
        "days": query.get("days", fallback.get("days")),
    }


def _experiment_record(
    artifact_path: Path,
    artifact: dict[str, Any],
    *,
    reference_query: dict[str, Any] | None = None,
    final_itinerary: dict[str, Any] | None = None,
    source_kind: str = "experiment",
) -> dict[str, Any] | None:
    query = artifact.get("reference_query")
    if not isinstance(query, dict):
        query = reference_query or {}
    verification = artifact.get("final_verification")
    if not isinstance(verification, dict):
        verification = None

    itinerary: Any = None
    if verification and isinstance(verification.get("translated_plan"), dict):
        itinerary = verification["translated_plan"]
    elif isinstance(final_itinerary, dict):
        itinerary = final_itinerary
    elif isinstance(artifact.get("final_accepted_plan"), list):
        itinerary = {
            "people_number": query.get("people_number"),
            "start_city": query.get("start_city"),
            "target_city": query.get("target_city"),
            "itinerary": artifact["final_accepted_plan"],
        }

    if itinerary is None or not isinstance(itinerary, (dict, list)):
        return None

    strategy = artifact.get("repair_strategy")
    if not strategy and isinstance(final_itinerary, dict):
        strategy = final_itinerary.get("selected_source")
    if not strategy:
        strategy = "Saved plan"
    run_id = str(artifact.get("run_id") or artifact_path.parent.parent.name)
    query_uid = str(
        artifact.get("query_uid")
        or (final_itinerary or {}).get("query_uid")
        or artifact_path.parent.name
    )
    request = _request_from_query(query, {
        "strategy": strategy,
        "start_city": (final_itinerary or {}).get("start_city"),
        "target_city": (final_itinerary or {}).get("target_city"),
        "people_number": (final_itinerary or {}).get("people_number"),
        "days": len(itinerary.get("itinerary", [])) if isinstance(itinerary, dict) else None,
    })
    request["strategy"] = strategy
    created_at = artifact_path.stat().st_mtime
    label = (
        f"{request.get('start_city') or '?'} → {request.get('target_city') or '?'}"
        f" · {strategy} · {run_id} · {query_uid}"
    )
    return {
        "run_id": f"{run_id}:{query_uid}:{strategy}",
        "created_at": created_at,
        "status": artifact.get("execution_status", "saved"),
        "request": request,
        "itinerary": itinerary,
        "verification": verification,
        "repair_history": artifact.get("repair_history", []),
        "attempts": artifact.get("repair_attempts", []),
        "history_source": source_kind,
        "history_label": label,
        "history_path": str(artifact_path),
    }


def _legacy_result_record(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    method = path.parent.name
    strategy = method.rsplit("_", 1)[-1]
    if strategy not in {"R0", "R1", "R2", "R3", "R4"}:
        strategy = "Saved plan"
    states = plan.get("personal_constraints")
    states = states if isinstance(states, list) else []
    errors = plan.get("error_info")
    errors = errors if isinstance(errors, list) else []
    verification = {
        "passed": plan.get("all_constraints_pass"),
        "personal_constraints": states,
        "error_info": errors,
    }
    label = (
        f"{plan.get('start_city') or '?'} → {plan.get('target_city') or '?'}"
        f" · {strategy} · {method} · {path.stem}"
    )
    return {
        "run_id": f"{method}:{path.stem}",
        "created_at": path.stat().st_mtime,
        "status": "saved",
        "request": {
            "strategy": strategy,
            "start_city": plan.get("start_city"),
            "target_city": plan.get("target_city"),
            "people_number": plan.get("people_number"),
            "days": len(plan["itinerary"]),
            "prompt": "",
        },
        "itinerary": plan,
        "verification": verification,
        "repair_history": [],
        "attempts": [],
        "history_source": "legacy result",
        "history_label": label,
        "history_path": str(path),
    }


def discover_saved_runs(project_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Find frontend runs and prior experiment outputs under this project."""
    project_root = Path(project_root).resolve()
    errors: list[str] = []
    records: dict[tuple[str, str, str], dict[str, Any]] = {}

    frontend_runs = project_root / "frontend" / "runs"
    if frontend_runs.is_dir():
        for run_path in frontend_runs.glob("*/run.json"):
            value = _read_json(run_path, errors)
            if not isinstance(value, dict) or value.get("itinerary") is None:
                continue
            request = value.get("request")
            request = request if isinstance(request, dict) else {}
            run_id = str(value.get("run_id") or run_path.parent.name)
            strategy = str(request.get("strategy") or "Unknown")
            record = dict(value)
            record["history_source"] = "frontend"
            record["history_path"] = str(run_path)
            record["history_label"] = (
                f"{request.get('start_city') or '?'} → {request.get('target_city') or '?'}"
                f" · {strategy} · frontend · {run_id}"
            )
            records[(run_id, str(run_id), strategy)] = record

    result_root = project_root / "results"
    if result_root.is_dir():
        for result_path in result_root.rglob("*.json"):
            plan = _read_json(result_path, errors)
            if not isinstance(plan, dict) or not isinstance(plan.get("itinerary"), list):
                continue
            record = _legacy_result_record(result_path, plan)
            key = (
                record["run_id"],
                result_path.stem,
                record["request"]["strategy"],
            )
            records[key] = record

    experiments = project_root / "experiments"
    if experiments.is_dir():
        for query_dir in experiments.rglob("queries"):
            if not query_dir.is_dir():
                continue
            for query_path in query_dir.iterdir():
                if not query_path.is_dir():
                    continue
                reference_path = query_path / "reference" / "query.json"
                reference = (
                    _read_json(reference_path, errors)
                    if reference_path.is_file()
                    else {}
                )
                reference = reference if isinstance(reference, dict) else {}
                final_path = query_path / "final_itinerary.json"
                final_value = _read_json(final_path, errors) if final_path.is_file() else None
                final_value = final_value if isinstance(final_value, dict) else None

                candidates = []
                history_path = query_path / "repair_history.json"
                if history_path.is_file():
                    candidates.append((history_path, "experiment"))
                else:
                    candidates.extend(
                        (path, "experiment")
                        for path in query_path.glob("*.json")
                        if path.name not in {
                            "initial_state.json",
                            "final_state.json",
                            "final_itinerary.json",
                        }
                    )

                for artifact_path, source_kind in candidates:
                    artifact = _read_json(artifact_path, errors)
                    if not isinstance(artifact, dict):
                        continue
                    if not any(
                        key in artifact
                        for key in ("final_verification", "final_accepted_plan")
                    ):
                        continue
                    record = _experiment_record(
                        artifact_path,
                        artifact,
                        reference_query=reference,
                        final_itinerary=final_value,
                        source_kind=source_kind,
                    )
                    if record is None:
                        continue
                    request = record["request"]
                    dedupe_key = (
                        str(artifact.get("run_id") or query_dir.parent.name),
                        str(artifact.get("query_uid") or query_path.name),
                        str(artifact.get("repair_strategy") or request.get("strategy")),
                    )
                    existing = records.get(dedupe_key)
                    if existing is None or (
                        len(record.get("repair_history") or [])
                        > len(existing.get("repair_history") or [])
                    ):
                        records[dedupe_key] = record

        for plans_dir in experiments.rglob("plans"):
            if (
                not plans_dir.is_dir()
                or plans_dir.parent.parent.name != "benchmark_eval"
            ):
                continue
            strategy_folder = plans_dir.parent.name
            strategy = strategy_folder.split("-", 1)[0]
            population_path = plans_dir.parent / "evaluation_population.json"
            population = _read_json(population_path, errors) if population_path.is_file() else {}
            population = population if isinstance(population, dict) else {}
            queries = population.get("queries")
            queries = queries if isinstance(queries, dict) else {}
            for plan_path in plans_dir.glob("*.json"):
                plan = _read_json(plan_path, errors)
                if not isinstance(plan, dict) or not isinstance(plan.get("itinerary"), list):
                    continue
                uid = plan_path.stem
                run_id = plans_dir.parent.parent.parent.name
                plan_strategy = str(plan.get("selected_source") or strategy)
                if plan_strategy == "selected":
                    plan_strategy = strategy
                if strategy_folder == "selected" and any(
                    key[0] == run_id and key[1] == uid for key in records
                ):
                    continue
                matching_pair = any(
                    key[1] == uid and key[2] == plan_strategy
                    for key in records
                )
                if matching_pair:
                    continue
                record = _experiment_record(
                    plan_path,
                    {
                        "query_uid": uid,
                        "repair_strategy": plan_strategy,
                        "run_id": run_id,
                    },
                    reference_query=queries.get(uid),
                    final_itinerary=plan,
                    source_kind="exported plan",
                )
                if record:
                    key = (str(record["run_id"]), uid, plan_strategy)
                    records.setdefault(key, record)

    results = sorted(
        records.values(),
        key=lambda record: _sort_timestamp(record.get("created_at")),
        reverse=True,
    )
    for record in results:
        record["created_at"] = str(record.get("created_at", ""))
    return results, errors
