"""Pool R0-R3 regression evidence into the R4 guidance matrix."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from chinatravel.evaluation.constraint_families import CONSTRAINT_FAMILIES
from r4.commonsense_evidence import COMMONSENSE_FAMILY, history_evidence

STRATEGIES = ("R0", "R1", "R2", "R3")
SOURCE_FAMILIES = (*CONSTRAINT_FAMILIES, COMMONSENSE_FAMILY)
DESTINATION_FAMILIES = SOURCE_FAMILIES


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _input_root(directory):
    root = Path(directory).resolve()
    return root / "regression_matrix" if (root / "regression_matrix").is_dir() else root


def _read_pivot(path, *, allow_commonsense):
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        expected_columns = {"source_family", *CONSTRAINT_FAMILIES}
        if reader.fieldnames is None or not expected_columns.issubset(reader.fieldnames):
            raise ValueError(f"{path}: missing expected source/destination columns")
        rows = {}
        for row in reader:
            source = row["source_family"]
            allowed = SOURCE_FAMILIES if allow_commonsense else CONSTRAINT_FAMILIES
            if source not in allowed or source in rows:
                raise ValueError(f"{path}: unexpected or duplicate source family {source!r}")
            rows[source] = row
    required = set(SOURCE_FAMILIES if allow_commonsense else CONSTRAINT_FAMILIES)
    if set(rows) != required:
        raise ValueError(f"{path}: expected source rows {sorted(required)}, found {sorted(rows)}")
    return rows


def _integer(value, path, cell):
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: {cell} must be a nonnegative integer") from exc
    if result < 0 or str(result) != str(value).strip():
        raise ValueError(f"{path}: {cell} must be a nonnegative integer")
    return result


def build_main_matrix(matrix_dirs, output_csv, *, perspective="candidate"):
    """Pool personal pivots and recover commonsense destinations from histories.

    Missing history evidence remains unavailable. Commonsense probabilities use
    only eligible observed transitions, with strategy coverage in the manifest.
    """
    if perspective not in ("candidate", "accepted"):
        raise ValueError("perspective must be candidate or accepted")
    if len(matrix_dirs) not in (1, 4):
        raise ValueError("Supply either one strategy matrix or all four inputs: R0, R1, R2 and R3")

    totals = {(s, d): {"regression_count": 0, "support_count": 0, "query_uids": set(),
                       "by_strategy": {label: {"regression_count": 0, "support_count": 0} for label in STRATEGIES}}
              for s in SOURCE_FAMILIES for d in DESTINATION_FAMILIES}
    for source in CONSTRAINT_FAMILIES:
        totals[(source, COMMONSENSE_FAMILY)]["by_strategy"] = {
            label: {"regression_count": None, "support_count": None} for label in STRATEGIES}
    manifests = []
    found_strategies = []
    for directory in matrix_dirs:
        root = _input_root(directory)
        files = {kind: root / f"{perspective}_regression_{kind}.csv"
                 for kind in ("count", "support", "rate")}
        for kind, path in files.items():
            if not path.is_file():
                raise FileNotFoundError(f"Missing {kind} pivot: {path}")
        tables = {kind: _read_pivot(path, allow_commonsense=True) for kind, path in files.items()}
        contribution_path = root / "matrix_contributions.csv"
        if not contribution_path.is_file():
            raise FileNotFoundError(f"Missing attempt-level provenance: {contribution_path}")
        contribution_uids = {(s, d): set() for s in SOURCE_FAMILIES for d in DESTINATION_FAMILIES}
        contribution_ids = set()
        labels = set()
        with contribution_path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("perspective") != ("candidate" if perspective == "candidate" else "accepted_trajectory"):
                    continue
                label, source, dest = row.get("repair_strategy"), row.get("source_family"), row.get("destination_family")
                if label in STRATEGIES:
                    labels.add(label)
                if row.get("run_id") and row.get("query_uid") and row.get("step"):
                    contribution_ids.add((row["run_id"], row["query_uid"], int(row["step"])))
                if source in SOURCE_FAMILIES and dest in DESTINATION_FAMILIES and row.get("eligible", "").lower() == "true":
                    if row.get("query_uid"):
                        contribution_uids[(source, dest)].add(row["query_uid"])
        if len(labels) != 1:
            raise ValueError(f"{contribution_path}: expected one strategy label, got {sorted(labels)}")
        strategy = next(iter(labels))
        if strategy in found_strategies:
            raise ValueError(f"Duplicate source strategy {strategy}")
        found_strategies.append(strategy)
        for source in SOURCE_FAMILIES:
            for destination in CONSTRAINT_FAMILIES:
                cell = (source, destination)
                count = _integer(tables["count"][source][destination], files["count"], cell)
                support = _integer(tables["support"][source][destination], files["support"], cell)
                rate = tables["rate"][source][destination]
                is_diag = source == destination
                if is_diag and source in CONSTRAINT_FAMILIES:
                    if count or support or rate not in ("", None):
                        raise ValueError(f"{root}: diagonal must be blank/zero for {cell}")
                elif count > support:
                    raise ValueError(f"{root}: regressions exceed eligible support for {cell}")
                elif support == 0 and rate not in ("", None):
                    raise ValueError(f"{root}: unsupported cell has a rate for {cell}")
                elif support and (not math.isfinite(float(rate)) or abs(float(rate) - count / support) > 1e-9):
                    raise ValueError(f"{root}: rate does not equal count/support for {cell}")
                target = totals[cell]
                target["regression_count"] += count
                target["support_count"] += support
                target["query_uids"].update(contribution_uids[cell])
                target["by_strategy"][strategy] = {"regression_count": count, "support_count": support}
        history_cells, history_summary = history_evidence(
            root, strategy, contribution_ids, perspective=perspective)
        if history_cells is not None:
            for source, cell in history_cells.items():
                target = totals[(source, COMMONSENSE_FAMILY)]
                target["regression_count"] += cell["regression_count"]
                target["support_count"] += cell["support_count"]
                target["query_uids"].update(cell["query_uids"])
                target["by_strategy"][strategy] = {
                    key: cell[key] for key in ("regression_count", "support_count")}
        manifests.append({"directory": str(root), "strategy": strategy,
                          **{f"{kind}_sha256": sha256(path) for kind, path in files.items()},
                          "contributions_sha256": sha256(contribution_path),
                          "commonsense_destination_evidence": history_summary})
    if len(matrix_dirs) == 4 and set(found_strategies) != set(STRATEGIES):
        raise ValueError(f"Expected one input each for R0-R3; found {sorted(found_strategies)}")

    rows = []
    available_histories = [item["strategy"] for item in manifests
                          if item["commonsense_destination_evidence"]["status"] != "unavailable"]
    incomplete_histories = any(item["commonsense_destination_evidence"]["status"] != "available"
                               for item in manifests)
    for source in SOURCE_FAMILIES:
        for destination in DESTINATION_FAMILIES:
            item = totals[(source, destination)]
            count, support = item["regression_count"], item["support_count"]
            diagonal = source == destination
            rate = "" if diagonal or support == 0 else format(count / support, ".12g")
            status = "structural_diagonal" if diagonal else ("observed" if support else "unobserved")
            query_count = len(item["query_uids"])
            if destination == COMMONSENSE_FAMILY and not diagonal:
                if not available_histories:
                    count = support = query_count = None
                    status = "unavailable"
                elif support and incomplete_histories:
                    status = "observed_partial"
            row = {"source_family": source, "destination_family": destination,
                   "regression_count": count, "support_count": support,
                   "support_query_count": query_count,
                   "regression_probability": rate, "evidence_status": status}
            for label in STRATEGIES:
                row[f"{label}_regression_count"] = item["by_strategy"][label]["regression_count"]
                row[f"{label}_support_count"] = item["by_strategy"][label]["support_count"]
            rows.append(row)

    output = Path(output_csv).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    pivot_path = output.with_name(output.stem + "_probabilities.csv")
    probabilities = {(row["source_family"], row["destination_family"]): row for row in rows}
    with pivot_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["source_family", *DESTINATION_FAMILIES])
        writer.writeheader()
        for source in SOURCE_FAMILIES:
            writer.writerow({"source_family": source, **{
                destination: ("not_applicable" if source == destination else
                              probabilities[(source, destination)]["regression_probability"] or "unavailable")
                for destination in DESTINATION_FAMILIES}})
    personal_cells = [totals[(s, d)] for s in CONSTRAINT_FAMILIES for d in CONSTRAINT_FAMILIES if s != d]
    commonsense_cells = [totals[(COMMONSENSE_FAMILY, d)] for d in CONSTRAINT_FAMILIES]
    destination_cells = [totals[(s, COMMONSENSE_FAMILY)] for s in CONSTRAINT_FAMILIES]
    manifest = {
        "matrix_type": "directional_constraint_regression_risk_with_commonsense_source_and_destination",
        "perspective": perspective, "source_families": list(SOURCE_FAMILIES),
        "destination_families": list(DESTINATION_FAMILIES),
        "aggregation": "pool regression counts and eligible attempt support across R0-R3, then divide",
        "input_matrices": manifests, "input_matrix_count": len(manifests),
        "cell_summary": {"personal_off_diagonal_supported": sum(x["support_count"] > 0 for x in personal_cells),
                         "personal_off_diagonal_cells": len(personal_cells),
                         "commonsense_source_supported": sum(x["support_count"] > 0 for x in commonsense_cells),
                         "commonsense_source_cells": len(commonsense_cells),
                         "commonsense_destination_supported": sum(x["support_count"] > 0 for x in destination_cells),
                         "commonsense_destination_cells": len(destination_cells)},
        "unobserved_cell_policy": {"probability_in_csv": None, "r4_neutral_fallback_probability": 0.5},
        "commonsense_destination_note": (
            "Only complete saved training verifications contribute. The before state follows accepted history; "
            "eligible changed repairs have one explicit mapped failing personal target and commonsense PASS before. "
            "A recorded commonsense FAIL afterward is a regression. No-ops, unknown verifications, "
            "already-failing destinations and the structural diagonal are excluded. "
            "Missing per-strategy counts/support remain blank, never inferred as zero."),
        "commonsense_destination_available_strategies": available_histories,
        "commonsense_destination_unavailable_strategies": [
            item["strategy"] for item in manifests if item["strategy"] not in available_histories],
        "probability_pivot": {"file": pivot_path.name, "sha256": sha256(pivot_path),
                              "unavailable_value": "unavailable", "diagonal_value": "not_applicable"},
        "output_sha256": sha256(output),
    }
    output.with_name("main_matrix_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return rows, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", action="append", required=True, help="R0-R3 run folder or its regression_matrix folder")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "matrices" / "pooled" / "main_matrix.csv")
    parser.add_argument("--perspective", choices=("candidate", "accepted"), default="candidate")
    args = parser.parse_args(argv)
    rows, manifest = build_main_matrix(args.input_dir, args.output, perspective=args.perspective)
    print(f"Matrix: {args.output.resolve()} ({manifest['perspective']})")
    print(f"Probability grid: {args.output.resolve().with_name(manifest['probability_pivot']['file'])}")
    print(json.dumps(manifest["cell_summary"], indent=2))


if __name__ == "__main__":
    main()
