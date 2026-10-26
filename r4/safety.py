"""Train-only evidence and pilot budget validation; never loads test records."""

import csv
import hashlib
import json
from pathlib import Path

R4_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = R4_ROOT.parent
LABELS = ("R0", "R1", "R2", "R3")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def split_uids(split="subset_train"):
    allowed_splits = ("subset_train", "subset_test", "combined_train", "combined_test",
                      "easy_train", "easy_test", "medium_train", "medium_test",
                      "human_train", "human_test")
    if split not in allowed_splits:
        raise ValueError(f"R4 requires a named train/test split, found {split!r}")
    path = PROJECT_ROOT / "chinatravel/evaluation/default_splits" / (split + ".txt")
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def train_uids(split="subset_train"):
    if not split.endswith("_train"):
        raise ValueError("Matrix evidence must come from a training split")
    return split_uids(split)


def validate_limits(args):
    allowed = split_uids(args.splits)
    if not 1 <= args.query_limit <= len(allowed):
        raise ValueError(f"--query-limit must be between 1 and {len(allowed)} for {args.splits}")
    if not 0 <= args.max_steps <= 6:
        raise ValueError("R4 permits at most 6 repairs per query across all matrix trials")
    minimum = 3 if getattr(args, "allow_missing_r1", False) else 4
    if args.mode == "individual" and args.max_steps < minimum:
        raise ValueError(f"Individual mode needs at least {minimum} repairs to try all supplied matrices")
    if args.index:
        if len(args.index) > args.query_limit or len(set(args.index)) != len(args.index):
            raise ValueError("Query IDs must be unique and within --query-limit")
        if not set(args.index) <= allowed:
            raise ValueError("Requested query IDs are outside the selected split")
    return allowed


def labeled_paths(values, *, allow_missing_r1=False):
    paths = {}
    for value in values:
        label, separator, raw_path = value.partition("=")
        if not separator or label not in LABELS or label in paths or not raw_path:
            raise ValueError("Supply unique R0=PATH, R1=PATH, R2=PATH and R3=PATH inputs")
        paths[label] = Path(raw_path).resolve()
    expected = set(LABELS) - ({"R1"} if allow_missing_r1 and "R1" not in paths else set())
    if set(paths) != expected:
        raise ValueError("Exactly four inputs are required: R0, R1, R2, R3 (R3P is distinct)")
    return {label: paths[label] for label in LABELS if label in paths}


def validate_matrix_dir(directory, allowed, expected_label=None):
    root = Path(directory).resolve()
    if (root / "regression_matrix").is_dir():
        root = root / "regression_matrix"
    path = root / "matrix_contributions.csv"
    if not path.is_file():
        raise ValueError(f"{directory}: missing matrix_contributions.csv training provenance")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    uids = {row.get("query_uid") for row in rows}
    labels = {row.get("repair_strategy") for row in rows}
    if not rows or not uids <= allowed:
        raise ValueError(f"{directory}: matrix evidence is empty, missing UIDs or outside the training split")
    if len(labels) != 1 or not labels <= set(LABELS):
        raise ValueError(f"{directory}: expected one of R0-R3, found {sorted(labels)}")
    label = next(iter(labels))
    if expected_label is not None and label != expected_label:
        raise ValueError(f"{directory}: expected {expected_label}, found {label}")
    return label, sorted(uids)


def validate_final_matrix(
    path, allowed, *, allow_missing_r1=False, allow_synthetic_fixture=False,
):
    path = Path(path).resolve()
    manifest_path = path.with_name("main_matrix_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("output_sha256") != sha256(path):
        raise ValueError("Final matrix hash does not match its manifest")
    sources = manifest.get("input_matrices", [])
    if manifest.get("fixture_type") == "synthetic_test_fixture":
        if not allow_synthetic_fixture:
            raise ValueError("Synthetic test matrix requires --allow-synthetic-matrix")
        if sources or manifest.get("input_matrix_count") != 0:
            raise ValueError("Synthetic test matrix must not claim empirical inputs")
        return manifest
    if len(sources) not in ((3, 4) if allow_missing_r1 else (4,)):
        raise ValueError("Combined mode requires a final matrix pooled from exactly R0-R3")
    labels = []
    for source in sources:
        root = Path(source["directory"])
        label, _ = validate_matrix_dir(root, allowed)
        labels.append(label)
        for kind in ("count", "support", "rate"):
            pivot = root / f"{manifest['perspective']}_regression_{kind}.csv"
            if sha256(pivot) != source[f"{kind}_sha256"]:
                raise ValueError(f"Matrix input changed: {pivot}")
        if source.get("contributions_sha256") != sha256(root / "matrix_contributions.csv"):
            raise ValueError(f"Matrix provenance changed or is unverified: {root}")
        history_evidence = source.get("commonsense_destination_evidence", {})
        history_inputs = list(history_evidence.get("history_files", []))
        if history_evidence.get("run_manifest"):
            history_inputs.append(history_evidence["run_manifest"])
        for history_input in history_inputs:
            history_path = Path(history_input["path"])
            if not history_path.is_file() or sha256(history_path) != history_input["sha256"]:
                raise ValueError(f"Commonsense history provenance changed: {history_path}")
    expected = [label for label in LABELS if label != "R1"] if len(sources) == 3 else list(LABELS)
    if sorted(labels) != expected:
        raise ValueError("Combined matrix must contain one matrix from each of R0-R3")
    return manifest
