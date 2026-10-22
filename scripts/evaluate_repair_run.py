"""Explicit offline ChinaTravel benchmark stage for saved repair evidence."""
import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chinatravel.evaluation.export_final_plans import evaluate_repair_run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--preference', action='store_true')
    args = parser.parse_args(argv)
    evaluate_repair_run(args.run_dir, preference=args.preference)


if __name__ == '__main__':
    main()
