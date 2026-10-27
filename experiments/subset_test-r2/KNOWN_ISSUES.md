# Known issues: subset_test-r2

## Two queries stopped repair early because the loop verifier crashed

Found 2026-10-26. **Not fixed**: the code and this run's data are unchanged.

| Query | Group | Rounds used | Saved stop reason | Correct stop reason | Tokens spent | Repair time |
|---|---|---|---|---|---|---|
| `m20241028164626006100` | easy | 1 of 6 | `repair_budget_exhausted` | stopped by a verifier crash, 5 rounds unused | 39,713 | 24.4 s |
| `t20241206171855902412` | easy | 4 of 6 | `repair_budget_exhausted` | stopped by a verifier crash, 2 rounds unused | 140,255 | 97.3 s |

### What happened

1. **The plan had a real timing error.** In each final plan, the return train or flight leaves before the plan's inner-city transport reaches the station:
   - `m20241028164626006100`, day 2: the train leaves Chengdu East at 15:00, but the metro arrives at 15:54.
   - `t20241206171855902412`, day 2: the flight leaves Shenzhen Bao'an at 16:34, but the transport arrives at 16:48.
2. **The loop's time check found it, then crashed.** `collect_time_error` in `chinatravel/agent/nesy_verifier/verifier/commonsense_constraint_nl.py` (line 793) builds its message from `activity_i['position']`. Train and flight activities have `start` / `end` instead, so it raised `KeyError: 'position'`. The saved verification shows:
   ```
   verifier_errors: ["Raise error in symoblic commonsense feedback, <function collect_time_error ...>: 'position'"]
   ```
3. **The crash was filed as a technical error.** `shared_verifier.py` keeps verifier crashes out of `commonsense_errors`. The plan therefore showed every personal constraint passing and 0 commonsense errors, but `passed = False`.
4. **The loop stopped early.** `run_repair_loop` (`chinatravel/agent/nesy_verifier/shared_repair_loop.py`, lines 233–235) stops when every personal constraint passes and no commonsense errors remain ("nothing left to fix"). It stopped with rounds unused, and the model was never told about the missed train or flight.
5. **The stop reason was saved wrongly.** `chinatravel/evaluation/repair_comparison.py` (line 320) labels every finish that didn't pass as `repair_budget_exhausted`, even when budget is left.

### Which results are wrong or biased

| Result | Effect |
|---|---|
| `stop_reason` in `queries/<uid>/R2-*.json` and `summaries.csv` | Wrong for these two queries: saved as `repair_budget_exhausted`, but the budget wasn't used up |
| Rounds (`repair_attempt_count`), tokens, repair time | Too low for these two queries: 5 + 2 rounds were never run. Easy R2 has 53 rounds instead of 60, and its per-query round, token and time averages are lower than they would be |
| Unchanged / changed rounds, cache hits, `phase_outcomes.csv` | These queries count only the rounds that ran |
| Personal-constraint and commonsense outcomes | These two plans may have improved with the missing rounds; R2's easy-group repair result is understated by an unknown amount |
| Benchmark scores (`benchmark_eval/`) | Correct: the benchmark doesn't have this crash and fails both plans on "Does not follow Chronological Order" |

When comparing R2 with other runs, footnote these two queries, or leave them out of round, token and time comparisons. `test_result_analysis/README.md` flags them automatically.

### Same crash in other queries of this run

The crash hides every timing error in the plan it occurs on, not only the one that caused it. In this run it occurred in 17 verifications across 6 queries. The other 4 continued repairing only because they still had other errors to fix.

| Query | Group | Verifications with the crash | Final plan affected |
|---|---|---|---|
| `e20241028160332826857` | easy | 7 of 7 | yes |
| `m20241028164936662445` | easy | 6 of 7 | no |
| `m20241028164626006100` | easy | 1 of 2 | yes (stopped early) |
| `t20241206171855902412` | easy | 1 of 5 | yes (stopped early) |
| `e20241028160902013119` | medium | 1 of 7 | no |
| `e20241028161334777418` | medium | 1 of 7 | yes |

"Verifications" counts the initial plan plus every repair round. The crash also occurs in `subset_test-r3` (6 queries, none stopped early), `subset_train-r0` (14 queries, 3 stopped early) and `subset_train-r2` (9 queries, 1 stopped before its first round).

### Fix (not applied)

- **Stop the crash:** in `collect_time_error`, fall back to the activity's `start` when `position` is missing, so the timing error is reported as a commonsense error.
- **Fix the stop reason:** give the "nothing left to fix" stop its own reason in `repair_comparison.py`.

After the fix, affected runs need repeating to get correct repair metrics.
