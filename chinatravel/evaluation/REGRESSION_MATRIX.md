# Regression matrices (Phase 3B)

This module aggregates existing `RepairAttemptRecord` data offline. It does not
run models, infer repair targets, change normalization/taxonomy, split data, or
change any repair or verifier behavior. Results describe personal constraints
only and are observational associations, not causal dependency estimates.

## Eligibility and formula

Source family `i` is eligible only for an attempt with exactly one explicit
`target_constraint_indices` entry. That 1-based target must exist, have state
exactly `False` before repair, and have a descriptor whose Phase 3A classification
is `mapped`. Missing, unmapped, ambiguous, or compound sources are excluded.
R0 now declares its False personal feedback targets at repair time with
`r0_failed_feedback` provenance. Empty legacy target lists still stay empty;
there is no matrix-time all-failures fallback. Invalid records (including
out-of-range targets) fail validation.

Every descriptor is classified. Only mapped instances form destination family
`j`. Its contribution is eligible only if at least one such instance exists,
**all** mapped instances were exactly `True` before, and **all** their candidate
after states are known. `None` is unknown, never PASS or FAIL. One unknown after
state excludes the entire family contribution, even if another member fails.
Descriptors not present are not guessed; classification/missing-descriptor
exclusions are retained in the audit. The population is the **mapped instances**,
not an assertion that all raw constraints of the same real-world family were
recognized. Mapping coverage must be reported with the matrix.

The diagonal is structurally ineligible. It appears as an excluded contribution
but is omitted from long aggregates and left blank in pivots.

Let `E[a,i,j]` indicate eligible attempt `a` for pair `(i,j)` and let `R[a,j]`
indicate at least one destination member is False in the proposed candidate.
For each strategy `s`:

```text
M_candidate[s,i,j] = sum(E[a,i,j] * R[a,j]) / sum(E[a,i,j])
M_accepted[s,i,j]  = sum(E[a,i,j] * R[a,j] * accepted[a]) / sum(E[a,i,j])
```

Both sums run over attempts of that strategy. A denominator of zero yields
`None` (blank CSV), never zero. An eligible attempt contributes at most one count
per cell regardless of how many destination instances regress. Rejected
proposals remain in both denominators and the candidate numerator; they cannot
contribute an accepted regression. Do not filter the accepted population to
accepted attempts. Unknown-outcome exclusions make the estimate conditional on
evaluable outcomes; their counts are exposed separately.

## Candidate is the primary cross-strategy view

The **candidate matrix** asks: "When this strategy proposes a repair targeting
family i, how often does the proposal break a previously satisfied family j?"
It is the main comparison of proposed repair behavior across strategies.

The **accepted matrix** asks: "How often does such a regression actually enter
the continuing accepted trajectory?" It is a system safeguard/outcome measure.
Low accepted regression for R2 is not evidence its proposals are intrinsically
safer: rollback can force accepted regression toward zero. Candidate harm remains
observable. These remain observed repair-regression associations, not causal
dependencies.

The primary matrix is strict single-target; multiple-target attempts remain in
coverage/contributions but are excluded from directional attribution. Concurrency
and scope fields never silently change primary eligibility. An isolated personal
target means exactly one target and exactly one concurrent personal failure;
commonsense failures may still coexist, so isolation does not establish causality.

## Python API and identity

```python
build_regression_matrix(records, run_id="default")
# {"contributions": [...], "aggregate": [...], "coverage": {...}}

build_contribution_table(records, run_id="default")
summarize_matrix_coverage(records, run_id="default")
aggregate_contributions(contributions)
```

Inputs are record objects, serialized dictionaries, or envelopes:

```python
{"run_id": "R2-model-seed-run", "repair_attempt": serialized_record}
```

An attempt identity is `(run_id, query_uid, step)`. Use different run IDs for
different strategies, seeds, or repetitions. Identical repeated records are
deduplicated and reported; conflicting data for that identity raises `ValueError`.
Contribution identity adds `(perspective, source_family, destination_family)`.
The aggregate helper independently deduplicates contribution keys, rejects
conflicts, and rejects mixed/unsupported definition versions.

Missing query UIDs are preserved as `None` and excluded from distinct query
counts. Supply unique run IDs for unidentified query runs; records colliding at
the same run/None/step cannot safely be treated as separate attempts. `run_id`
is caller/file provenance, not an inferred identifier in the record.

## Flat output schemas

`matrix_contributions.csv` columns:

```text
run_id, query_uid, step, repair_strategy, source_constraint_index,
source_family, destination_family, perspective, eligible, regression,
accepted, exclusion_reason, target_provenance, target_mapping_status,
descriptor_exclusions, taxonomy_version, normalizer_version,
matrix_definition_version, target_count, concurrent_failed_count,
concurrent_commonsense_failure_count, feedback_personal_constraint_count,
feedback_commonsense_failure_count, editable_scope, scope_level,
protected_constraint_count, escalation_reason, is_single_target,
is_isolated_personal_target, has_concurrent_commonsense_failure
```

One row per attempt, destination family and perspective is emitted, including
excluded attempts with no source family. `regression` is `None` when ineligible.
`descriptor_exclusions` is a JSON string listing indices, classification status,
and reasons for excluded/missing descriptors. Scope, provenance, feedback and
concurrency come from canonical record fields, migrated on read when old records
stored intent in metadata. Feedback counts and concurrent commonsense presence
remain `None` when unavailable; explicitly empty feedback has count 0.
`has_concurrent_commonsense_failure` is True/False for known counts, otherwise
None. Scope is slot/day/plan or unavailable (None/blank), never `unknown`.

Exclusion precedence is source validity, diagonal, absent mapped destination,
destination not all PASS before, then unknown candidate after. Source reasons
are `zero_targets`, `multiple_targets`, `source_not_false`, and
`source_{unmapped,ambiguous,compound,missing_descriptor}`. Destination reasons are
`structurally_ineligible_diagonal`, `destination_family_absent`,
`destination_not_all_pass_before`, and `destination_unknown_after`.

`regression_matrix_long.csv` columns:

```text
repair_strategy, perspective, source_family, destination_family,
regression_count, eligible_count, regression_rate, support_attempts,
support_queries, unknown_after_excluded_attempts, taxonomy_version,
normalizer_version, matrix_definition_version, counting_unit, target_policy
```

For each observed strategy this contains every off-diagonal family pair, in
both perspectives, including zero-support cells with unavailable rates.
`support_attempts` counts distinct eligible attempt identities and equals
`eligible_count`. `support_queries` counts distinct non-null query UIDs among
eligible attempts, across runs. Repeated attempts from one query are not
independent observations. Definition/taxonomy versions are `1.0.0`, while
normalizer version is imported from Phase 3A. `counting_unit=repair_attempt` and
`target_policy=single_explicit_failed_target`.

## Secondary scope-conditioned matrix

`regression_matrix_by_scope_long.csv` has the same aggregate columns, with
`editable_scope` after `repair_strategy`. It uses the exact same contribution
rows and eligibility, grouped separately by strategy, scope, perspective and
family pair. Missing scope forms an explicit None/blank group and is counted
in coverage; it is never assigned to slot/day/plan. This secondary view can
compare R3's scopes without changing or replacing the primary strategy-level
matrix. The Python result adds `aggregate_by_scope`; both views share one
aggregation implementation. Diagonals and zero-support rates remain unavailable.
No additional scope pivots or changed-slot/edit-footprint metrics are introduced.

## Coverage audit

`matrix_coverage.json` reports deduplicated attempts:

```text
total_repair_attempts
duplicate_records_ignored
zero_target_attempts
single_target_attempts
multi_target_attempts
target_mapping: {mapped, unmapped, ambiguous, compound}
target_missing_descriptor_instances
source_target_not_false_attempts
attempts_missing_descriptors
missing_descriptor_instances
missing_query_uid_attempts
destination_unknown_after_excluded_contributions
destination_unknown_after_excluded_attempts
candidate_eligible_contributions
accepted_eligible_contributions
distinct_query_count
taxonomy_version
normalizer_version
matrix_definition_version
```

`target_mapping` counts **target instances**, including those in multi-target
attempts; missing target descriptors have a separate count. Source-not-False
counts single-target attempts. Missing descriptors counts uncovered verifier
positions, not an empty list on a query with no personal constraints.
Unknown-after counts apply after source and PASS-before eligibility: contributions
count destination pairs once (not twice for two perspectives); attempts count
distinct attempts having any such pair. Eligible contribution counts are by
perspective and must match. No-target/multi-target attempts are retained in
coverage even though excluded from directional inference.

Phase 4.1 also retains these global coverage counts and reports them in
`by_strategy` and `by_strategy_scope` row lists:

```text
isolated_single_target_attempts
single_target_with_other_personal_failures_attempts
concurrent_commonsense_failure_attempts
missing_target_provenance_attempts
missing_editable_scope_attempts
```

Each breakdown includes total/zero/single/multi-target attempts, mapping-status
counts (target instances), eligible candidate/accepted contributions, unknown-after
exclusions, missing descriptors and distinct query counts. Missing scope has an
explicit `editable_scope: null` row in the scope breakdown; it is not pooled with
a known scope. Missing commonsense counts do not count as observed failures;
their contribution Boolean remains unavailable. Coverage describes the supplied
trajectories only; representativeness is unestablished without real trajectories.

## CLI

```bash
python scripts/build_regression_matrix.py \
  --input attempts.jsonl history.json \
  --output-dir artifacts/matrices/r2 \
  --run-id R2-model-seed-run \
  --repair-strategy R2
```

JSONL accepts serialized records or run/record envelopes. JSON accepts shared
history lists, `{ "history": [...] }` loop results, or single records. Step-0
verification is skipped; later entries must have formal `repair_attempt` records.
Legacy histories are rejected rather than silently losing proposals.

`--run-id` overrides all input run identities. Otherwise envelopes may supply
run IDs; fallback IDs are hashes of resolved input paths, stable for the same
location. Use explicit run IDs to deduplicate overlapping exports in different
files or preserve identity after moving files. An optional exact strategy filter
is applied before aggregation. Multiple remaining strategies raise an error
before writing, since one pivot pair cannot represent multiple strategies
without pooling. The Python API keeps strategies separate in its long table.

Six files are produced: `matrix_contributions.csv`, `regression_matrix_long.csv`,
`regression_matrix_by_scope_long.csv`, `regression_matrix_candidate.csv`,
`regression_matrix_accepted.csv`, and `matrix_coverage.json`.
Pivot rows are source families, columns are destination families; unavailable
and diagonal cells are blank, while observed zero regression rates are `0.0`.
Empty input produces header-only long tables, blank pivots, and zero coverage.

No train/test enforcement is performed. Choose the intended input partition
externally; inspect strict single-target and classification coverage before
interpreting a sparse matrix.

For the exact per-strategy intent contract, see
[Metadata required from repair strategies](REPAIR_ATTEMPTS.md#metadata-required-from-repair-strategies).
Target selection and editable scope are independent. Changed-slot/edit-footprint
analysis is intentionally deferred until stable activity identities are agreed.
