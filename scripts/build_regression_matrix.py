"""Build offline regression CSVs from records (JSONL) or shared histories (JSON)."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chinatravel.evaluation.train_test_split import load_manifest, filter_attempts
from chinatravel.evaluation.constraint_families import CONSTRAINT_FAMILIES
from chinatravel.evaluation.regression_matrix import (
    AGGREGATE_COLUMNS, CONTRIBUTION_COLUMNS, SCOPE_AGGREGATE_COLUMNS, build_regression_matrix,
)


def load_input(path, run_id=None):
    path = Path(path)
    default_run = run_id or "file-" + hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
    if path.suffix.lower() == ".csv":
        string_fields = {"query_uid", "repair_strategy", "exception", "target_provenance", "editable_scope",
                         "escalation_reason", "decision_reason", "repair_phase", "run_id", "matrix_run_id"}
        with path.open(encoding="utf-8", newline="") as stream:
            items = []
            for row in csv.DictReader(stream):
                item = {}
                for key, value in row.items():
                    if value == "":
                        item[key] = None
                    elif key in string_fields:
                        item[key] = value
                    else:
                        try:
                            item[key] = json.loads(value)
                        except (ValueError, TypeError) as exc:
                            raise ValueError(f"{path}: CSV field {key!r} requires JSON encoding") from exc
                items.append(item)
    elif path.suffix.lower() == ".jsonl":
        with path.open(encoding="utf-8") as stream:
            items = [json.loads(line) for line in stream if line.strip()]
    else:
        with path.open(encoding="utf-8") as stream:
            payload = json.load(stream)
        if isinstance(payload, dict) and "history" in payload:
            default_run = run_id or payload.get("run_id", default_run)
            payload = payload["history"]
        items = payload if isinstance(payload, list) else [payload]
    records = []
    for item in items:
        if isinstance(item, dict) and item.get("step") == 0 and "verification" in item:
            continue
        if not isinstance(item, dict):
            raise ValueError(f"{path}: expected record dictionaries")
        if "repair_attempt" in item:
            records.append({"run_id": run_id or item.get("run_id", default_run),
                            "repair_attempt": item["repair_attempt"]})
        elif "before_personal_constraints" in item:
            # Paired-runner flat streams carry invocation and strategy-run identity.
            payload = {key: value for key, value in item.items() if key not in ("run_id", "matrix_run_id")}
            records.append({"run_id": run_id or item.get("matrix_run_id", item.get("run_id", default_run)),
                            "repair_attempt": payload})
        else:
            raise ValueError(f"{path}: proposal lacks a formal repair_attempt record")
    return records


def _write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_pivots(directory, aggregate, *, legacy=False):
    for perspective, prefix in (("candidate", "candidate"), ("accepted_trajectory", "accepted")):
        lookup = {(row["source_family"], row["destination_family"]): row
                  for row in aggregate if row["perspective"] == perspective}
        for metric, field in (("rate", "regression_rate"), ("support", "support_count"),
                              ("count", "regression_count")):
            rows = [{"source_family": source, **{
                destination: lookup.get((source, destination), {}).get(field, None if metric == "rate" else 0)
                for destination in CONSTRAINT_FAMILIES}} for source in CONSTRAINT_FAMILIES]
            _write_csv(directory / f"{prefix}_regression_{metric}.csv", rows,
                       ("source_family", *CONSTRAINT_FAMILIES))
            if legacy and metric == "rate":
                _write_csv(directory / f"regression_matrix_{prefix}.csv", rows,
                           ("source_family", *CONSTRAINT_FAMILIES))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", help="Override run identity for every supplied input")
    parser.add_argument("--repair-strategy", help="Filter by exact recorded strategy name")
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--partition", choices=("train", "test"))
    args = parser.parse_args(argv)
    if bool(args.split_manifest) != bool(args.partition):
        parser.error("--split-manifest and --partition must be supplied together")
    records = [record for path in args.input for record in load_input(path, args.run_id)]
    if args.split_manifest:
        records = filter_attempts(records, load_manifest(args.split_manifest), args.partition)
    if args.repair_strategy:
        records = [item for item in records
                   if item["repair_attempt"].get("repair_strategy") == args.repair_strategy]
    analysis = build_regression_matrix(records)
    if args.split_manifest:
        analysis["coverage"]["split_selection"] = {"partition": args.partition, "manifest_sha256": hashlib.sha256(args.split_manifest.read_bytes()).hexdigest()}
    strategies = {row["repair_strategy"] for row in analysis["aggregate"]}
    if len(strategies) > 1:
        parser.error("Pivot CSVs require one strategy; select --repair-strategy to avoid pooling methods")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_dir / "matrix_contributions.csv", analysis["contributions"], CONTRIBUTION_COLUMNS)
    _write_csv(args.output_dir / "regression_matrix_long.csv", analysis["aggregate"], AGGREGATE_COLUMNS)
    _write_csv(args.output_dir / "regression_matrix_by_scope_long.csv",
               analysis["aggregate_by_scope"], SCOPE_AGGREGATE_COLUMNS)
    _write_pivots(args.output_dir, analysis["aggregate"], legacy=True)
    scopes = {row["editable_scope"] for row in analysis["aggregate_by_scope"]}
    for scope in sorted(scopes, key=lambda value: value or ""):
        scoped_dir = args.output_dir / "by_scope" / (scope or "unspecified")
        scoped_dir.mkdir(parents=True, exist_ok=True)
        _write_pivots(scoped_dir, [row for row in analysis["aggregate_by_scope"]
                                   if row["editable_scope"] == scope])
    with (args.output_dir / "matrix_coverage.json").open("w", encoding="utf-8") as stream:
        json.dump(analysis["coverage"], stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
