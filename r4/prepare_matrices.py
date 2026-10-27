"""Filter R0-R3 histories to train UIDs, then use the official matrix builder."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

R4_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = R4_ROOT.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
for root in (WORKSPACE_ROOT, PROJECT_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from r4.safety import LABELS, PROJECT_ROOT, labeled_paths, sha256, train_uids
from scripts.matrix_building.build_regression_matrix import load_input


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", action="append", required=True, metavar="R0=PATH")
    parser.add_argument("--splits", default="subset_train")
    parser.add_argument("--allow-missing-r1", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "matrices" / "training_matrices")
    args = parser.parse_args(argv)
    allowed = train_uids(args.splits)
    inputs = labeled_paths(args.attempts, allow_missing_r1=args.allow_missing_r1)
    # Validate every source before writing any matrix. Unknown or nontraining
    # UIDs are excluded explicitly, with counts retained in the provenance file.
    filtered = {}
    for label in inputs:
        records = load_input(inputs[label])
        if any(item["repair_attempt"].get("repair_strategy") != label for item in records):
            raise ValueError(f"{inputs[label]} contains strategy records other than {label}")
        selected = [item for item in records if item["repair_attempt"].get("query_uid") in allowed]
        if not selected:
            raise ValueError(f"{label}: no attempts belong to {args.splits}; provide training histories")
        filtered[label] = (records, selected)
    if args.output_dir.exists():
        raise ValueError("Output directory already exists; choose a new --output-dir")
    for label, (records, selected) in filtered.items():
        directory = args.output_dir.resolve() / label
        directory.mkdir(parents=True)
        attempts_path = directory / "train_attempts.jsonl"
        attempts_path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in selected), encoding="utf-8")
        subprocess.run([
            sys.executable, "-X", "utf8", str(PROJECT_ROOT / "scripts/matrix_building/build_regression_matrix.py"),
            "--input", str(attempts_path), "--repair-strategy", label,
            "--output-dir", str(directory),
        ], cwd=PROJECT_ROOT, check=True)
        provenance = {
            "split": args.splits, "source_path": str(inputs[label]), "source_sha256": sha256(inputs[label]),
            "kept_training_attempts": len(selected), "excluded_nontraining_or_missing_uid_attempts": len(records) - len(selected),
            "training_query_uids": sorted({item["repair_attempt"]["query_uid"] for item in selected}),
        }
        (directory / "training_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        print(f"{label}={directory}")


if __name__ == "__main__":
    main()
