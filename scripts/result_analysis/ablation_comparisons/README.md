# Ablations & Comparisons (offline)

Reads generated TEST reporting and saved trajectory artifacts. Never executes
experiments, scores plans, invokes models/verifiers, rebuilds matrices, or imports
Streamlit. The frontend reads generated CSV/JSON; it does not compute metrics.

## Canonical comparisons

| Left → Right | Visible label | Meaning |
| --- | --- | --- |
| R0 → R2 | R0 vs R2 — Rollback protection | Mechanism / ablation-like comparison |
| R1 → R3 | R1 vs R3 — Editing-scope flexibility | Mechanism comparison; scheduled widening |
| R3 → R4 | R3 vs R4 — Advanced repair strategies | Strategy comparison — not a matrix ablation |
| R0 → R4 | R0 vs R4 — Matrix-guidance comparison | Intended matrix-guidance comparison, qualified by empirical validity |

**R0 is the no-matrix baseline; R4 is the matrix-guided strategy.** The fourth
pair requires only the existing R0 and R4 TEST runs. No additional run is needed.
Its question is: “What changes when moving from the R0 no-matrix baseline to the
matrix-guided R4 strategy?”

**Delta = Right - Left**, so the fourth pair uses **R4 - R0**. Values are read at
existing source precision; saved tables are not unrounded. Every metric records
its unit, denominator, known-value N and direction (`higher`, `lower`, or
`descriptive`). Positive is not automatically better.

## CLI

Run from the repository root:

```bash
.venv/bin/python -m scripts.result_analysis.ablation_comparisons.build_ablation_comparisons \
  --r0 experiments/subset_test-r0 \
  --r1 experiments/subset_test-r1 \
  --r2 experiments/subset_test-r2 \
  --r3 experiments/subset_test-r3 \
  --r4 experiments/subset_test-r4 \
  --test-reporting-dir test_result_analysis \
  --analysis-dir results/analysis/repair_strategies/test \
  --output-dir results/analysis/ablation_comparisons
```

The only run inputs are `--r0` through `--r4`; each is optional. Omit unavailable
runs. Missing R0 or R4 makes the fourth comparison explicitly unavailable, without
TRAIN or another strategy being substituted. All five use the same reporting
root. For final runs, replace the input paths and regenerate the same outputs;
no frontend registration or copying is needed.

`--comparison r0_vs_r4_matrix` builds one pair; the option can repeat. Default is
all four. `--matched-query-subset` explicitly requests intersection analysis.
`--repository-root` resolves recorded relative provenance. Output directories
must be separate from inputs. Use `--help` for the full interface.

## Inputs and authoritative definitions

- Full common summaries read Tables 1–4 verbatim from
  `scripts/result_analysis/build_test_result_tables.py` outputs. An explicit
  intersection calls its pure `table_pc`, `table_cs`, `table_process`, and
  `table_eval_exp` on saved per-query records. Neither scoring nor `build_queries`
  runs. Missing columns/rows remain unavailable.
- Reporting must bind to an unambiguous README strategy section, exact source
  path/run ID, all six CSVs, and unique manifest UIDs/strategy. Difficulty comes
  from saved `group` values (`easy`, `medium`, `human`), not UID prefixes.
- Proposal metrics use `scripts.analyze_repair_strategies.load_run/build_tables`,
  its strategy hooks, and shared `compute_attempt_metrics`. `--analysis-dir`
  checks bound generated diagnostic provenance when available; read-only shared
  helpers also accept the saved source logs directly. Legacy TRAIN evidence is
  never substituted for TEST diagnostics.
- R4 selection metrics reuse `scripts.repair_analysis_r4.build_tables`, which
  validates the recorded selected outcome and considered pool. TRAIN matrix
  provenance reuses `audit_matrix`, including its documented line-ending hash
  equivalence rules. No matrix is rebuilt.

The common catalog below is unchanged. PC benchmark cells use Table 1, corrected
CS cells Table 2, costs/process Table 3, and evaluation Table 4. Candidate-loop
regressions/net change remain separate from accepted-state events. New standard
CS violations/net standard-CS check change stay unavailable because loop error
messages do not supply check-level transitions. The strict >85% CS row requires
a matching consistent denominator. Complete-token means, completeness and
lower-bound tokens retain their separate definitions. Table 4 CS micro retains
the raw evaluator exception-column caveat; it is not corrected Table 2 CS share.

## Validity and causal-language safeguards

Every checklist item is `pass`, `fail`, or `unknown`. Missing metadata is never
an agreement. Checks cover populations/counts, per-UID difficulty, recorded initial
plans, model/config, nominal/effective budget, scheduler, verifier/evaluator,
implementation, benchmark source/query identities, language, translation mode,
seed, source-run identity and intended strategy pairing.

- **Incompatible / blocked**: required TEST input absent/invalid, mismatched
  populations (without explicit subset mode), conflicting difficulty, wrong
  strategy pairing or duplicate source paths. No paired headline delta.
- **Descriptive comparison only**: query cohorts match, but other controls
  differ or remain unknown. No causal interpretation.
- **Matched strategy comparison**: recorded compatibility/component controls
  agree, but complete component-isolation evidence is absent. No causal claim.
- **Controlled ablation**: reserved for the R0/R4 comparison when all controls
  pass and a complete snapshot proves that matrix guidance is the only intended
  treatment difference. Role names alone never establish this classification.

The fourth pair additionally checks explicit enabled/disabled treatment metadata,
verified TRAIN-only R4 matrix provenance, absence of positive guidance in R0 logs,
and recorded equivalence for:

- `repair_prompt_without_guidance_hash`
- `repair_logic_without_guidance_hash`
- `repair_scope_policy`
- `acceptance_behavior_hash`
- `structural_guard_policy_hash`
- `candidate_generation_hash`
- `selection_behavior_hash`

Common/component metadata may be top-level or in `comparison_controls` (or the
existing `compatibility.config`). A controlled classification also requires both
manifests to record `ablation_settings_complete: true` and matching
`ablation_settings` snapshots after removing only `matrix_guidance_enabled`.
Snapshots include the component controls above, model/config, max steps,
scheduler, common repair implementation, verifier/evaluator, benchmark identity,
language, translation, seed and `other_settings` covering all remaining settings.
These are contracts for future experiments; analysis never edits current manifests
to obtain a stronger classification.

With explicit `--matched-query-subset`, labels state **Matched-query subset** and
retain original N, matched N and excluded UIDs. The original table helpers
aggregate that saved-query slice. Different original populations prevent a
controlled classification. Every displayed difficulty requires matching,
nonempty UID cohorts on both sides.

## Actual R0/R4 implementation audit

The saved fourth-pair validity output includes a read-only repository audit:

| Component | Repository evidence |
| --- | --- |
| Prompt/repair logic | R0 uses `BACK_PROMPT`; R4 reuses the R3 prompt contract and appends advisory matrix guidance. |
| Scope | Both request whole-plan repair; R4 explicitly selects PLAN rather than inheriting the R3 widening schedule. |
| Scheduler | Shared loop is intended; executed scheduler-version equality needs recorded metadata. |
| Acceptance | Both inherit default acceptance. R4's structural filter acts before acceptance and can return the previous plan; it is not R2 rollback. |
| Candidate generation | R0 prefixes/repairs response JSON; R4 uses R3 parsing plus structural checks. |
| Structural guards | R4 checks `_structure_problem` and can return an unchanged proposal; R0 lacks that R3 guard path. |
| Selection | R4 has a separate least-unresolved post-hoc selection over initial/candidate outcomes. Common benchmark metrics still use the final accepted trajectory for both strategies. |
| Verifier/model/budget/initial plans/population | Recorded checklist values qualify implementation equivalence; missing configuration is not treated as equal. |

Sources: `repair_strategies/r0.py`, `r3.py`, `r4.py`, `base.py`, the shared repair
loop, `r4/select_outcomes.py`, and final-accepted export code. Audited source files
are fingerprinted. Current repository observations do not prove which code a
historical run executed; recorded run/component controls are also required.

Current runs differ in initial-plan identities and implementation hashes, and
recorded R0/R4 model configuration differs. Several controls are unrecorded.
Therefore R0/R4 is **Descriptive comparison only**.

## Mechanism evidence

Existing mechanism definitions remain unchanged: R0 candidate/accepted regression
counts; R2 protected True→False harm, rejection and verified raw-plan retention;
R1 recorded localization/actual failure reasons/footprint; R3 observed scheduled
scope reaches/transitions and distinct candidate/accepted target fixes; R4 logged
support/unsupported cells, guards, validated considered pool and post-hoc choices.
Independent trials are not joined. Post-hoc selection never rewrites benchmark
or accepted-loop endpoints.

Only in the fourth comparison, R0 gets explicit **Not applicable** entries for
matrix guidance/support, R4 structural guards and post-hoc selection diagnostics.
Their numeric value is blank and `unit`/denominator are `Not applicable`, not zero.
The dashboard renders and exports that distinction. R0 proposal/outcome metrics
remain measured where applicable. R4 retains its existing numeric diagnostics and
adds the existing `r4_fallbacks.has_unsupported_relationship` count to distinguish
proposals with any unsupported cell from wholly unsupported guidance. Missing
R4 evidence is unavailable, not N/A and not fabricated zero.

## Generated outputs and refresh

```
results/analysis/ablation_comparisons/
  r0_vs_r2/{summary.csv,mechanism.csv,validity.json,metadata.json}
  r1_vs_r3/{summary.csv,mechanism.csv,validity.json,metadata.json}
  r3_vs_r4/{summary.csv,mechanism.csv,validity.json,metadata.json}
  r0_vs_r4_matrix/{summary.csv,mechanism.csv,validity.json,metadata.json}
  comparison_metrics.csv
  mechanism_metrics.csv
  index.json
  README.md
```

`summary.csv` contains tidy comparison/type/cohort/difficulty/run identities,
metric values/delta, unit/direction, cohort and known-value counts, source,
denominator, validity and availability reason. Mechanism rows retain run/side,
metric/value, evidence N, source, denominator and units. The other three pairs'
numerical results are unchanged.

The CLI retires the obsolete generated comparison folder during regeneration.
Root tidy outputs contain the requested canonical pairs only. Metadata records
command/time, source paths/run IDs, source/code hashes and output checksums.
The frontend rejects stale or edited outputs until CLI regeneration; no check is
weakened or replaced by an in-memory calculation. CSVs are deterministic for fixed
inputs/code; metadata timestamps differ. After final runs, regenerate existing
TEST tables/diagnostics, run this CLI, and click **Refresh local data** (or restart
Streamlit). There is no frontend edit or manual file-copy step.

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
