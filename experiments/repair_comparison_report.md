# Repair Strategy Results

What the current runs of R0, R2 and R3 show when strategies are compared only on the same queries.
Pass rates are too close to separate the strategies. How they spend their repair rounds differs a lot.

- **Model:** deepseek/deepseek-chat (temperature 0)
- **Sandbox:** English
- **Budget:** 6 repair rounds
- **Data as of:** 25 Oct 2026

## Main findings

| Topic | Finding |
|---|---|
| Pass rate | **No strategy fixes plans reliably.** Final pass rates are 3–10% everywhere. R3 passed 3 of 30 test queries and R2 passed 1, but that gap is not statistically significant (McNemar p = 0.63). On subset_train, R0 passed 4 of 60 and R2 passed 5. |
| Getting stuck | **R0 and R2 spend over half their rounds repeating themselves.** In 54–57% of their rounds the model got exactly the same request again, and about 60% of rounds left the plan unchanged. R3 changes its prompt and editing scope as it goes, so it repeats in only 17% of rounds. |
| Commonsense | **R3 and R0 remove more commonsense errors than R2.** Net, R3 removed 27% of commonsense errors on test, against 10% for R2. On train, R0 removed 33% and R2 removed 8%. |
| Personal | **R2's rollback protects personal constraints, at a price.** R0 kept 17 rounds that broke a personal constraint, R3 kept 3 and R2 kept none. On train, R2 ended with more queries passing all personal constraints than R0: 55% vs 40%, the only significant difference here (p = 0.012). In exchange, R2 kept only 2 personal-constraint fixes on train, against 14 for R0. |
| Cost | **R3 spends about twice the tokens of R2** (179k vs 93k per query). Both would cost about the same (≈210k) if every request were sent to the model. R2 is cheaper because its repeated requests are served from the cache, not because it is more efficient. |
| Matrix | **Nearly every regression comes from commonsense repair rounds**, mostly breaking accommodation or budget constraints. Fixing one personal constraint almost never broke another: 3 cases across all runs. That is too sparse to estimate a personal-to-personal matrix `M`. |

## What can be compared

A comparison is only fair between two runs on the same split under the same repair loop (commit
`5fab19a` or later: 6-round budget, repeated commonsense rounds, shared repeat-request cache).
That leaves two pairs. The archived R3 runs used the earlier loop and are left out.

| Strategy | subset_test (30) | subset_train (60) |
|---|---|---|
| R0 baseline | **Not run** | Done |
| R1 targeted | **Not run** | **Not run** |
| R2 rollback | Done | Done |
| R3 adaptive | Done | Old loop only |
| R4 matrix | Not yet | n/a |

> The R0 baseline has not been run on subset_test, the split where the project's comparisons
> count. Every test-split number below is R2 against R3. None of it is measured against the
> baseline yet.

## subset_test: R2 vs R3

Same 30 queries for both. **Bold** marks the better value where the difference is large enough to
mention. Runs `subset_test-r2` and `subset_test-r3`.

| Measure | R2 | R3 | Note |
|---|---:|---:|---|
| ***Outcome*** | | | |
| Plans passing every constraint (repair verifier) | 1 / 30 | 3 / 30 | McNemar p = 0.63; the passing queries do not overlap |
| Plans passing every constraint (benchmark evaluator) | 0 / 30 | 2 / 30 | disagrees with the repair verifier, see caveats |
| Passing after round 5 | 1 | 2 | round 6 added one pass for R3 |
| Queries passing all personal constraints, start → end | 15 → 16 | 14 → 15 | both gained one |
| Benchmark: all personal constraints pass (logical macro) | 53.3% | 50.0% | |
| Benchmark: commonsense checks passed (micro) | 86.1% | 87.4% | |
| Benchmark: schema pass | 36.7% | 43.3% | |
| ***Repair behaviour*** | | | |
| Commonsense errors, first → last commonsense round | 113 → 102 | **158 → 115** | net −10% vs −27% |
| Share of those errors fixed | 50% | **67%** | R3 also added more new errors (63 vs 46) |
| Personal-constraint fixes kept | 3 | 7 | R2's rejected proposals held 19 more fixes |
| Rounds that proposed breaking a personal constraint | 11 of 169 | **3 of 174** | R2 rolled back all 11; R3 kept all 3 |
| Share of plan slots changed, when the plan changed | 53% | **33%** | R3 makes smaller edits |
| ***Cost*** | | | |
| Rounds used per query | 5.6 | 5.8 | 29 and 27 queries used the full budget |
| Rounds that repeated an identical request | 57% | **17%** | answered from the cache, no model call |
| Rounds that left the plan unchanged | 64% | **37%** | |
| LLM tokens spent per query | **92.6k** | 178.6k | real model calls only |
| Tokens per query if nothing were cached | 213k | 210k | same nominal cost |
| Model calls per query | 2.4 | 4.9 | |
| Wall time per query | 94 s | 167 s | |

## subset_train: R0 vs R2

Same 60 queries for both. On this split R2 can be compared with the baseline. Runs
`subset_train-r0` and `subset_train-r2`.

| Measure | R0 | R2 | Note |
|---|---:|---:|---|
| ***Outcome*** | | | |
| Plans passing every constraint (repair verifier) | 4 / 60 | 5 / 60 | 1 and 2 of these passed before any repair; p = 1.0; no overlap |
| Plans passing every constraint (benchmark evaluator) | 0 / 60 | 1 / 60 | disagrees with the repair verifier, see caveats |
| Queries that passed after round 5, then broke | 3 | 0 | |
| Queries passing all personal constraints, start → end | 27 → 23 | **29 → 30** | queries with at least one round (59 and 57) |
| Queries passing all personal constraints at the end (all 60) | 40% | **55%** | McNemar 10 vs 1, p = 0.012 |
| Benchmark: all personal constraints pass (logical macro) | 43.3% | **55.0%** | |
| Benchmark: commonsense checks passed (micro) | 88.2% | 86.7% | |
| Benchmark: schema pass | 36.7% | 53.3% | |
| ***Repair behaviour*** | | | |
| Commonsense errors, first → last commonsense round | **342 → 230** | 293 → 271 | net −33% vs −8% |
| Share of those errors fixed | **64%** | 51% | new errors 107 vs 128 |
| Queries where a commonsense round broke a personal constraint | 9 | 5 | R0 recovered 3, R2 none |
| Personal-constraint fixes kept | 14 | 2 | R0 also kept 18 regressions |
| Rounds that proposed breaking a personal constraint | 17 of 331 | 25 of 332 | R0 kept all 17; R2 rolled back all 25 |
| Share of plan slots changed, when the plan changed | 49% | 45% | both rewrite the whole plan |
| ***Cost*** | | | |
| Rounds used per query | 5.5 | 5.5 | |
| Rounds that repeated an identical request | 54% | 54% | |
| Rounds that left the plan unchanged | 60% | 64% | |
| LLM tokens spent per query | 88.8k | 89.3k | |
| Tokens per query if nothing were cached | 200k | 201k | |
| Wall time per query | 99 s | 112 s | |
| Queries that crashed | 0 | 1 | file-permission error on a OneDrive path |

## Signal for the regression matrix

R4 needs `M[i→j]`: how often repairing constraint family *i* breaks family *j*. The table counts
regressions in proposed plans, from `regression_matrix/` in each run. A "cell with data" is a
source–destination pair with at least one usable observation.

| Run | Observations | Cells with data | Regressions | Where the regressions are |
|---|---:|---:|---:|---|
| test · R2 | 139 | 7 | 6 | commonsense repair → budget 6/20 |
| test · R3 | 311 | 21 | 2 | budget → party resources 1/10; commonsense repair → attraction 1/30 |
| train · R0 | 275 | 24 | 18 | commonsense repair → accommodation 8/20, → trip specification 6/72, → budget 1/12, → attraction 1/15; trip specification → budget 1/1; budget → trip specification 1/3 |
| train · R2 | 307 | 15 | 25 | commonsense repair → accommodation 13/36, → budget 12/39 |

- **The matrix has one row that matters.** 49 of the 51 regressions start from a commonsense
  repair round, and most land on accommodation or budget. Only 3 come from fixing one
  personal-constraint family and breaking another.
- **R3 gives the most coverage on fewest queries** (311 observations from 30 queries) and the
  lowest regression rate. Its matrix is clean but nearly empty, so it says little about which
  families conflict.
- **R2's kept-plan matrix is empty by design**, because the rollback discards every regressing
  proposal. Only its proposed-plan matrix carries signal.
- **R0 has the widest spread of regressions**, as expected from whole-plan rewrites. That makes it
  the most informative source so far for the commonsense row, but also the noisiest.

## Caveats

- **Each run starts from a different first plan.** The planner generates a new first plan in
  every run, so no plan hash matches between paired runs (0 of 30 and 0 of 60). Results at the
  start were identical on 23 of 30 test queries and 40 of 56 train queries. R3 started with more
  commonsense errors than R2 (4.7 vs 4.0 per query). Some of every gap above comes from starting
  position rather than strategy.
- **Samples are small.** Pass-rate gaps are 1–2 queries and not statistically significant. Only the
  personal-constraint result on train (R2 over R0) reaches p < 0.05.
- **The repair verifier and the benchmark disagree on full passes**: 1 vs 0 (test R2), 3 vs 2
  (test R3), 4 vs 0 (train R0) and 5 vs 1 (train R2). Until that is explained, quote both.
- **Every full pass started with all personal constraints satisfied.** No strategy fully repaired
  a query that began with a failed personal constraint. Repair only fixed commonsense errors on
  plans that already met the user's requirements.
- **Many personal-constraint results are unknown** because the plan could not be translated for
  checking. Unknowns range from 10 to 42 per run and shift between rounds, which moves the
  personal satisfaction rates.
- **Do not compare across splits.** R2 scored 36.7% schema pass on test and 53.3% on train, so
  split differences are as large as strategy differences.

## Runs still needed

1. **R0 on subset_test.** This is the baseline every hypothesis is measured against, and it is
   missing on the split where comparisons count.
2. **Reuse one first plan per query across all strategies**, so paired runs differ only in the
   repair step. Without this, gaps of a few queries cannot be attributed to the strategy.
3. **R1 on both splits, and R3 on subset_train under the current loop**, to complete the R0–R3
   comparison and give R4 a matrix from every strategy.
4. **Reconcile the repair verifier with the benchmark evaluator** on the passing queries listed in
   each run's `summaries.csv`.

## Sources and method

Sources: `experiments/subset_test-r2`, `experiments/subset_test-r3`, `experiments/subset_train-r0`,
`experiments/subset_train-r2`. Each folder holds `summaries.csv`, `phase_outcomes.csv`,
`pass_rates.csv`, `llm_cache_hits.csv`, `attempts.jsonl`, `benchmark_eval/` and
`regression_matrix/`.

Counts of proposed regressions, kept fixes, unchanged rounds and start/end personal results are
recomputed from `attempts.jsonl`. Commonsense figures come from `pass_rates.csv`, and McNemar tests
are exact, two-sided, on paired queries.
