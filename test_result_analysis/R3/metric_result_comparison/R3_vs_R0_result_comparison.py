"""Build the compiled R0 vs R3 effectiveness table (All queries) from the merged tables.

Writes <output-dir>/R0vsR3_effectiveness_compiled.csv with the columns
metric, R0, R3, source. It has the same rows as R1_vs_R3_effectiveness_compiled.csv
(see R3_vs_R1_result_comparison.py, which holds the row definitions).

Usage (from the repository root):
  python test_result_analysis/R3/R3_vs_R0_result_comparison.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from R3_vs_R1_result_comparison import main  # noqa: E402

if __name__ == "__main__":
    main(other="R0")
