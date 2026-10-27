## R0/R4 matrix-guidance comparison revision

The canonical fourth pair is now **R0 vs R4 — Matrix-guidance comparison**,
left R0 (no-matrix baseline), right R4 (matrix-guided strategy), delta R4 − R0.
The CLI accepts only R0–R4. Registry, adapters, missing-run checks, metadata,
examples and tests no longer require an additional run. Regeneration retires the
obsolete generated folder and writes `r0_vs_r4_matrix/`; root tidy/index outputs
contain exactly the four current pairs. A retired browser selection maps to the
new fourth pair. Previous generated refresh-audit sidecars were archived under
`/tmp/ablation-comparison-previous-refresh-audit/` rather than left as current data.

The fourth page shows intended question versus empirical validity, compatibility
checks and a read-only implementation audit. All existing common metrics retain
their source definitions. R0 matrix-only diagnostics are explicitly Not applicable,
not zero, while R4 uses logged support, guards and validated outcome-pool/selection
evidence. Candidate/accepted/benchmark/post-hoc endpoints remain distinct. The
other three pairs' summary and mechanism CSVs are byte-for-byte unchanged.

Current R0/R4 validity is **Descriptive comparison only**: populations match at
30/30/30, but recorded initial identities and implementation/configuration differ,
and several controls are unknown. Repository code also shows distinct prompts,
parsing and structural guards, plus R4 post-hoc selection. Both use whole-plan
scope. The page displays the recorded validity classification. Controlled status additionally requires recorded equivalence for prompt/
logic excluding guidance, scope, acceptance, guards, candidate generation and
selection, existing common controls, correct treatment/provenance, and a complete
matching settings snapshot. Missing isolation evidence cannot produce a causal label.

Current availability: R0/R2, R1/R3, R3/R4 and R0/R4 all available, each N=30 on
both sides and matched N=30; all are descriptive comparisons only. Reproduction
uses the five current TEST run paths documented in the CLI/dashboard READMEs.

Validation: 18 standalone comparison tests, 9 comparison-page tests, and 48 existing
analysis tests pass. Full dashboard suite: 142 passed and 2 pre-existing errors
out of 144, both expecting the legacy PC 2+ failure source row while the current
team builder emits separate 2 and 3+ bins. This unrelated definition/source issue
was not altered or hidden. All four real-data comparison views, existing pages,
startup/imports, compilation, exact other-pair CSV parity and whitespace checks pass.
All experiment artifacts, existing TEST reporting/strategy-analysis outputs, TRAIN
matrices/analysis, repair/verifier/evaluator implementations remain unchanged.
No model/API calls, commits or pushes.

## Ablations & Comparisons revision

Added the seventh page, ordered Overview, Query Explorer, TRAIN set, TEST set,
Ablations & Comparisons, Strategy-Specific, Examples. The new page reads generated
CSV/JSON only. It shows pair questions, validity/checklists, difficulty-specific
common results and Right − Left deltas, distinct mechanism evidence, downloads,
one supplementary chart, definitions, and reproduction commands/provenance.

New offline package: `scripts/result_analysis/ablation_comparisons/`, with CLI,
input adapters, validity rules, metric catalog and documentation. It reuses the
original TEST table cells/pure reporting helpers, original strategy analyzer and
hooks, shared transition metrics, R4 selection tables and TRAIN matrix audit.
No scorer, experiment, verifier or model is run. Existing source helpers and
metric definitions are unchanged. Explicit matched-query subset mode records
original/matched counts and exclusions. Missing controls downgrade validity;
contradictory populations/difficulty/treatment block deltas. Only fully controlled
matrix guidance comparisons license causal interpretation.

Generated outputs live under `results/analysis/ablation_comparisons/`: one folder
per predefined pair, each with summary.csv, mechanism.csv, validity.json and
metadata.json, plus root tidy metric/mechanism CSVs, index and README. Inputs,
analysis code and generated outputs are hashed; the frontend rejects stale or
edited results rather than recomputing them on rerun.

Current canonical availability uses R0/R2, R1/R3, R3/R4 and R0/R4. The fourth
pair is the intended matrix-guidance comparison, with R0 as baseline. All current
pairs are descriptive; standard-CS new/net transition metrics remain unavailable.
R4 post-hoc choices stay separate from final accepted benchmark trajectories.

Validation: 15 standalone comparison tests, 141 dashboard tests, and 48 existing
analysis tests pass. CLI smoke, all four comparison selections, all six existing
pages, actual app startup, imports/compilation, source-cell parity, Right − Left
parity, and whitespace checks pass. All 2,572 pre-existing protected source and
artifact files remain unchanged; only the explicitly requested new analysis
package was added within scripts/. No model/API calls, commits or pushes.

See `dashboard/ABLATION_COMPARISONS.md` and the offline package README for the
complete source catalog, control metadata contract, limitations, output schema,
current commands and future final-run commands.

## Navigation labels and order revision

Validation: 135 dashboard tests and 48 existing analysis tests pass. Actual app
startup, imports, compilation and whitespace checks pass. Exact navigation labels,
order, stable routes and all six headings are covered by tests. Protected source
and experiment artifacts (2,572 files) remain unchanged. No commits or pushes.

Top navigation and page headings now read, in order: Overview, Query Explorer,
TRAIN set, TEST set, Strategy-Specific, Examples. `PAGE_SPECS` keeps the visible
ordering explicit. Existing module URL paths (Overview at the root) are preserved.
UI cross-references, README order/filter policy, and navigation/headings tests are
updated. Only presentation, tests and documentation changed; page dataset bindings,
comparison safeguards, canonical examples, diagnostic filters, numerical metrics
and experiment artifacts are preserved.

## Canonical representative examples revision

Validation: 133 dashboard tests (including 15 canonical-example tests) and 48
existing analysis tests pass. All six pages render with real data. The final
canonical page has five populated selections and Markdown exports, with no
exceptions. Compilation/import and whitespace checks pass. All 2,572 protected
source/artifact files remain unchanged, with no additions. No model/API calls,
commits or pushes were made.

Replaced manual example-type/partition/strategy filters with four automatically
bound canonical sections and an R4 contrast subsection. `example_selection.py`
selects from independent checkpoint trajectories. The component loads only saved
matrices, contributions, difficulty labels and selection artifacts. No aggregate
metrics, scoring functions or experiment/source artifacts are changed.

Detection and source details are documented in `EXAMPLES_REPORTING.md`.
R2 requires the logged regression rejection reason and raw-plan preservation.
R3 narratives describe fixed scheduled widening. R4 supported examples require
logged cells matching the frozen TRAIN matrix with recorded hash agreement
(allowing only LF/CRLF variants); post-hoc selection is separately identified.
Missing or ambiguous evidence stays unavailable. Markdown exports contain the
same selected trajectory and states displayed in the section, plus its heading.

Current automatic defaults (not hard-coded into the application):

| Category | Partition / strategy | Query UID | Attempt |
| --- | --- | --- | --- |
| Interdependency | TRAIN R0 | e20241028160908981620 | 1 |
| Protection | TEST R2 | e20241028161340383778 | 1 |
| Widening | TEST R3 | e20241028160914767827 | 3 |
| Supported guidance | TEST R4 | e20241028160902013119 | 1 |
| Structural guard contrast | TEST R4 | m20241028164916356794 | 1 |

All categories currently have qualifying examples. Qualifying proposal counts:
2 TRAIN cascades, 11 R2 rollbacks, 15 R3 sequences, 11 supported R4 repairs,
164 R4 limitation proposals. These are selection inventory counts, not new
aggregate performance metrics or independent sample sizes.

## Page-scoped navigation revision

Validation: 117 dashboard tests and 48 existing analysis tests pass. Six additional
local-navigation checks passed after strengthening the matrix-family assertion.
All six pages and the app entry point render against real data; all four report
summary frames equal the corresponding saved CSV frames. Compilation/imports and
whitespace checks pass. 2,572 protected source/artifact files are unchanged, with
no additions. No model/API calls, commits or pushes were made.

Removed the global Repair-analysis explorer title and dataset/strategy/proposal
controls. Top navigation is persistent and contains only the six page links.
`page_context.py` owns explicitly scoped diagnostic selectors with distinct widget
keys; the app passes only discovered runs. TRAIN matrices use TRAIN R0–R3,
TEST Tables 1–4 use TEST reporting, Strategy-Specific uses TEST. Query Explorer
and Examples default to TEST with their own local partition controls. Overview
summarizes both partitions. Refresh remains in the sidebar.

Table selectors/downloads, source bindings, formulas and saved numerical cells
are unchanged. TEST set discards any stale supplied global filters. Matrix
family/support controls and candidate-transition explanations now live on their
relevant pages. Synthetic fixtures include the upstream builder's newly required
`error_reply_rounds=0`; no builder changes were made. The token lower-bound
row also accepts both the old and newly renamed upstream labels; this is a label
adapter only and preserves the exact saved value.

# Table-first ChinaTravel Evaluation revision

The fourth TEST tab is now ChinaTravel Evaluation, with the same independent
Difficulty × Strategy main-table architecture as Tables 1–3. It includes a metric
bar chart, five-metric strategy profile, difficulty profile and optional saved
query-level counts/results. No Table 4 repair-round view is added.

Changed files in this revision: new `dashboard/components/evaluation.py`,
`dashboard/metrics.py`, shared `components/reporting.py` (optional filtered-summary
callback), `components/common.py` (optional precision, existing default retained),
`dashboard/pages/test_results.py`, new
`dashboard/tests/test_evaluation_reporting.py`, new `EVALUATION_REPORTING.md`,
README.md and this report. Tables 1–3 source rows, metrics and default display
behavior are unchanged.

Exact source: `test_result_analysis/<strategy>/table4_eval_exp.csv`, generated by
`build_test_result_tables.py:table_eval_exp()` using benchmark per-query fields.
Final accepted plan exports go through evaluate_repair_run.py to
`eval_exp.py:evaluate_final_plans` and schema/commonsense/hard-logic evaluators.
Unfiltered source cells are read directly; filtered cohorts use the existing pure
report helper on saved rows, never trajectory scores or benchmark recomputation.

Definitions and footnote:

- Commonsense micro pools raw CS matrix cells, including an exception column when
  present. The documented exception/unmarked-check inflation caveat is shown as *.
- Commonsense macro counts raw all-CS-success plans / evaluated plans.
- Logical micro pools passing reference hard_logic_py personal constraints over
  the actual total reference constraints, not the mean of query percentages.
- Logical macro counts plans passing every reference personal constraint / plans.
- All-pass counts schema ∩ CS ∩ logical success / plans. It is definitionally
  different from CS macro even when current numerical values coincide.

All are already percentages; no extra ×100 conversion is applied. Exact formulas,
source rows, handling of missing/error results, aggregation, footnote provenance
and relationships to Tables 1/2 are documented in
[EVALUATION_REPORTING.md](EVALUATION_REPORTING.md) and the UI definition expander.
The literal historical asterisk is not encoded in the generated CSV; the displayed
footnote explicitly uses the existing reporting documentation's raw-micro caveat.

Query detail exposes only saved raw CS counts, PC counts, schema/All-pass flags
and the report helper's zero-failure criteria. Missing fields remain Unavailable;
no query result is reverse-engineered from aggregate scores. Filtered Table 4
results fail closed if required saved evaluator fields are incomplete. Population,
partition, run/report binding and provenance/freshness safeguards remain active.

Validation: **110 dashboard tests passed**, **45 existing analysis tests passed**.
Real-data Table 4 rendering/source values, compilation/import and whitespace checks
passed. **2,566 protected source/artifact files** remain unchanged, with no additions
to protected trees. Tests include exact CSV-cell parity, percentage formatting,
missing/future R0/R1, arbitrary cohorts, filters/profiles/downloads, missing fields,
query population blocking, pooled logical micro, raw exception handling, and a
counterexample where CS macro passes but All-pass fails. All prior Table 1–3 tests
pass. No model/API calls, evaluator-definition changes, commits or pushes occurred.

The reports below describe preceding revisions.

---

# Table-first TEST process revision

Repair Process / Efficiency now uses the same Difficulty × Strategy architecture
as PC and CS. It independently loads bound reporting runs, including future R0/R1,
with matching-population guards, outcome details, separate token/time charts,
dynamic round tables/comparison and secondary process counters. Downloads use the
exact active display dataframe.

Changed files: `dashboard/components/repair_process.py`, shared
`components/reporting.py`, the delegation wrapper in `components/cs.py`,
`dashboard/pages/test_results.py`, `dashboard/metrics.py`, new
`dashboard/tests/test_process_reporting.py`, new `PROCESS_REPORTING.md`, README.md
and this report. Existing PC/CS calculations are unchanged.

Main source: `test_result_analysis/<strategy>/table3_repair_process.csv`, or the
original `table_process()` helper on saved per_query.csv for filtered cohorts.
Exact row mappings and every diagnostic denominator/missingness rule are in
[PROCESS_REPORTING.md](PROCESS_REPORTING.md) and the UI source expander.

Complete-token query means, missing-token rounds and all-query lower bounds remain
separate. Missing usage is never presented as genuine zero cost. Low completeness
has an explicit below-80% presentation warning. Changed-round PC deltas retain
positive-improves and CS-error deltas retain negative-improves, comparing candidate
verification against the preceding accepted state, including rejected candidates.

Changed/cache/other classification reuses the original round_data() helper. Its
three categories form the exclusive split; recorded model-call failure flags can
overlap it. Cache hits skip only the matching exact repeated request; no whole-round
zero-call/cost-savings claim is made. The reporting residual unchanged_other does
not itself prove a new request or actual model dispatch.

The main model-call-failure percentage is Unavailable because Table 3 has no such
established source row. Separate logged-counter failure diagnostics require
complete coverage; missing classification/counters/tokens remain unavailable.
Universal benchmark CS fix/regression identities are not invented or duplicated
from message diagnostics.

Validation: **95 dashboard tests passed**, **45 existing analysis tests passed**.
Real-data rendering of Tables 1/2/3 and the current R4 token-coverage warning passed;
compilation/import and whitespace checks passed. **2,566 protected source/artifact
files** remain byte-identical, with no protected-tree additions. Existing PC and
CS regression tests all pass. No model/API calls, experiment edits, numerical
metric-definition changes, commits or pushes were made.

The reports below describe preceding revisions.

---

# Table-first TEST CS revision

TEST set → Commonsense Constraints now mirrors the PC reporting structure:
Difficulty × Strategy comparison, exact saved failure-label attribution, loop
round diagnostics, round-wise strategy comparison and filtered CSV downloads.
Both PC and CS views load available reporting runs independently of the sidebar
single-strategy/difficulty selectors.

Files changed in this revision:

- `dashboard/components/cs.py`: table-first CS sections and query-population guards.
- New `dashboard/components/reporting.py`: shared cohorts, controls, compatibility
  warnings and charts; `components/pc.py` delegates to it without PC value changes.
- `dashboard/pages/test_results.py`: mounts both comparison tabs even when the
  sidebar-selected run lacks reporting.
- `dashboard/data_loader.py`: shared reporting-discovery entry point with a
  backward-compatible PC wrapper; binding checks are unchanged.
- `dashboard/metrics.py`: shared pivots and round alignment plus documented CS
  summary/failure-attribution/message-diagnostic presentation helpers.
- New `dashboard/tests/test_cs_reporting.py`: CS-specific fixtures and regressions.
- New `dashboard/CS_REPORTING.md`, README.md and this report: exact source mappings,
  unavailable metrics, failure-attribution denominators and validation.

Sources audited before implementation: `table2_cs.csv`, `per_query.csv`, and the
original `table_cs()` helper in build_test_result_tables.py. Existing passed-count/
rate and 2+ final-failure summaries reuse pc_cs_extras(). No full CS family-rate
CSV/helper exists upstream. Exact per-query failure labels are expanded with
explicit attributable-plan denominators; evaluator exceptions are excluded from
category attribution while still counted as failing all standard checks in the
main benchmark table.

Unsupported round check pass/fix/regression metrics remain Unavailable: histories
contain error messages, not check denominators/identity transitions. Additional
explicitly named message diagnostics reuse accepted trajectory reconstruction.
The chart includes Initial, dynamically observed rounds and Final where values
are defined, and leaves missing cells unconnected. Selected CS comparisons with
different difficulty-specific query populations are blocked, without silently
intersecting cohorts or substituting TRAIN.

Metric-by-metric source/definition mappings, including every unavailable row, are
in [CS_REPORTING.md](CS_REPORTING.md) and the UI sources expander.

Validation: **79 dashboard tests passed**, **45 existing analysis tests passed**.
Real-data rendering of both comparison tables/charts, compilation/import checks
and whitespace checks passed. **2,566 protected existing source/artifact files**
remain unchanged, with no additions to protected source/artifact trees. No model/
API calls, original numerical-definition changes, commits or pushes occurred.
All prior PC tests pass, and explicit regression tests confirm its pivot cells and
round/chart behavior are unchanged after shared-helper extraction.

The reports below describe preceding revisions.

---

# Table-first TEST PC revision

TEST set → Personal Constraints now starts with the report-ready
Metric × difficulty/strategy table. Its local controls default to all observed
difficulties and all canonically bound TEST reporting strategies. Available runs
remain visible even if the sidebar-selected run lacks reporting. Missing/future
R1 support is data-driven.

Changed in this revision: `dashboard/components/pc.py`, `dashboard/pages/test_results.py`,
`dashboard/data_loader.py`, `dashboard/metrics.py`, `dashboard/tests/test_refresh.py`,
new `dashboard/tests/test_pc_reporting.py`, README.md, this report and new
[PC_REPORTING.md](PC_REPORTING.md).

Main-table numeric cells come from table1_pc.csv or the unchanged team table_pc
summary helper over saved per_query.csv when filtering query cohorts. The
initially-perfect-and-unchanged subset is not relabelled as all initially-perfect
queries; the broader requested row remains Unavailable. Failure types reuse
table1b_pc_failure_by_kind.csv or the original table_pc_kinds helper for slices.
Round tables use accepted loop-verifier evidence and shared accepted metrics,
separately labelled from benchmark endpoint reporting. The round comparison chart
uses the same cells as its numerical table and leaves missing rounds unconnected.

The source mapping and every row's interpretation/denominator are documented in
PC_REPORTING.md and in the PC tab's sources expander. No benchmark scoring or
alternative metric definitions were introduced.

Validation: **59 dashboard tests passed**, **45 existing analysis tests passed**;
compilation, actual repository PC rendering and whitespace checks passed. The
2,566 protected existing source/artifact files remain byte-identical. No model/API
calls, experiment edits, metric-definition changes, commits or pushes occurred.

The report below describes the preceding refresh implementation.

---

# Future-run refresh implementation report

The dashboard now loads final R0–R4 TEST outputs without source edits, strategy
registration or artifact copies into dashboard/. Existing numerical definitions
and source artifacts were left unchanged.

## Files changed in this revision

- `dashboard/data_loader.py`: manifest-based discovery; partitioned diagnostics with
  provenance-checked legacy fallback; stricter reporting binding; provenance and
  source-hash visibility; manifest-aware checkpoint cache invalidation.
- `dashboard/metrics.py`: added UI availability, observed-round and support-bound
  helpers. Existing metric calculations/definitions are unchanged.
- `dashboard/app.py`: data-derived controls and refresh accessible even when runs
  are unavailable.
- `dashboard/pages/overview.py`: dynamic R0–R4 availability and query populations.
- `dashboard/pages/test_results.py`, `dashboard/components/common.py`: provenance,
  unavailable-binding reasons and explicit freshness limitations.
- `dashboard/tests/test_dashboard.py`: replaced live snapshot assumptions with
  fixtures; all five TEST strategies are exercised.
- New `dashboard/tests/fixtures.py`, `dashboard/tests/test_refresh.py`: synthetic
  persisted evidence and future-run/refresh tests.
- `dashboard/README.md`, `dashboard/DATA_AUDIT.md`, this report: workflow and scope.

## TRAIN/TEST coexistence and discovery

Preferred diagnostics are `results/analysis/repair_strategies/train/R0`–`R3` and
`.../test/R0`–`R4`. The existing analyzer CLI supports these separate output-dir
values without modification. Legacy per-strategy outputs remain readable only
when bound to the selected source path, run ID and available attempt checksum.
No legacy artifacts were moved, copied, regenerated or removed.

Run discovery reads immediate `experiments/*/run_manifest.json` files, validates
partition/strategy/population and checks for persisted artifacts. Directory names
need not begin with subset. Nested archives are not traversed. Multiple valid
runs remain selectable; no arbitrary source is silently treated as latest.

All temporary availability assumptions have been removed from runtime messages
and tests. R0–R4 remain the supported strategy schema. Round IDs come from observed
steps, including checkpoint histories when the attempt stream is empty. Support
bounds come from persisted matrix/guidance values and include pooled TRAIN counts.
Empty support disables the slider safely.

## Reporting and freshness

Common TEST tables still come exclusively from build_test_result_tables.py and
its pure summary helpers. Binding requires exact strategy labels, the generated
README's source path and run ID, every required reporting file, and an exact,
unique query population/strategy match.

A partial builder invocation overwrites combined README notes. Omitted strategies
remain unavailable until all desired runs are regenerated together. This behavior
is documented and intentionally not bypassed.

Provenance shows source paths, run IDs, generated paths, query populations/counts
and recorded generation timestamps. Missing generation timestamps remain
Unavailable. Analysis source checksums are checked for listed files. Reports
without checksum evidence explicitly display:

“Source freshness cannot be cryptographically verified.”

Identity matching alone is never described as freshness verification.

## Validation

- Dashboard tests: **45 passed** using isolated persisted fixtures.
- Existing analysis tests: **45 passed**.
- Actual repository Streamlit import/Overview smoke: passed.
- Local Streamlit server startup: passed, then stopped; telemetry disabled.
- Compilation and git diff --check: passed, including explicit whitespace checks
  for untracked dashboard files.
- **2,566 protected existing source/artifact files** verified unchanged by SHA-256;
  no additions in the protected experiment/analysis/reporting/matrix/code trees.

Coverage includes all R0–R4 becoming available, availability UI updates, cohorts of
1/11/47 queries, observed rounds beyond six, support above 500, empty controls,
TRAIN/TEST coexistence and CLI generation, guarded legacy fallback, wrong-source/
population rejection, partial README regeneration, provenance limitations,
manifest cache invalidation, refreshed numerical tables/figures/downloads and
checkpoint reloads. UI tests block benchmark scoring/build-query entry points.

Validation used installed system Streamlit with project dependencies on PYTHONPATH
because the existing project environment lacks Streamlit. Installing
requirements-dashboard.txt in one environment supports the normal commands.
The localhost startup smoke used approved port access; no provider was contacted.
No model/API calls, metric-definition changes, commits or pushes were made.

## Final workflow and remaining limits

Exact commands are in README.md, under “Data discovery and final-run workflow”:
final runs → evaluate_repair_run.py → all-strategy common TEST table generation →
separate TRAIN and TEST analyzer output directories → Refresh local data.
The documented final-directory names are examples; pass actual source paths to
the existing upstream commands. No frontend registration/configuration is needed.

Remaining limits are upstream schema compatibility, one bound common reporting
set per strategy, one bound diagnostic set per partition/strategy, and the TEST
builder's lack of checksum/generation metadata. Its origin mapping must cover
all final query IDs. Finish writing artifacts before refreshing. The dashboard
does not redefine upstream budget semantics or infer missing measurements.
