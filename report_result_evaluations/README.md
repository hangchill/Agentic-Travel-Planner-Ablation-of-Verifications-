# report_result_evaluations

The processing code, saved tables and saved figures behind the report's Evaluation and Results section,
`docs/report/overleaf/evaluation_and_results.tex`. Everything is rebuilt from the saved runs with one command.
Nothing here calls a model.

```
python report_result_evaluations/run_all.py                  # a few minutes; system Python with pandas, numpy, matplotlib, plus uv
python report_result_evaluations/run_all.py --skip-rescore   # keep the saved T14 and fig6 (no project environment needed)
```

Only `failure_repair.py` (Table T14) and `plots/r1_vs_r3_scope_effect.py` (fig6) rescore plans with the
benchmark checker. They need the project environment and the sandbox database, so `run_all.py` runs them
through `uv run --no-sync --with matplotlib`.

## Folders

| Folder | Contents |
|---|---|
| `report_tables/` | The three tables of the .tex, in its layout (same rows, columns and rounding) |
| `tables/` | The data tables they are built from, and the tables whose numbers the text quotes |
| `figures/` | The six figures of the .tex |
| `data/` | One row per round, per query and per personal constraint, read from the saved runs |
| `plots/` | The scripts that draw fig2, fig4, fig5 and fig6 |

## What the report uses

| In the .tex | File in `report_tables/` | Built from |
|---|---|---|
| Table "Key held-out TEST results" (`tab:key_test_results`) | `key_test_results.csv` | `tables/t1_headline.csv` (rates), `tables/t5_efficiency.csv` (tokens, time) |
| Table "R0's regressions and the same items in R4" (`tab:r0-regressions-r4`) | `r0_regressions_r4.csv` | `tables/t16_r0_regressions_in_r4.csv` (which reads `tables/t14_failure_repair.csv`) |
| Table "The six test queries…" (`tab:r0-r4-case-trace`) | `r0_r4_case_trace.csv` | `tables/t16b_r0_r4_case_trace.csv`; the three descriptive columns are the .tex text, kept in `CASE_TRACE_TEXT` in `build_report_tables.py`, which stops if the trace no longer agrees with them |

All three are written by `build_report_tables.py`.

| Figure in the .tex | File | Built by |
|---|---|---|
| fig1 effectiveness against cost | `figures/fig1_effectiveness_vs_cost.png` | `make_figures.py` (T1, T5) |
| fig2 change by difficulty | `figures/fig2_change_by_difficulty.png` | `plots/difficulty_test.py` |
| fig3 effectiveness against cost, train | `figures/fig3_effectiveness_vs_cost_train.png` | `make_figures.py` (T7b) |
| fig4 difficulty with cost (test) | `figures/fig4_difficulty_with_cost.png` | `plots/difficulty_test.py` |
| fig5 difficulty with cost (train) | `figures/fig5_train_difficulty.png` | `plots/difficulty_train.py` |
| fig6 R1 against R3 scope effect | `figures/fig6_r1_vs_r3_scope_effect.png` | `plots/r1_vs_r3_scope_effect.py` |

The figure files have the same names as `docs/report/overleaf/figures/`; copy them there after a rebuild.

Tables whose numbers the text quotes, but which the .tex does not show:

| Table | Numbers in the text |
|---|---|
| T3 `t3_regression.csv`, T3c `t3c_regression_queries.csv` | Ablation 1: R0's 11 accepted regressions on 6 queries and how they ended; R2's 11 rejected candidates on 2 queries |
| T4 `t4_budget_use.csv` | Rounds, and the share of rounds that changed the plan or were cached repeats (Efficiency, Ablations 1 to 3) |
| T6 `t6_difficulty_effectiveness.csv` | Performance by query difficulty; personal-constraint change per strategy (Ablations 1 and 3); plans that fail at most four checks |
| T6b `t6b_difficulty_what_fails.csv` | Named-place failures in the Easy group |
| T11 `t11_query_outcome_map.csv` | The query that only R4 completed (Ablation 3) |
| T14 `t14_failure_repair.csv` | Input of T16 |

## Files

| File | What it does |
|---|---|
| `run_all.py` | Runs the scripts below in order and merges their manifests into `MANIFEST.csv` |
| `load_runs.py` | Reads the runs once and writes `data/rounds.csv` (one row per repair round), `data/queries.csv` (one row per query and run) and `data/constraints.csv` (one row per personal constraint and run) |
| `failure_repair.py` | Writes `tables/t14_failure_repair.csv`: per strategy, the initial failures of each personal-constraint kind and commonsense check that pass in the final plan, and the passing items that break (benchmark rescoring of the initial and final plans) |
| `build_report_tables.py` | Writes `tables/t*.csv`, `report_tables/*.csv` and `tables/REPORT_TABLES.md` (every table with its caption and source) |
| `plots/difficulty_test.py` | fig2 and fig4. Copied from `test_result_analysis/difficulty_comparison_graphs/difficulty_comparison_ALL.py`; only the paths changed |
| `plots/difficulty_train.py` | fig5. Copied from the plot step of `train_result_analysis/difficulty_comparisons/difficulty_comparison_r0-3.py`; only the paths changed |
| `plots/r1_vs_r3_scope_effect.py` | fig6. Copied from `test_result_analysis/R3/scoping_effect/R1vR3_scope_effect_graph.py`; only the paths changed. `failure_repair.py` imports its plan loader |
| `make_figures.py` | Draws fig1 and fig3, checks that the plot scripts wrote the other four, and writes `figures/manifest_figures.csv` |
| `MANIFEST.csv` | One row per table and figure: report id, path, source script, whether it carries a confidence interval |

## Inputs (read only)

| Input | Used for |
|---|---|
| `experiments/subset_test-r{0..4}/` and `experiments/subset_train-{r0,r1,r2,r3-new}/` (`attempts.jsonl`, per-query checkpoints, `reference/query.json`, `benchmark_eval/`) | Every round-level number (loop verifier), the benchmark scores of the final plans, and the hotel bookings in T16b |
| `test_result_analysis/<S>/per_query.csv`, `train_result_analysis/<S>/per_query.csv` | Benchmark scores of the initial plans |
| `test_result_analysis/merged/`, `train_result_analysis/merged/` | fig2, fig4 and fig5 |
| `scripts/result_analysis/build_test_result_tables.py` | The benchmark scoring functions that fig6 and T14 import |
| `chinatravel/evaluation/splits/subset_origin.json` | Difficulty group of each query |

## Definitions used by the scripts

- **Round that changed the plan:** `decision_reason != "no_progress_unchanged"`. This includes the 11 R2 candidates that rollback rejected.
- **Cached no-op:** an unchanged round whose request was an exact repeat answered by the loop's repeat-request cache (`llm_cache_hits > 0`). **Locked round:** a no-op that follows a no-op in the same repair phase.
- **New / fixed commonsense errors per round:** set difference of the candidate plan's loop-verifier error messages against the accepted plan's messages before the round.
- **Regression (T16):** during repair, a personal constraint that passed before a changed round and failed after it (loop verifier; at risk counts constraint-rounds). From initial to final plan, an item that passed in the initial plan and fails in the final plan (benchmark).
- **Flagged families (T3, T16):** total budget and food cost → `monetary_budget`; rooms / room type → `accommodation`.
- **Hotel booking changed (T16b):** a changed round whose candidate plan has different accommodation activities (day, hotel, room type, rooms) from the plan before.
- **Repair tokens and time:** repair rounds only; the initial plan generation is not counted. **Nominal tokens:** tokens spent plus the tokens the cache saved.
- **Initial plan:** the plan before any repair round. Every run generated its own, so the change from the initial plan is reported beside each final level.
- **Statistics:** descriptive values. A percentile bootstrap 95 % CI over queries (5,000 resamples, seed 4213) is given only in T1 and T3. fig6 carries its own intervals (4,000 resamples, seed = round number). No hypothesis tests.

## Caveats carried over from the runs

- R1 train has reconstructed checkpoints without an initial plan or per-step verifications, so it appears only with final benchmark scores. Its rebuild and scoring were done once by the score step of `train_result_analysis/difficulty_comparisons/difficulty_comparison_r0-3.py`, which writes into `experiments/subset_train-r1` and so is not copied here.
- Two R2 test queries stopped early after a verifier crash (1 and 4 rounds used); their `stop_reason` says `repair_budget_exhausted`.
- Three R0 train final plans are the error text of a failed API call; the commonsense checker cannot score them and they count as failing every check.
- The loop verifier checks named-place constraints against the Chinese name, so it never passes them in English runs; the benchmark translates the name before scoring.
