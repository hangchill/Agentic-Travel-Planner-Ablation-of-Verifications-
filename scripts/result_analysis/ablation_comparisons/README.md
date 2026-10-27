# Ablations & Comparisons (offline)

This module reads existing TEST reporting and trajectory artifacts. It never runs
experiments, scores plans, invokes a verifier/model, rebuilds a matrix, or imports
Streamlit. The dashboard reads its generated CSV/JSON, with no subprocess or
metric calculation on reruns. Existing reporting definitions are unchanged.

## Questions and interpretation

| Pair (left → right) | Type | Question |
| --- | --- | --- |
| R0 → R2 | Mechanism comparison / ablation-like comparison | Does rollback reduce harmful accepted regressions? |
| R1 → R3 | Mechanism comparison | Does scheduled scope flexibility improve outcomes relative to localization? |
| R3 → R4 | Strategy comparison — not a matrix ablation | How do advanced strategies differ in quality, cost and behaviour? |
| R4 without matrix → R4 with matrix | Matrix-guidance ablation candidate | What does matrix guidance contribute, if other controls match? |

**Delta = Right - Left**, calculated from displayed source values, without
unrounding saved tables. A positive delta is not necessarily better. Every common
metric records `higher`, `lower`, or `descriptive`. Counts, percentages,
percentage-point changes, events per proposal and time are separately labelled.
No significance or causal claim follows from a descriptive or matched comparison.

## Run the CLI

From the repository root with the project's Python environment:

```bash
python -m scripts.result_analysis.ablation_comparisons.build_ablation_comparisons \
  --r0 experiments/subset_test-r0 \
  --r2 experiments/subset_test-r2 \
  --r3 experiments/subset_test-r3 \
  --r4 experiments/subset_test-r4 \
  --test-reporting-dir test_result_analysis \
  --analysis-dir results/analysis/repair_strategies/test \
  --output-dir results/analysis/ablation_comparisons
```

Future complete runs (replace paths with actual final-run folders):

```bash
python -m scripts.result_analysis.ablation_comparisons.build_ablation_comparisons \
  --r0 experiments/final_test-r0 \
  --r1 experiments/final_test-r1 \
  --r2 experiments/final_test-r2 \
  --r3 experiments/final_test-r3 \
  --r4 experiments/final_test-r4 \
  --r4-no-matrix experiments/final_test-r4-no-matrix \
  --test-reporting-dir test_result_analysis \
  --r4-no-matrix-reporting-dir results/analysis/test_reporting_no_matrix \
  --analysis-dir results/analysis/repair_strategies/test \
  --r4-no-matrix-analysis-dir results/analysis/repair_strategies/test_no_matrix \
  --output-dir results/analysis/ablation_comparisons
```

All run arguments are optional. Omitting R1 or R4-no-matrix creates explicit
unavailable results for those comparisons; TRAIN or another strategy is never
substituted. Only supplied runs are loaded. `--comparison r0_vs_r2` limits building
to one pair; the option can repeat. `--matched-query-subset` explicitly opts into
intersection analysis. `--repository-root` resolves relative recorded provenance.
Output directories must be separate from input directories. Run `--help` for all
options.

The second R4 run needs its **own** reporting root, containing `R4/` and the team
builder's `README.md`; a single canonical `R4/` cannot describe two distinct runs.
Use the unchanged TEST table builder with an alternate `--output-dir`. No-matrix
reporting is never silently read from the with-matrix root. Its diagnostics root
is also independently configurable.

## Inputs and existing authoritative code

- `scripts/result_analysis/build_test_result_tables.py` remains the common TEST
  source of truth. Full-cohort comparison cells are read verbatim from Tables
  1–4. Explicit intersection slices call its pure `table_pc`, `table_cs`,
  `table_process`, `table_eval_exp` on saved `per_query.csv`; neither `build_queries`
  nor `score_plans` is called. Source rounding and raw evaluator universes remain.
- Reporting must have an unambiguous strategy README section binding source path
  and run ID, all six existing CSV files, exact unique manifest UIDs, intended
  strategy, and recognized saved difficulty groups. Difficulty comes from saved
  `group` (`easy`, `medium`, `human`), never UID prefixes.
- `scripts/analyze_repair_strategies.load_run/build_tables`, strategy hooks and
  `chinatravel.evaluation.repair_metrics.compute_attempt_metrics` validate raw
  transitions and define candidate/accepted events. They run read-only in the CLI.
  `--analysis-dir` checks matching generated provenance where available; its cells
  are not silently substituted for the shared helper's current result. Legacy
  TRAIN diagnostics cannot bind to TEST. Missing pre-generated diagnostics do not
  require regenerating them: the same pure analysis helpers accept saved logs.
- R4 selection/pool counts reuse `scripts.repair_analysis_r4.build_tables` and
  validate the selected outcome against its recorded candidate pool. Matrix
  provenance reuses `audit_matrix`, including its documented LF/CRLF equivalence
  rules and TRAIN population checks. It does not rebuild guidance.
- Missing inputs/fields produce unavailable values. If common reporting is
  absent, full-cohort loop diagnostics may still be available; difficulty-specific
  comparisons require saved difficulty identities on both sides.

## Validity rules

`validity.json` records each check as `pass`, `fail`, or `unknown`, with both
recorded values. It checks UID set/count, per-UID difficulty, recorded initial-plan
hashes, base model, sampling/config, nominal and effective strategy repair budget,
scheduler, verifier/evaluator, repair implementation, benchmark source and query
identities, language, translation mode, seed, and intended strategy difference.
Missing metadata never counts as an agreement.

- **Incompatible / blocked**: missing/invalid required TEST run, incompatible
  populations, conflicting difficulty mappings, wrong strategy pairing, duplicate
  matrix run paths, or contradictory recorded matrix treatment. Deltas are blank.
- **Descriptive comparison only**: population match permits descriptive values,
  but any other control is unknown or differs. Different initial plans or
  implementations are prominently recorded and never called controlled.
- **Matched strategy comparison**: all checks pass for R0/R2, R1/R3, or R3/R4.
  It still does not license causal claims.
- **Controlled ablation**: reserved for distinct R4 runs with all checks passing,
  verified TRAIN-only guidance provenance, explicit `matrix_guidance_enabled=false`
  on the left and `true` on the right, no positive guidance logged on the left,
  and a declared complete settings snapshot equal after removing only that Boolean.

Additional control metadata can be top-level or in `comparison_controls` (or
existing `compatibility.config`). Supported names are listed in
`comparison_validity.FIELDS`. Controlled matrix comparisons also require
`ablation_settings_complete: true` and `ablation_settings` on **both** manifests.
The snapshot must contain `model_identifier`, `sampling_settings`, `max_steps`,
`scheduler_version`, `repair_implementation_hash`, `verifier_config`,
`evaluator_config`, `benchmark_population_hash`, `language`, `oracle_translation`,
`seed`, `other_settings` (including every other relevant setting), and
`matrix_guidance_enabled`. This is a metadata contract for future experiments;
the analyzer does not add it to existing manifests. If it cannot be established,
classification is downgraded. No current run is relabelled as controlled.

With `--matched-query-subset`, the output is explicitly labelled **Matched-query
subset** and includes original N, matched N and excluded UIDs. Source helpers
recompute only this saved-query subset. Difficulty mapping must still agree.
An intersection never silently replaces full-cohort analysis, and differing
original populations prevent a controlled classification. By default population
mismatch produces no headline delta. All difficulty rows also require identical,
nonempty query cohorts on both sides.

## Outputs

```
results/analysis/ablation_comparisons/
  r0_vs_r2/{summary.csv,mechanism.csv,validity.json,metadata.json}
  r1_vs_r3/{summary.csv,mechanism.csv,validity.json,metadata.json}
  r3_vs_r4/{summary.csv,mechanism.csv,validity.json,metadata.json}
  r4_matrix_ablation/{summary.csv,mechanism.csv,validity.json,metadata.json}
  comparison_metrics.csv
  mechanism_metrics.csv
  index.json
  README.md
```

`summary.csv` and root `comparison_metrics.csv` are tidy rows with comparison ID,
type, difficulty, run/strategy identities, metric family/ID/label, values, delta,
unit/direction, cohort N, known-value N, validity, exact source and denominator.
Unavailable reasons remain explicit. `mechanism.csv` records side/run, difficulty,
metric, value, evidence N, source, denominator, unit and direction. The shared
`CATALOG` below specifies every common row. Source-row aliases support the
upstream token lower-bound wording change without changing values.

`metadata.json` stores generation time, invocation, source-run identities, notes,
source/code SHA-256 hashes and output hashes. CSVs are deterministic for the same
inputs/code; metadata timestamps change. The dashboard rejects edited outputs or
changed/deleted recorded inputs/code until regeneration. Cross-repository copies
should be regenerated to rebind absolute provenance. The root tidy files/index
cover the comparisons requested in that invocation; per-pair folders are
independent and may be regenerated one at a time.

## Mechanism definitions and limitations

- R0 has candidate/accepted PC-regression proposal counts, **no invented rollback
  or rejection metrics**. Its regressions are not labelled protected-PC harm.
- R2 harm is at least one previously True **protected** PC becoming False in the
  candidate (`protected_regression_count`). Rejection/acceptance is separate.
  Rejection rate divides rejected harmful proposals by harmful proposals.
  Harmful-query counts use distinct UIDs. Preservation counts distinct queries
  with a harmful rejected round whose logged accepted raw plan equals the prior
  accepted raw plan. Missing raw plans invalidate equality proof; vectors alone
  do not prove itinerary retention. Coverage is reported, not assumed complete.
- R1 localization opportunities, recorded slot selection, localization failures,
  actual reasons and measured footprint use `hook_r1`. Slot selection means a
  recorded two-element `editable_slot`; it is not equivalent to repair success.
- R3 scope reaches, attempts, next-scope transitions and successful-target scopes
  use `hook_r3`/shared `targeted_fixed_count`. Candidate and accepted target-fix
  counts are separately labelled. Highest scope uses recorded query sequences.
  Widening is **scheduled**, not inferred to be triggered by failure. Independent
  trials are never joined into a trajectory.
- R4 guidance status is logged-positive-support, logged-unsupported, or no logged
  relationship. A proposal may have supported and unsupported cells; the status
  means any supported cell exists. Support occurrence counts retain repeats and
  are not independent queries. Structural guard failures use logged
  `proposal_rejected_reason`; absent logging is unknown. Post-hoc initial/repaired
  selection and mean considered outcomes (including initial when the original
  helper counts it) are separate from benchmark/final accepted states.
  No-matrix guidance fields are unavailable when not logged, never manufactured.
- New standard-CS violations and net standard-CS check change remain unavailable:
  loop error messages cannot supply benchmark check-level transitions. CS >85%
  reuses the strict saved threshold count only with a consistent matching check
  denominator. Token completeness and all-PC success rates divide existing saved
  counts by selected query N. Attempts/query averages saved `rounds`.
- Table 4 Commonsense micro preserves the raw evaluator's exception-column
  inflation caveat; it is not the corrected Table 2 rate. Logical micro pools
  reference PCs; it is not mean per-query PC rate. No benchmark is rescored.

## Common metric catalog

| Metric | Source | Unit | Better | Denominator |
| --- | --- | --- | --- | --- |
| PC: Avg % PC passed: final | table1_pc: Avg % PC passed per query - final plan | % | higher | Queries; mean per-query share |
| PC: Avg % PC passed: change | table1_pc: Avg % PC passed per query - change (percentage points) | percentage points | higher | Queries; mean per-query share change |
| PC: Final plans with 0 failed PC | table1_pc: Final plans with 0 failed PC | queries | higher | Queries |
| PC: All-PC-pass rate | table1_pc: Final plans with 0 failed PC | % | higher | Selected query N; saved zero-failure count / N |
| PC: Queries with PC pass rate decreased | table1_pc: Queries where % PC passed decreased | queries | lower | Queries; saved count |
| PC: Avg new PC violations (candidate loop) | attempts: newly_violated_count | PCs/proposal | lower | Observed proposals with shared PC transition evidence; includes rejected candidates |
| PC: Avg net PC change (candidate loop) | attempts: net_repair_gain | PCs/proposal | higher | Observed proposals; shared candidate fixed minus regressed count |
| PC: Avg new PC violations (accepted loop) | attempts: accepted_newly_violated_count | PCs/proposal | lower | Observed proposals; rejected proposals contribute no accepted regression |
| CS: Avg % CS passed: final | table2_cs: Avg % CS checks passed per query - final plan | % | higher | Queries; mean corrected standard-check share |
| CS: Avg % CS passed: change | table2_cs: Avg % CS checks passed per query - change (percentage points) | percentage points | higher | Queries; mean corrected standard-check share change |
| CS: Final plans with 0 failed CS | table2_cs: Final plans with 0 failed CS checks | queries | higher | Queries; saved zero-failure count |
| CS: >85% CS success rate | threshold:  | % | higher | Selected query N; original strict threshold table count / N |
| CS: Avg new CS violations | unavailable:  | checks/proposal | lower | Unavailable: no standard-check transition table in existing reporting |
| CS: Avg net CS check change | unavailable:  | checks/proposal | higher | Unavailable: loop messages are not benchmark check identities |
| Process: Avg repair attempts/query | queries: rounds | attempts/query | descriptive | Selected queries; saved per_query.rounds mean |
| Process: Avg tokens/query (complete data) | table3_repair_process: [per query] Avg tokens spent per query (queries with complete token data) | tokens | lower | Queries with complete summed total_tokens_delta; source rounding retained |
| Process: Token completeness | table3_repair_process: [per query] Queries with token data | % | descriptive | Selected query N; saved complete-token query count / N |
| Process: Avg tokens/query lower bound | table3_repair_process: [per query] Avg tokens spent per query - all queries, failed requests counted as 0 (lower bound) OR [per query] Avg tokens spent per query - known values only, all queries (lower bound) | tokens | lower | All queries; missing token deltas add 0 only as a lower bound |
| Process: Avg repair time/query | table3_repair_process: [per query] Avg repair time per query (s) | seconds | lower | Queries with complete repair-time sums; source rounding retained |
| Process: Plan-change rate | table3_repair_process: [round-wise] % of rounds where the plan changed | % | descriptive | Observed repair rounds; candidate translated plan vs preceding accepted plan |
| Process: Model-call failure rate (error reply) | table3_repair_process: [round-wise] % of rounds where the model call failed (error text instead of a plan; includes cached repeats of a failed reply) | % | lower | Observed rounds; source raw_response error-text marker, including cached failures |
| Process: Cache-unchanged rate | table3_repair_process: [round-wise] % of rounds unchanged - answered from cache (exact repeat of an earlier request) | % | descriptive | Observed rounds; unchanged candidate and llm_cache_hits > 0 |
| Process: Explicit no-progress rate | attempts: unchanged_confirmed | % | descriptive | Observed proposals; decision_reason == no_progress_unchanged |
| Evaluation: Commonsense micro | table4_eval_exp: Commonsense micro (%) - share of all (plan, check) pairs passed | % | higher | Pooled raw evaluator cells including exception column; unchanged Table 4 caveat |
| Evaluation: Commonsense macro | table4_eval_exp: Commonsense macro (%) - plans passing every CS check | % | higher | Queries; raw CS all-pass plans / N |
| Evaluation: Logical micro | table4_eval_exp: Logical micro (%) - share of all personal constraints passed (pooled) | % | higher | Pooled reference PCs; passed / total |
| Evaluation: Logical macro | table4_eval_exp: Logical macro (%) - plans passing every personal constraint | % | higher | Queries; all reference PCs pass / N |
| Evaluation: All-pass ratio | table4_eval_exp: All-pass ratio (%) - schema + CS + PC all passed | % | higher | Queries; schema AND CS AND PC pass / N |
