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
In particular, empty R0 target metadata stays empty; there is no all-failures
fallback. Invalid records (including out-of-range targets) fail validation.

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
matrix_definition_version
```

One row per attempt, destination family and perspective is emitted, including
excluded attempts with no source family. `regression` is `None` when ineligible.
`descriptor_exclusions` is a JSON string listing indices, classification status,
and reasons for excluded/missing descriptors. `target_provenance` comes from
`repair_metadata` when present; structured values are encoded as JSON strings.

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

Five files are produced: contributions and long aggregates above,
`regression_matrix_candidate.csv`, `regression_matrix_accepted.csv`, and coverage.
Pivot rows are source families, columns are destination families; unavailable
and diagonal cells are blank, while observed zero regression rates are `0.0`.
Empty input produces header-only long tables, blank pivots, and zero coverage.

No train/test enforcement is performed. Choose the intended input partition
externally; inspect strict single-target and classification coverage before
interpreting a sparse matrix.
