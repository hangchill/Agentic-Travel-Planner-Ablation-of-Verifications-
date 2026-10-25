"""Persistence helpers for Streamlit demo runs."""

import json
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def save_run_artifacts(run_dir: Path, record: dict[str, Any]) -> None:
    """Write the complete run record and separately browseable artifacts."""
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "run.json": record,
        "request.json": record.get("request", {}),
        "itinerary.json": record.get("itinerary"),
        "repair_history.json": record.get("repair_history", []),
        "attempts.json": record.get("attempts", []),
    }
    for filename, value in artifacts.items():
        if value is None:
            continue
        path = run_dir / filename
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, default=_json_default) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
