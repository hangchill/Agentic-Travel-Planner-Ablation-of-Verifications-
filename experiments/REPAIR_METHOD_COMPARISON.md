# Repair method comparison

As of 2026-10-25 · deepseek-chat, temperature 0, English sandbox, 6-round repair budget

On the current runs, no method's pass rate differs from another's by more than chance. The differences that hold up are in how the methods behave:

- **R3 keeps making changes and rarely breaks things.** It changes the plan in 63% of rounds and breaks a passing personal constraint in 1.7% of rounds.
- **R2's rollback works.** It never kept a plan that broke a personal constraint, and it lost no query whose personal constraints all passed at the start.
- **R0 and R2 mostly repeat themselves.** About 55% of their rounds send exactly the same request as an earlier round and get the same plan back.

Two things limit every comparison. There is no R0 run on `subset_test` and no R1 run under the current loop. And the repair loop's verifier never checks for overlapping activities, which is the most common reason the benchmark fails a plan.

---

## 1. Runs compared

Four runs used identical repair code (implementation hash `d8664b6…`). Between their commits only the analysis scripts changed (regression matrix, summaries), so these runs can be compared directly.

| Run | Method | Split | Queries | Commit |
|---|---|---|---|---|
| `subset_train-r0` | R0 whole-plan regeneration | train | 60 | `0034ac0` |
| `subset_train-r2` | R2 protected (rollback) | train | 60 | `8aa2de3` |
| `subset_test-r2` | R2 protected (rollback) | test | 30 | `606021e` |
| `subset_test-r3` | R3 adaptive scope | test | 30 | `606021e` |

**Left out:** `archives_runs/subset_{train,test}-r3-beforefix` (`e1d97b7`). They ran the old loop, which gave 5 personal rounds plus 1 commonsense round and had no repeat-request cache, so their numbers are not comparable. There is no R1 run on either subset.

**Only two pairs share a split:** R0 vs R2 on train, and R2 vs R3 on test.

**Each run starts from its own initial plan.** Each run generated its own initial plan, and in all 30/60 queries the initial plan differed between runs, even at temperature 0, because the provider is not deterministic. So each method starts from a different plan, which adds noise on top of the method's own effect.

## 2. Pass rates: no reliable difference

| Run | Final pass (loop verifier) | All-pass (benchmark evaluator) | All personal constraints pass at end |
|---|---|---|---|
| R0 train | 4/60 (6.7%) | 0/60 (0%) | 24/60 (40%) |
| R2 train | 5/60 (8.3%) | 1/60 (1.7%) | 33/60 (55%) |
| R2 test | 1/30 (3.3%) | 0/30 (0%) | 16/30 (53%) |
| R3 test | 3/30 (10.0%) | 2/30 (6.7%) | 15/30 (50%) |

- **R3 vs R2 on test:** 3 vs 1 final passes (Fisher exact p = 0.61); 2 vs 0 benchmark passes (p = 0.49).
- **R2 vs R0 on train:** 5 vs 4 final passes (p = 1.0).
- **No query passed under both methods**, in either pair. The R3 rerun and the old R3 test run also share no passing query. Which plans pass depends mostly on the initial plan and on chance, not on the method.
- **Detectable gap:** with 30 queries per method, the gap would need to be about 6 passing plans to 0 to reach p < 0.05.

**One outcome difference is significant: R2 keeps personal constraints satisfied better than R0.** On train, 10 queries ended with all personal constraints passing under R2 but not R0, and 1 the other way (sign test p = 0.012). Section 3 shows why: R0 keeps plans that break constraints, and R2 rolls them back.

## 3. Behaviour: the differences that hold up

These metrics are counted per repair round (169–332 rounds per run), so they are much less noisy than pass rates.

| Metric | R0 train | R2 train | R2 test | R3 test |
|---|---|---|---|---|
| Repair rounds | 331 | 332 | 169 | 174 |
| Rounds returning an identical plan | 198 (60%) | 214 (64%) | 108 (64%) | **64 (37%)** |
| Rounds answered from the repeat-request cache | 179 (54%) | 180 (54%) | 96 (57%) | **29 (17%)** |
| Rounds that broke a passing personal constraint | 17 (5.1%) | 25 (7.5%) | 11 (6.5%) | **3 (1.7%)** |
| ...of those, kept in the plan | **17** | 0 | 0 | 3 |
| Queries that lost "all personal constraints pass" | **5 of 28** | 0 of 32 | 0 of 15 | 0 of 14 |
| Commonsense errors before the commonsense rounds | 342 | 293 | 113 | 158 |
| Commonsense errors fixed / newly introduced | 219 / 107 | 150 / 128 | 57 / 46 | 106 / 63 |
| Net commonsense reduction | **33%** | 8% | 10% | **27%** |
| Mean tokens per query | 95k | 94k | 93k | 185k |
| Mean wall time per query | 99 s | 112 s | 94 s | 167 s |

**Whole-plan methods get stuck.** R0 and R2 send the same request again and get the same plan back in over half their rounds. At temperature 0 an unchanged prompt returns an unchanged plan, so about 55% of the budget does nothing. R3's prompt changes as its scope widens (slot, then day, then plan), so it keeps exploring. Against R2 on test, the gap in identical-plan rounds is 37% vs 64% (p < 0.001).

**Narrow edits break less.** R3 broke a passing personal constraint in 3 of 174 rounds, against 11 of 169 for R2 on test (p = 0.03). Only 56 of R3's 174 rounds were at whole-plan scope.

**R2's rollback works as designed.** Every candidate that broke a personal constraint (25 on train, 11 on test) was rejected. R0 kept all 17 of its breaking candidates and lost 5 of the 28 queries that started with every personal constraint satisfied.

**R2 makes the least progress on commonsense errors.** It removes a net 8–10% of commonsense errors, against 33% for R0 and 27% for R3. One possible cause: R2 discards a whole candidate that breaks a personal constraint, along with any commonsense fixes in that candidate. This has not been checked yet.

**The R2 numbers hold across splits.** R2's train and test runs agree closely: 64% identical-plan rounds on both, 54% vs 57% cache-served rounds, and 8% vs 10% commonsense reduction. So these metrics are stable enough to compare methods.

**R3 costs twice as much, but only in tokens actually spent.** R3 spends about 2× the tokens of R0 or R2 because its requests rarely repeat, so the cache rarely answers them. Counting cache-served rounds at full price, R2 test and R3 test cost about the same (6.40M vs 6.30M tokens). R0 and R2 look cheaper because half their rounds are free repeats that change nothing.

## 4. Regression-matrix signal (for R4 / H3)

All four matrices were rebuilt with the current `build_regression_matrix.py` (definition v2.1.0) so they are counted the same way. The saved R0 matrix predates `9ceac72`, which excludes unchanged attempts, and should be rebuilt in place.

| Run | Rounds | Single-target rounds | Eligible contributions | Regressions observed | Matrix cells with data (of 81) |
|---|---|---|---|---|---|
| R0 train | 331 | 115 | 275 | 18 | 24 |
| R2 train | 332 | 94 | 307 | 25 | 15 |
| R2 test | 169 | 31 | 139 | 6 | 7 |
| R3 test | 174 | 51 | 311 | 2 | 21 |

R3 gives the cleanest causal signal, but because it rarely regresses, its matrix is nearly all zeros: 2 regressions in 311 eligible contributions. R0 and R2 record more regressions, but from whole-plan rewrites, where cause and effect are mixed. The matrices therefore trade data volume against attribution quality. That trade-off is part of H3's answer, but no single run is yet large enough to fill most of the 81 cells.

## 5. Verifier gap: the loop never sees overlapping activities

The repair loop marked 10 plans as passing that the benchmark failed: 4 under R0 train, 4 under R2 train, 1 under R2 test and 1 under R3 test. All 10 fail the benchmark's "Does not follow Chronological Order" check.

The two verifiers check time order differently:

- **Loop verifier** (`chinatravel/agent/nesy_verifier/verifier/commonsense_constraint_nl.py`, `collect_time_error`): checks only that each activity ends after it starts and starts after its transport arrives.
- **Benchmark evaluator** (`chinatravel/symbol_verification/commonsense_constraint.py`): also requires that activities do not overlap and that transport leaves after the previous activity ends.

Chronological order is the most common benchmark failure in every run: 45/60 (R0 train), 50/60 (R2 train), 22/30 (R2 test) and 23/30 (R3 test) final plans. No repair method is ever told about it, so it caps every method's benchmark pass rate. Adding the overlap checks to the loop verifier would change all methods, so every run would need repeating afterwards.

## 6. Missing before H1/H2 can be tested

- **R0 on `subset_test`.** Every hypothesis is stated relative to R0, and the test split is where comparisons count. There is currently no R0 test run.
- **R1 under the current loop**, on both splits.
- **R3 on `subset_train` under the current loop.** It is needed for R3's matrix; only the old-loop run exists.
- **Same initial plan for every method.** Each run currently generates its own initial plan, and that is the largest source of noise. Reusing one frozen initial plan per query (`queries/*/initial_state.json` is already saved) would make the comparisons paired.
- **Overlap check in the loop verifier** (section 5). If added, it should go in before the runs above.

---

**Data:** `experiments/subset_train-r0`, `subset_train-r2`, `subset_test-r2`, `subset_test-r3` (`summaries.csv`, `pass_rates.csv`, `llm_cache_hits.csv`, `attempts.jsonl`, `benchmark_eval/*/`). The p-values are two-sided Fisher exact tests, except the paired personal-pass comparison, which uses a sign test.
