# R4 repair-risk exploration (subset_train R0 + R3)

Offline analysis behind the doc "R4 Repair-Risk Evidence from subset_train" (2026-10-25).
Not committed; nothing here changes the repair code.

| File | What it does | Output |
| --- | --- | --- |
| extract.py | one row per repair round: plans before/after, constraint states, commonsense errors by kind, which plan parts were edited | – |
| approaches.py | A0-A7: current matrix, event matrix, edit->effect, co-failure, fixability, commonsense kind->kind, budget slack, pooling; LOQO skill | run.txt, scoreboard.json |
| stricter.py | strict LOQO (vs column rates) + multivariable edit model | stricter.txt |
| robustness.py | query bootstrap + R0-vs-R3 agreement for the edit effects | robustness.txt |
| r4_artifact.py | fix levers, avoidable damage, prototype risk profile | r4_artifact.txt, r4_risk_profile.json |
| quality_eval.py | held-out AUC for judging candidates + rejection replay | quality_eval.txt |

Data: R0 = experiments/subset_train-r0 on `main` (extract with
`git archive main experiments/subset_train-r0/queries | tar -x -C <dir>` and point `R0` in extract.py at it);
R3 = experiments/subset_train-r3. Run from this folder with the project venv and PYTHONUTF8=1.
