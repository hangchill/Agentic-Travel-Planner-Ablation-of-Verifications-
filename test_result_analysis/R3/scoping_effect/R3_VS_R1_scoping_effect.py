"""R3 vs R1: effect of widening the edit scope after the slot rounds, by round window.

Aim of the comparison:
  R1 edits only the flagged slots in every round (slot scope in rounds 1-6). R3 also uses
  slot scope in rounds 1-2, then widens to day scope (rounds 3-4) and plan scope (rounds
  5-6). Thus rounds 1-2 compare two slot-scope strategies, and rounds 3-6 show what R3's
  widening adds over staying at slot scope. This tests the known limit of R1: a constraint
  that the locked slots cannot fix stays unfixed. (R3 vs R0 tests the other side: does the
  narrow start help compared with whole-plan regeneration from round 1?)

  The two strategies are not identical in rounds 1-2: R3 also unlocks bookings (hotel,
  intercity transport) when a failing constraint is about one, and the prompts differ. The
  runs also start from different initial plans, so compare the change rows, not the levels.

Writes to <output-dir> (default test_result_analysis/R3/):
  R3_vs_R1_pc.csv      PC fulfillment: subset, row, Start, After rounds 1-2, 3-4, 5-6
  R3_vs_R1_cs.csv      CS checks, same columns
  R3_vs_R1_effectiveness.csv
                       the effectiveness table: per subset, the PC rows, then the CS rows
                       (same columns; the same rows as the two files above)
  R3_vs_R1_tables.md   both tables as Markdown, with this aim

Rows, subsets, scoring and inputs are the same as in R3_VS_R0_scoping_effect.py (this
script reuses its code; see its docstring for the definitions).

Usage:
  python test_result_analysis/R3/R3_VS_R1_scoping_effect.py
  python test_result_analysis/R3/R3_VS_R1_scoping_effect.py \
      --run R1=experiments/subset_test-r1 --run R3=experiments/subset_test-r3 \
      --output-dir test_result_analysis/R3
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import R3_VS_R0_scoping_effect as shared  # noqa: E402

AIM = ("Aim: show what R3's scope widening adds over staying at slot scope. R1 edits only the flagged "
       "slots in every round; R3 also uses slot scope in rounds 1-2, then widens to day scope "
       "(rounds 3-4) and plan scope (rounds 5-6). Rounds 1-2 compare two slot-scope strategies "
       "(R3 can also unlock bookings, and the prompts differ); rounds 3-6 show the effect of the "
       "widening.")


def main(argv=None):
    shared.main(argv, baseline="R1", aim=AIM, description=__doc__, script=Path(__file__).name)


if __name__ == "__main__":
    main()
