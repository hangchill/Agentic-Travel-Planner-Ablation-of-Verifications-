"""Rebuild every table and figure behind docs/report/overleaf/evaluation_and_results.tex.

Steps (each a separate script):
  1. load_runs.py                    experiments/ + read-only summary folders -> data/{rounds,queries,constraints}.csv
  2. failure_repair.py               initial and final benchmark rescoring of R0 to R4 -> tables/t14_failure_repair.csv
     plots/r1_vs_r3_scope_effect.py  per-round benchmark rescoring of R1 and R3 -> figures/fig6_r1_vs_r3_scope_effect.png
                                     (both run in the project environment through `uv run`, because the benchmark
                                     commonsense checker imports geopy; skipped with a warning if that fails)
  3. build_report_tables.py          data/*.csv (+ t14 for T16) -> tables/t*.csv, tables/REPORT_TABLES.md
  4. plots/difficulty_test.py        figures/fig2_change_by_difficulty.png, figures/fig4_difficulty_with_cost.png
     plots/difficulty_train.py       figures/fig5_train_difficulty.png
     make_figures.py                 figures/fig1_*.png, figures/fig3_*.png and figures/manifest_figures.csv
  5. merge the manifests into MANIFEST.csv

Needs Python 3.10+ with pandas, numpy and matplotlib, and uv for step 2. No model calls.
Writes only inside report_result_evaluations/.

Usage:  python report_result_evaluations/run_all.py [--skip-figures] [--skip-rescore]
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


def run(script, *extra):
    cmd = [sys.executable, str(HERE / script), *extra]
    print(">>", " ".join(cmd))
    subprocess.run(cmd, check=True)


def run_in_project_env(script, output):
    """Benchmark rescoring needs the project environment (the commonsense checker imports geopy)."""
    uv = shutil.which("uv")
    keep = f"kept the existing {output}"
    if uv is None:
        print("!! uv not found:", keep)
        return
    cmd = [uv, "run", "--no-sync", "--with", "matplotlib", "python", str(HERE / script)]
    print(">>", " ".join(cmd))
    if subprocess.run(cmd, cwd=HERE.parent).returncode != 0:
        print(f"!! {script} failed:", keep)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-figures", action="store_true", help="do not redraw the figures (keep the saved PNGs)")
    ap.add_argument("--skip-rescore", action="store_true",
                    help="do not rescore plans with the benchmark (Table T14 and fig6 keep their saved files)")
    args = ap.parse_args()
    run("load_runs.py")
    if not args.skip_rescore:  # before the tables: T16 reads tables/t14_failure_repair.csv
        run_in_project_env("failure_repair.py", "tables/t14_failure_repair.csv")
        if not args.skip_figures:
            run_in_project_env("plots/r1_vs_r3_scope_effect.py", "figures/fig6_r1_vs_r3_scope_effect.png")
    run("build_report_tables.py")
    if not args.skip_figures:
        run("plots/difficulty_test.py")
        run("plots/difficulty_train.py")
        run("make_figures.py")
    parts = [pd.read_csv(HERE / "tables" / "manifest_tables.csv")]
    for extra in (HERE / "tables" / "manifest_failure.csv", HERE / "figures" / "manifest_figures.csv"):
        if extra.exists():
            parts.append(pd.read_csv(extra))
    manifest = pd.concat(parts, ignore_index=True)
    manifest.to_csv(HERE / "MANIFEST.csv", index=False)
    print("wrote", HERE / "MANIFEST.csv")
    print(manifest[["report_id", "kind", "path", "has_ci"]].to_string(index=False))


if __name__ == "__main__":
    main()
