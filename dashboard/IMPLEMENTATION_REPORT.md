# Table-first TEST CS revision

TEST Results → Commonsense Constraints now mirrors the PC reporting structure:
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

TEST Results → Personal Constraints now starts with the report-ready
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
