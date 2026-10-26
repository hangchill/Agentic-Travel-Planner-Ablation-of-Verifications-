# Data and definition audit

This is the original audit snapshot. Availability now comes from discovered data;
see README.md for the current partition-aware layout and final-run workflow.

Audited before dashboard metric design, 2026-10-26. The dashboard is a read-only
presentation layer. The existing analysis scripts and numerical outputs are unchanged.

## Sources and coverage

| Partition | Strategy | Queries | Proposals | Common TEST tables | Strategy CSVs |
|---|---|---:|---:|---|---|
| TRAIN | R0 | 60 | 331 | Not applicable | Yes |
| TRAIN | R1 | 60 | 346 | Not applicable | Yes |
| TRAIN | R2 | 60 | 332 | Not applicable | Yes |
| TRAIN | R3 | 60 | 325 | Not applicable | Yes |
| TEST | R0 | 30 | 174 | Not generated | No matching analysis folder |
| TEST | R1 | — | — | Run unavailable | Run unavailable |
| TEST | R2 | 30 | 169 | Yes | Persisted attempts/checkpoints |
| TEST | R3 | 30 | 174 | Yes | Persisted attempts/checkpoints |
| TEST | R4 | 30 | 175 | Yes | Yes |

Active sources are `experiments/subset_{train,test}-r*`; TRAIN R3 uses
`subset_train-r3-new`. Archives and pilots are excluded. There is no R4 TRAIN run.
Each available run has a manifest, attempts.jsonl, query initial states, checkpoints,
summary/cost indexes and benchmark exports. R0–R3 TRAIN have saved matrix triplets,
long cell tables, coverage metadata and contribution rows. R4 TEST has nested
`queries/*/trials/`, selected `final_state.json` exports, matrix-input snapshots,
run/selection metadata, and generated `r4_trials`, `r4_selections`, guidance,
safety, provenance, targeting and cost CSVs.

`results/analysis/repair_strategies/R0`–`R3` currently describe TRAIN, not TEST.
Their provenance binds to the specific run. `R4` describes TEST. All have
attempt/query/overall/phase/mechanism/failure/footprint/evidence tables;
strategy hooks add global rewrite, localization, protection/rollback or scopes.
These folders must never be joined to TEST simply by strategy label.

## TEST builder audit

Authority: `scripts/result_analysis/build_test_result_tables.py`, the script used
by the committed `test_result_analysis/README.md` and its R2/R3/R4 reporting tables.
The CLI accepts arbitrary `LABEL=DIR` values. It does not enforce a TEST partition
or R0–R4 whitelist itself. It resolves the first requested manifest strategy and
expects exactly one `benchmark_eval/<strategy>-*` directory. The dashboard adds
explicit partition/source/population checks.

Inputs:

- `run_manifest.json`: IDs, requested strategy, language, nominal budget.
- `benchmark_eval/*/evaluation_population.json`: reference hard-logic constraints.
- `benchmark_eval/*/plans/<uid>.json`: final benchmark-exported plan.
- `queries/*/<strategy>-*.json` or `queries/*/trials/<strategy>-*.json` via `pair_path`:
  initial translated plan, repair history, attempt usage, stop reason.
- `chinatravel/evaluation/splits/subset_origin.json`: easy/medium/human groups.

`build_queries()` calls local benchmark evaluators to rescore initial/final plans.
**The dashboard never calls it or score_plans().** It consumes the generated CSVs.
The pure `table_pc`, `table_pc_kinds`, `table_cs`, `table_process`, `table_eval_exp`
functions can summarize saved per-query rows without running scoring, and are
reused for filtered cohorts.

Outputs per label:

- `per_query.csv`: 38 scalar/text fields, query identities and difficulty groups.
- `table1_pc.csv`: count/rate before/final/net; query increase/same/decrease;
  final 0/1/2+ failures; top three failure kinds; named-place exclusions.
- `table1b_pc_failure_by_kind.csv`: kind, failed, total, percent failed.
- `table2_cs.csv`: failed standard check counts before/final/change;
  improved/same/worse queries; final 0/1/2/3/4+ failures; strict >85% threshold;
  evaluator exceptions; top three check categories.
- `table3_repair_process.csv`: complete/lower-bound tokens, missing counts, time,
  per-token efficiency; changed-round effects; pooled changed/cached/other split.
- `table4_eval_exp.csv`: raw benchmark CS/PC micro/macro and schema+CS+PC all-pass.
- `README.md`; with multiple runs, merged side-by-side CSVs and `MERGED_TABLES.md`.

There is no individual round-number table. The process table's “round-wise” rows
are pooled over all rounds. Merged CSVs are formatted side-by-side tables; they
do not establish matched populations or compatible initial plans.

## Definitions, disagreements and chosen presentation

| Metric | Team TEST reporting | Strategy analyzer / diagnostic evidence |
|---|---|---|
| PC count/rate | Benchmark Boolean vector; passed / all reference PCs; macro average of query shares | Loop states; True / (True+False); UNKNOWN excluded; all UNKNOWN undefined |
| PC improved/same/decreased | Compare before/final passed count; total fixed per query | Accepted vector trajectory; explicit False→True fixes and True→False regressions |
| Final PC bins | `pc_total - pc_passed_final`, 0/1/2+ | Explicit False count; UNKNOWN is separate |
| Named-place exclusion | Existing `constraint_kind()` flags Chinese literal with `_name_set)` pattern; all other constraints retained | No equivalent generic analyzer metric |
| PC kinds | Team string-pattern classifier; per-kind failed constraints / total constraints | Structural family classifier is a different taxonomy; never interchange labels |
| PC fixed/new/net | Net benchmark count change available; separate fixed/new not persisted | Shared attempt metrics supply candidate and accepted fixes/new/net |
| CS counts/rates | Standard benchmark categories (currently 28); exceptions fail all standard checks | Loop error messages have no pass denominator; not check-category outcomes |
| CS improvement/bins | Compare failed standard check totals; final exact 0/1/2/3/4+ | Loop message-count/set changes are diagnostic only |
| >85% CS | Strict greater-than threshold, currently at most 4 of 28 failed | Unavailable from loop messages |
| CS fixes/new/net | Benchmark net count gain available; separate initial/final check identities absent | Message removals/introductions can be displayed with explicit labels |
| Changed round | JSON-sorted candidate `verification.translated_plan` differs from previously accepted translated plan; includes rejected candidates | Analyzer unchanged requires `no_progress_unchanged`; footprint zero is a separate observation |
| No progress | No dedicated TEST table metric; “unchanged_other” does not prove no progress | Explicit decision marker only |
| Changed-round PC effect | Candidate True-count delta, including UNKNOWN→True; mean within query then across queries | False→True events exclude UNKNOWN and have distinct candidate/accepted totals |
| Changed-round CS effect | Candidate error-count delta, negative means fewer; within-query then across-query averaging | No benchmark check-rate interpretation |
| Attempts | History entries after initial; `rounds` | Attempt stream proposals; query counts can include checkpoint-only zero-attempt evidence |
| Tokens/time | Complete sum of attempt deltas only; empty/missing totals are blank; known-token lower bound separate | Analyzer can report known zero for proven zero attempts; missing values remain unavailable |
| Model/verifier calls | Not generated by TEST builder | Persisted counters, complete sums only |
| Budget exhaustion | No table row; stop reason and early-stop flag persisted | Dashboard counts exact logged `repair_budget_exhausted`, never infers from six attempts |
| R4 final | Last accepted trial plan exported for benchmark | Analyzer separately stores last accepted and post-hoc selected outcomes |
| Raw CS benchmark | Table 4 retains raw exception column to match benchmark definition | Table 2 corrects exception cases by counting every standard check failed |

The dashboard uses the established team's TEST definition wherever provided.
These are different estimands, not silently “corrected” values. No clear numerical
bug was changed. The builder's human-readable source strings mention an older
script location and make a general claim about named-place behavior; the dashboard
does not expand that claim beyond the team's existing classifier/exclusion.

## Availability classification

**A — directly available:** R2/R3/R4 TEST PC/CS before/final and cohort reporting;
PC failure kinds; CS top failures; changed/cache/other split, costs, per-query
changed effects; TRAIN candidate/accepted cell counts/support/rates; strategy
attempt/query diagnostic columns; R4 trials, selection and guidance relationships.

**B — derived only from saved data:** percentages absent from team tables; CS
pass counts/rates from saved benchmark counts; filtered summaries by calling team
helpers; process medians and logged budget exhaustion; complete counter sums;
observed accepted round trajectories; localisation flags, protected-candidate
funnel, observed scope transitions, proposal guidance categories; saved-cell pooled
count/support rates; candidate-example search. These derivations are in metrics.py.

**C — unavailable:** R1 TEST, R4 TRAIN, R0 TEST common reporting until generated;
initial/final benchmark PC and CS fixed/new identities; per-round benchmark pass
rates; unlogged localisation success/validated scope confinement; causal effects;
proof a model followed matrix advice; missing usage deltas; true active/stopped
status beyond persisted observations. UNKNOWN, missing and zero are distinct.

The matrix page does not rebuild eligibility from proposals. Its coverage metadata
shows the persisted single-target construction-stage count separately from eligible
relationship contributions. The additional eligible-attempt count deduplicates
query/step keys with existing eligible=True, is_single_target=True, personal-source
contributions for the selected perspective. It requires at least one eligible
observed destination; it does not substitute a new eligibility rule.
