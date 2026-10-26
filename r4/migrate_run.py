"""Consolidate a saved R4 experiment without generation or benchmark calls."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from chinatravel.evaluation.repair_comparison import _component, _load, _save, checkpoint_paths
from r4.select_outcomes import select_outcomes


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence(value):
    """Compare evidence while allowing added provenance and relocated paths."""
    if isinstance(value, list):
        return [_evidence(item) for item in value]
    if isinstance(value, dict):
        result = {key: _evidence(item) for key, item in value.items()
                  if key not in {"matrix", "matrix_used", "risk_matrix_path"}}
        for key in ("metadata", "repair_metadata"):
            if result.get(key) == {}:
                result.pop(key)
        return result
    return value


def migrate_run(run_dir):
    root = Path(run_dir).resolve()
    if not root.is_dir() or (root / ".comparison.lock").exists():
        raise ValueError("Migration requires an existing, unlocked R4 run")
    metadata = _load(root / "r4_run_metadata.json")
    manifest = _load(root / "run_manifest.json")
    if metadata.get("strategy") != "R4":
        raise ValueError("Not an R4 run")
    legacy_inputs = root.with_name(root.name + "-inputs")
    inputs = root / "inputs"
    moves = []
    # Every recursive directory move is preflighted against the explicit run.
    if legacy_inputs.exists():
        if legacy_inputs.resolve().parent != root.parent or inputs.exists():
            raise ValueError("Conflicting or out-of-scope input directory")
        moves.append((legacy_inputs, inputs))
    for path in checkpoint_paths(root):
        destination = path.parent / "trials" / path.name
        if path.parent.name != "trials":
            moves.append((path, destination))
    benchmark = root / "benchmark_eval"
    old_selected = benchmark / "R4_selected"
    if old_selected.exists():
        moves.append((old_selected, benchmark / "selected"))
    for strategy in manifest["repair_strategies_requested"]:
        old = benchmark / _component(strategy)
        if old.exists():
            moves.append((old, root / "diagnostics" / "benchmark_trials" / strategy))
    for source, destination in moves:
        if not destination.resolve().is_relative_to(root):
            raise ValueError(f"Destination outside the run: {destination}")
        if source != legacy_inputs and not source.resolve().is_relative_to(root):
            raise ValueError(f"Source outside the run: {source}")
        if destination.exists():
            raise ValueError(f"Migration destination already exists: {destination}")
    if (inputs / "combined").exists() and (inputs / "pooled").exists():
        raise ValueError("Conflicting pooled matrix snapshots")

    initial_hashes = {path.relative_to(root).as_posix(): _digest(path)
                      for path in (root / "queries").glob("*/initial_state.json")}
    reference_hashes = {path.relative_to(root).as_posix(): _digest(path)
                       for path in (root / "queries").glob("*/reference/query.json")}
    trial_evidence = {_load(path)["query_uid"] + "/" + _load(path)["repair_strategy"]: _evidence(_load(path))
                      for path in checkpoint_paths(root)}
    old_selections = _load(root / "r4_selection_and_costs.json")
    score_hashes = {path.relative_to(benchmark).as_posix(): _digest(path)
                    for path in benchmark.rglob("*") if path.is_file()} if benchmark.exists() else {}

    # Verify the original matrix snapshots before relocating any files.
    for info in metadata["matrices"].values():
        path = Path(info["path"])
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        allowed_roots = (root, legacy_inputs.resolve())
        if not any(path.is_relative_to(parent) for parent in allowed_roots):
            raise ValueError("Matrix snapshot lies outside this run's input directories")
        if _digest(path) != info["sha256"] or _digest(path.with_name("main_matrix_manifest.json")) != info["manifest_sha256"]:
            raise ValueError("Original matrix snapshot hash mismatch")
    for source, destination in moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
    combined = inputs / "combined"
    if combined.exists():
        pooled = inputs / "pooled"
        if pooled.exists() or not combined.resolve().is_relative_to(root):
            raise ValueError("Conflicting pooled matrix snapshot")
        combined.rename(pooled)

    original_metadata = deepcopy(metadata)
    for name, info in metadata["matrices"].items():
        label = name.removeprefix("R4_") if name != "R4" else "pooled"
        info.update(matrix_used=label, path=f"inputs/{label}/main_matrix.csv")
        path = root / info["path"]
        if _digest(path) != info["sha256"] or _digest(path.with_name("main_matrix_manifest.json")) != info["manifest_sha256"]:
            raise ValueError("Relocated matrix snapshot hash mismatch")
    metadata["artifact_layout_version"] = 2
    _save(root / "r4_run_metadata.json", metadata)
    selections = select_outcomes(root, metadata)
    after = {row["query_uid"]: row for row in selections}
    preserved_selection_fields = ("selected_source", "selected_step", "selected_plan", "selected_verification",
                                  "selection_score", "costs", "monetary_cost", "repair_attempt_count_all_trials")
    for before in old_selections:
        for field in preserved_selection_fields:
            if before.get(field) != after[before["query_uid"]].get(field):
                raise ValueError(f"Migration changed {field} for {before['query_uid']}")
    for relative, digest in {**initial_hashes, **reference_hashes}.items():
        if _digest(root / relative) != digest:
            raise ValueError(f"Migration changed immutable evidence: {relative}")
    after_trials = {_load(path)["query_uid"] + "/" + _load(path)["repair_strategy"]: _evidence(_load(path))
                    for path in checkpoint_paths(root)}
    if trial_evidence != after_trials:
        raise ValueError("Migration changed trial evidence")
    for relative, digest in score_hashes.items():
        parts = Path(relative).parts
        if parts[0] == "R4_selected":
            destination = benchmark / "selected" / Path(*parts[1:])
        else:
            label = next((s for s in manifest["repair_strategies_requested"] if _component(s) == parts[0]), None)
            destination = root / "diagnostics" / "benchmark_trials" / label / Path(*parts[1:]) if label else benchmark / relative
        if _digest(destination) != digest:
            raise ValueError(f"Migration changed benchmark evidence: {relative}")

    # Keep historical metadata in the migration record before removing its duplicate file.
    duplicate = inputs / "r4_run_metadata.json"
    report_path = root / "layout_migration.json"
    if not report_path.exists():
        _save(report_path, {
            "artifact_layout_version": 2, "query_count": len(selections),
            "verified": ["initial states", "references", "trial evidence", "selected outputs", "costs",
                         "matrix hashes", "benchmark files"],
            "original_run_metadata": original_metadata,
            "original_input_metadata": _load(duplicate) if duplicate.exists() else None,
            "initial_state_sha256": initial_hashes, "reference_sha256": reference_hashes,
            "original_benchmark_sha256": score_hashes,
        })
    if duplicate.exists():
        duplicate.unlink()
    return {"run_dir": str(root), "query_count": len(selections), "verified": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(migrate_run(args.run_dir), indent=2))


if __name__ == "__main__":
    main()
