"""Explicit offline ChinaTravel benchmark stage for saved repair evidence."""
import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from chinatravel.evaluation.export_final_plans import evaluate_repair_run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--preference', action='store_true')
    parser.add_argument('--include-trials', action='store_true',
                        help='Also export final accepted R4 trial scores under benchmark_eval/trials')
    args = parser.parse_args(argv)
    # R0-R4 share the same endpoint policy: score final_verification from each
    # authoritative checkpoint, never the best outcome selected from history.
    results = evaluate_repair_run(args.run_dir, preference=args.preference)
    if args.include_trials and (args.run_dir / 'r4_run_metadata.json').is_file():
        evaluate_repair_run(args.run_dir, preference=args.preference, trial_diagnostics=True)
    return results


if __name__ == '__main__':
    main()
