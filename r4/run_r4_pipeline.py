"""Run R4, offline benchmark evaluation, summaries and per-trial matrices."""

import argparse
import json
import subprocess
import sys

try:
    from .run_r4 import PROJECT_ROOT, add_run_arguments, execute
except ImportError:
    from run_r4 import PROJECT_ROOT, add_run_arguments, execute


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_arguments(parser)
    args = parser.parse_args(argv)
    run_dir = execute(args)
    if run_dir is None:
        return
    subprocess.run([
        sys.executable, "-X", "utf8", str(PROJECT_ROOT / "scripts/result_analysis/evaluate_repair_run.py"),
        "--run-dir", str(run_dir),
    ], cwd=PROJECT_ROOT, check=True)
    subprocess.run([
        sys.executable, "-X", "utf8", str(PROJECT_ROOT / "scripts/result_analysis/build_repair_summary.py"),
        "--input", str(run_dir),
    ], cwd=PROJECT_ROOT, check=True)
    metadata = json.loads((run_dir / "r4_run_metadata.json").read_text(encoding="utf-8"))
    for name in metadata["repair_budgets"]:
        subprocess.run([
            sys.executable, "-X", "utf8", str(PROJECT_ROOT / "scripts/matrix_building/build_regression_matrix.py"),
            "--input", str(run_dir / "attempts.jsonl"), "--repair-strategy", name,
            "--output-dir", str(PROJECT_ROOT / "matrices" / run_dir.name / name),
        ], cwd=PROJECT_ROOT, check=True)
    print(f"Completed R4 pipeline: {run_dir}")
    print("Best selected plans and costs: r4_selection_and_costs.json")


if __name__ == "__main__":
    main()
