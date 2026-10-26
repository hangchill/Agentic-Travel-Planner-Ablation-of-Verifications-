# TEST PC reporting sources and interpretation

The Personal Constraints tab now starts with one cross-strategy table. Available
canonical TEST reporting bindings determine strategy columns; no TRAIN tables are
substituted. The sidebar-selected strategy does not restrict this PC table.
Choose Difficulty and Strategies above the table. The default shows every
observed difficulty plus All, and every strategy with bound reporting outputs.
Medium columns use the presentation label Med. Columns for absent strategies or
empty difficulty populations are omitted. CSV download uses the currently
presented dataframe, not the unfiltered or merged source snapshot.

## Main comparison table

Every numerical main-table cell is read from
`test_result_analysis/<strategy>/table1_pc.csv`, retaining the original Easy,
Medium, Human and All columns. Presentation aliases below do not redefine metrics.
When sidebar UID/phase/round/family/outcome filters select a smaller query cohort,
the dashboard reuses the original builder's `table_pc()` function on that run's
saved `per_query.csv`. PC difficulty controls remain independent of the sidebar
single-strategy/difficulty selectors. Proposal filters select whole-query cohorts;
round views retain complete observed trajectories for those cohorts.

| Displayed row | Exact generated table1_pc.csv row |
|---|---|
| Avg PC per query | Avg personal constraints per query |
| Avg PC failed: initial | Avg PC failed per query - initial plan |
| Avg PC failed: final | Avg PC failed per query - final plan |
| Avg PC passed: initial | Avg PC passed per query - initial plan |
| Avg PC passed: final | Avg PC passed per query - final plan |
| Avg PC passed: change | Avg PC passed per query - change (final - initial) |
| Avg % PC passed: initial | Avg % PC passed per query - initial plan |
| Avg % PC passed: final | Avg % PC passed per query - final plan |
| Avg % PC passed: change (pts) | Avg % PC passed per query - change (percentage points) |
| Queries: % PC passed increased | Queries where % PC passed increased |
| Queries: % PC same | Queries where % PC passed remained the same |
| Queries: % PC decreased | Queries where % PC passed decreased |
| Queries: all PC pass at start | Unavailable: no equivalent generated summary row |
| Final plans: 0 failed PC | Final plans with 0 failed PC |
| Final plans: 1 failed PC | Final plans with 1 failed PC |
| Final plans: 2+ failed PC | Final plans with 2+ failed PC |
| All PC passed, excl. named-place | Final plans passing all PC, excluding named-place constraints |
| Avg % PC final, excl. named-place | Avg % PC passed per query - final plan, excluding named-place constraints |

The three query-change rows are counts of queries, despite their references to
pass percentages. The existing `of which already 100% in the initial plan` row
counts only queries initially passing all PCs whose result also remained the same.
It is a subset of all initially-perfect queries and is deliberately not relabelled
as the requested broader metric. The broader row stays Unavailable; it is not
recomputed or inferred from a different definition. Missing exact source rows
likewise remain Unavailable, including in future generated tables.

## Final PC failures by constraint family

The unfiltered whole-cohort source is
`test_result_analysis/<strategy>/table1b_pc_failure_by_kind.csv`:

| Displayed column | Source column |
|---|---|
| PC family | kind |
| Failure count | failed |
| Total constraints | total |
| Failure rate (%) | failure_rate_pct |

Here “PC family” retains the reporting builder's existing PC-kind taxonomy. It is
not the matrix structural-family taxonomy. Rates are failed constraints divided
by total constraints of the same kind, rather than percent of queries failing.

For difficulty/query-cohort slices, use saved `per_query.csv` plus
`benchmark_eval/<strategy>-*/evaluation_population.json` reference constraints,
calling the original builder's `table_pc_kinds()` function. No evaluator runs and
no alternative classifier is introduced. If reference data is unavailable,
sliced failure-kind metrics stay Unavailable. Strategy selection above also
filters this section; Failure difficulty and PC families are additional controls.
The compact top view sorts the same filtered rows by count then failure rate and
shows at most five nonzero rows. It does not pool or double-count strategy cohorts.

## PC outcomes by repair round

There is no generated benchmark-by-round table. The round sections therefore show
explicitly labelled **accepted loop-verifier diagnostics**; benchmark values from
the main table are never inserted into the loop trajectory. Initial and Final are
saved checkpoint verification states, not post-hoc R4 selections.

Persisted sources:

- `experiments/<run>/queries/*/<strategy>-*.json`, or `queries/*/trials/*.json`:
  initial_verification, repair_history and final_verification.
- `attempts.jsonl`: candidate/accepted vectors and proposal identities.
- A provenance-matched `.../<partition>/<strategy>/attempt_level.csv`, or legacy
  equivalent, supplies existing shared metric columns where available. Otherwise
  the unchanged `compute_attempt_metrics()` helper reads the persisted attempts.

| Displayed round metric | Persisted field / existing definition |
|---|---|
| Mean PC pass rate (%) | Accepted vector True/(True+False), macro mean ×100; all-UNKNOWN undefined |
| Mean # PC passed | Mean True count of accepted vectors |
| Mean # PC failed | Mean False count of accepted vectors; UNKNOWN separate |
| % rounds fixing >=1 PC | Share of defined accepted_fixed_count values >0 ×100 |
| Avg # PCs fixed | Mean accepted_fixed_count |
| % rounds introducing >=1 new PC violation | Share of defined accepted_newly_violated_count values >0 ×100 |
| Avg # new PC violations | Mean accepted_newly_violated_count |
| Avg net PC change | Mean accepted_net_repair_gain |
| New-violation rate (%) | Mean defined accepted_new_violation_rate ×100 |
| # queries still active (observed) | Distinct selected query UIDs with a later observed proposal |
| % queries still active (observed) | That count / selected cohort query count ×100 |
| Observed queries (N) | State vectors observed at that column; round rows use observed proposals only |

The existing new-violation rate denominator is the number of PCs passing before a
proposal; it is different from the proportion of rounds introducing any violation.
Rejected R2 candidates do not change accepted-state counts or accepted fix/
regression events. Event metrics have no Initial/Final values. Initial active
counts refer to queries with any observed proposal; Final activity cells are
Unavailable. Observed activity is not proof of scheduler status.

Round columns use actual step IDs, including gaps or steps beyond six. No stopped
query is forward-filled. Missing or ambiguous independent query/trial states are
not merged into one trajectory. State means and event means use their available
observations; the selected cohort size is the active-percentage denominator.

Round-wise comparison pivots these same numeric cells to Strategy × observed round
for the chosen metric and difficulty. The supplementary line chart uses exactly
the comparison table's long-form round cells. It plots observed round points only,
leaves missing strategy/round cells unconnected, and does not invent Initial/Final
event values. Different populations/settings/initial plans produce descriptive
comparison warnings instead of a controlled-performance claim.
