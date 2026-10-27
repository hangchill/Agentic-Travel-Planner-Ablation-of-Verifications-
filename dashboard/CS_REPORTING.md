# Table 2: Commonsense Constraints reporting

The CS tab follows the PC tab's table-first structure: main difficulty × strategy
comparison, failure types, accepted-loop round diagnostics, round-wise strategy
comparison and CSV downloads. PC and CS share discovery, cohort filters, controls,
pivot construction, tables/downloads and chart utilities. PC numeric definitions,
row mappings and round/chart behavior are unchanged.

## Audit and source of truth

Audited `scripts/result_analysis/build_test_result_tables.py` before implementation.
Its corresponding CS outputs are:

- `test_result_analysis/<strategy>/table2_cs.csv`: standard benchmark failed-check
  summaries, query changes, exact final failure bins, strict >85% threshold count,
  evaluator exceptions and top-three failure-check text.
- `per_query.csv`: `cs_total`, `cs_passed_initial`, `cs_passed_final`,
  `cs_failed_checks_final`, `cs_evaluator_exception_initial/final` and raw benchmark
  fields. Corrected Table 2 fields are used here, not the raw Table 4 micro/macro.
- `merged/table2_cs.csv`: existing combined static view; the dashboard pivots the
  bound per-strategy sources so its active filters and availability remain current.

The builder's `table_cs()` remains the authority for its existing rows. For a
filtered cohort the dashboard calls that same pure helper on saved per-query rows.
It never calls `build_queries()`, `score_plans()` or an evaluator. The existing
`dashboard.metrics.pc_cs_extras(..., 'cs')` helper supplies already-established
passed-count/rate summaries and the 2+ final-failure bin.

The builder has no `table2b` full CS failure-kind CSV and no full CS failure-kind
rate helper. It does provide exact failure-check labels in `per_query.csv` and a
`table_cs()` top-three summary via `top_three(Counter(...))`. The failure-family
view below expands those persisted labels without inventing a taxonomy.

## Main comparison metric mapping — benchmark evidence

Group columns are Easy / Medium / Human / All; Medium is displayed as Med. All
available observed difficulties and bound reporting strategies are selected by
default. Query-change rows are **query counts**, despite referring to pass shares.

| Displayed metric | Source file/helper | Exact underlying definition |
|---|---|---|
| Avg CS per query | per_query.csv / cs_reporting_summary | Mean saved cs_total standard check count |
| Avg CS failed: initial | table2_cs.csv / table_cs | Avg CS checks failed per query - initial plan |
| Avg CS failed: final | table2_cs.csv / table_cs | Avg CS checks failed per query - final plan |
| Avg CS passed: initial | per_query.csv / pc_cs_extras | Mean cs_passed_initial |
| Avg CS passed: final | per_query.csv / pc_cs_extras | Mean cs_passed_final |
| Avg CS passed: change | table2_cs.csv | Negative of Avg CS checks failed per query - change (final - initial; negative = fewer failures) |
| Avg % CS passed: initial | per_query.csv / pc_cs_extras | Mean 100 × cs_passed_initial / cs_total |
| Avg % CS passed: final | per_query.csv / pc_cs_extras | Mean 100 × cs_passed_final / cs_total |
| Avg % CS passed: change (pts) | pc_cs_extras outputs | Final mean passed percentage minus initial mean passed percentage over the same cohort |
| Queries: % CS passed increased | table2_cs.csv / table_cs | Queries where failed CS checks decreased (improved) |
| Queries: % CS same | table2_cs.csv / table_cs | Queries where failed CS checks stayed the same |
| Queries: % CS decreased | table2_cs.csv / table_cs | Queries where failed CS checks increased (got worse) |
| Final plans: 0 failed CS | table2_cs.csv / table_cs | Final plans with 0 failed CS checks |
| Final plans: 1 failed CS | table2_cs.csv / table_cs | Final plans with 1 failed CS check |
| Final plans: 2+ failed CS | per_query.csv / pc_cs_extras | Existing 2+ bin: cs_total - cs_passed_final >= 2 |
| Final plans with >85% CS passed | table2_cs.csv / table_cs | Existing dynamic “Final plans with at most … failed CS checks (more than 85% of the … checks passed)” row |
| % final plans with >85% CS passed | per_query.csv / pc_cs_extras | Existing strict >0.85 final pass-share percentage |

Each row above is a benchmark result or a documented presentation summary of saved
benchmark counts. No scoring or replacement benchmark definition is introduced.
The original negative failed-count change is sign-reversed only because the new
label asks for passed-count change. Source rounding of that row is preserved.

The threshold is strictly greater than 85%, not greater-than-or-equal. With the
current 28 checks, at most four failures qualify. With 20 checks, 17/20 does not
qualify and 18/20 does. The upstream helper assumes a common check count when it
constructs its threshold row. Both requested threshold values stay Unavailable if
check totals vary in the source cohort, the row's logged denominator disagrees,
the source threshold changes from 85%, or the exact threshold row is missing.
Directly sourced missing rows remain Unavailable; they are not independently
recreated from another definition. Derived rows with missing required saved
counts likewise remain Unavailable.

Evaluator exceptions count as failing **every standard check** in Table 2 and the
saved corrected passed counts. The raw evaluator-exception column used by Table 4
is not silently included as an extra standard check here.

## Failure-family view — benchmark label attribution

“CS family” preserves each exact saved `cs_failed_checks_final` label, including
original spellings. No schedule/travel/opening-hours grouping is inferred or
renamed. The source is per_query.csv; the display helper is cs_failure_families().

| Displayed field | Definition |
|---|---|
| CS family | Exact semicolon-delimited saved failure-check label |
| Failure count | Attributable plans listing that label, at most once per plan |
| Attributable plans (N) | Known nonexception plans with complete, consistent label evidence, including known zero-failure plans |
| Failure rate (%) | 100 × failure count / attributable plans, only when those plans have a common standard check count |

The reporting builder leaves category labels blank for evaluator exceptions.
Although the main table counts every check failed for those plans, their blank
labels do not identify actual failed categories. They are excluded from family
attribution, never counted as passes. Missing/inconsistent label evidence and
unknown exception flags are also excluded. A blank label with a saved zero-failure
count is a known passing observation and belongs in the denominator. Failure
attribution coverage explicitly shows included/excluded query counts for each
strategy and difficulty. If no attribution is possible, the family table stays
Unavailable; rates remain Unavailable if check totals do not support a common
category opportunity population.

This is a new documented display summary because no upstream full family-rate
helper exists. It does not replace the existing Table 2 check-count metrics or
its exception policy. Family rates have an explicitly narrower denominator than
the main benchmark cohort. Only observed nonzero failure labels are listed;
zero-failure category names cannot be inferred from blank strings. The top view
shows up to three rows per strategy from the same filtered family table, rather
than ranking incompatible cohort counts against each other.

## Outcomes by repair round — Loop-verifier diagnostics

Sources are saved `queries/*/<strategy>-*.json` or `queries/*/trials/*.json`:
initial_verification, repair_history and final_verification, with attempts.jsonl
for proposal identities/activity. Existing trajectory() reconstruction supplies
accepted CS errors and message-set changes. Rejected candidates never advance the
accepted state. R4 post-hoc selections do not replace trial final states.

Loop error messages are **not** benchmark check-category outcomes. Histories do
not log the denominator of CS checks passing or failed check-identity vectors.
Therefore the following requested check-level rows are Unavailable in every
Initial/round/Final column: Mean CS pass rate, Mean # CS passed, Mean # CS failed,
% rounds fixing >=1 CS, Avg # CS fixed, % rounds introducing >=1 new CS violation,
Avg # new CS violations, Avg net CS change and New CS violation rate. A count of
messages is not relabelled as the number of failed constraints, and a disappearing
message is not claimed to prove a benchmark check was fixed.

The table additionally provides these supported, explicitly named diagnostics:

| Displayed diagnostic | Source / existing definition |
|---|---|
| Mean # CS error messages | Mean length of the accepted commonsense_errors list; Initial/Final from saved checkpoint verification |
| % rounds removing >=1 CS message | Share of defined accepted CS messages removed values >0 ×100 |
| Avg # CS messages removed | Mean existing trajectory() CS messages removed: distinct before messages absent from accepted-after list |
| % rounds introducing >=1 CS message | Share of defined accepted CS messages introduced values >0 ×100 |
| Avg # CS messages introduced | Mean existing trajectory() CS messages introduced: distinct after messages absent before |
| Avg net CS message reduction | Mean unique messages removed minus mean unique messages introduced |
| # queries still active (observed) | Existing PC round/activity convention: distinct selected UIDs with a later persisted proposal |
| % queries still active (observed) | That count / selected reporting cohort size ×100 |
| Observed CS states (N) | Number of known accepted CS error lists at that column |

Message-list counts can include repeated messages; event set differences count
unique strings, as the existing trajectory helper does. Missing error lists stay
unknown and are not replaced by empty lists. Event metrics have no Initial/Final
values. Initial observed-active counts refer to queries with any persisted
proposal; Final activity cells are Unavailable. Observed activity is not evidence
of the scheduler's actual active/stopped state.

Only dynamically observed step IDs are shown. No stopped query or absent round is
forward-filled. Independent trial checkpoints are not concatenated. State/event
means use defined observations; active percentages use the selected cohort size.

## Round-wise comparison, chart and safeguards

The selector retains all requested check-level metrics (Unavailable when logs do
not support them), plus clearly named supported message diagnostics. It defaults
to Mean CS error messages so the initial chart uses observable evidence. Activity
is also available. The numerical Strategy × Initial/round/Final table is primary;
the supplementary categorical line chart uses those exact cells. Missing values
remain unconnected. Unsupported metrics produce an explanation instead of a
fabricated chart. Neither Initial nor Final event values are invented.

CS comparisons are blocked when selected strategies have different filtered query
UID populations for a displayed difficulty. A user can select matching strategies
or inspect a single run. Difficulty-group populations are checked separately;
there is no silent intersection, population dropping, or TRAIN substitution.
Model/settings/initial-plan incompatibilities retain the shared descriptive
comparison warnings. Reporting/run binding and provenance/freshness safeguards
remain unchanged, including the explicit lack-of-checksum warning.

All main/family/round CSV downloads use their currently displayed dataframes.
Main Difficulty × Strategy filtering is independent of the sidebar's single-run
selection. Sidebar proposal filters select query cohorts; their complete observed
trajectories remain available for round views, as on the PC page.
