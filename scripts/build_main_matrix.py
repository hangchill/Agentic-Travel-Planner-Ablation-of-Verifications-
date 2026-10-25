"""Validate four training-only R0-R3 matrices and pool their counts/support."""

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from r4.build_main_matrix import build_main_matrix
from r4.safety import LABELS, train_uids, validate_matrix_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", action="append", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "matrices/pooled/main_matrix.csv")
    parser.add_argument("--splits", default="subset_train")
    parser.add_argument("--perspective", choices=("candidate", "accepted"), default="candidate")
    args = parser.parse_args(argv)
    allowed = train_uids(args.splits)
    labels = [validate_matrix_dir(path, allowed)[0] for path in args.input_dir]
    if sorted(labels) != list(LABELS):
        parser.error("Supply exactly one matrix directory from each of R0, R1, R2 and R3")
    _, manifest = build_main_matrix(args.input_dir, args.output, perspective=args.perspective)
    print(f"Matrix: {args.output.resolve()} ({manifest['status']})")


if __name__ == "__main__":
    main()
