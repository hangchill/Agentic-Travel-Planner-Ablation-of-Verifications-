"""Build offline regression CSVs from records (JSONL) or shared histories (JSON)."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chinatravel.evaluation.constraint_families import CONSTRAINT_FAMILIES
from chinatravel.evaluation.regression_matrix import (
    AGGREGATE_COLUMNS, CONTRIBUTION_COLUMNS, build_regression_matrix,
)


def load_input(path, run_id=None):
    path = Path(path)
    default_run = run_id or "file-" + hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
    if path.suffix.lower() == ".jsonl":
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
            records.append({"run_id": default_run, "repair_attempt": item})
        else:
            raise ValueError(f"{path}: proposal lacks a formal repair_attempt record")
    return records


def _write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", help="Override run identity for every supplied input")
    parser.add_argument("--repair-strategy", help="Filter by exact recorded strategy name")
    args = parser.parse_args(argv)
    records = [record for path in args.input for record in load_input(path, args.run_id)]
    if args.repair_strategy:
        records = [item for item in records
                   if item["repair_attempt"].get("repair_strategy") == args.repair_strategy]
    analysis = build_regression_matrix(records)
    strategies = {row["repair_strategy"] for row in analysis["aggregate"]}
    if len(strategies) > 1:
        parser.error("Pivot CSVs require one strategy; select --repair-strategy to avoid pooling methods")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_dir / "matrix_contributions.csv", analysis["contributions"], CONTRIBUTION_COLUMNS)
    _write_csv(args.output_dir / "regression_matrix_long.csv", analysis["aggregate"], AGGREGATE_COLUMNS)
    for perspective, filename in (("candidate", "regression_matrix_candidate.csv"),
                                  ("accepted_trajectory", "regression_matrix_accepted.csv")):
        lookup = {(row["source_family"], row["destination_family"]): row["regression_rate"]
                  for row in analysis["aggregate"] if row["perspective"] == perspective}
        rows = [{"source_family": source,
                 **{destination: lookup.get((source, destination)) for destination in CONSTRAINT_FAMILIES}}
                for source in CONSTRAINT_FAMILIES]
        _write_csv(args.output_dir / filename, rows, ("source_family", *CONSTRAINT_FAMILIES))
    with (args.output_dir / "matrix_coverage.json").open("w", encoding="utf-8") as stream:
        json.dump(analysis["coverage"], stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
