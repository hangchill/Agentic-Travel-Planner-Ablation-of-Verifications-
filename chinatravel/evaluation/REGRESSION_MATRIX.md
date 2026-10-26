# Regression matrix methodology

For a repair targeting source family i, measure whether a previously satisfied
destination family j becomes violated. This is an observed repair-regression
association, not causal dependency. Families come from the deterministic
[constraint normalizer](CONSTRAINT_FAMILIES.md).

## Primary eligibility

An attempt contributes only when:

1. Exactly one personal target is declared.
2. That original 1-based target was False before repair.
3. Its descriptor maps unambiguously to source family i.
4. Destination family j has at least one mapped instance.
5. Every mapped j instance was True before repair.
6. Every corresponding candidate-after state is known (not None).
7. i != j; diagonals are structurally excluded.

A regression occurs if **any** eligible destination instance is False afterward.
Each attempt counts at most once per family pair, even if several instances fail.

### Source families

The source axis is the 9 personal `CONSTRAINT_FAMILIES` plus one extra
`commonsense_repair` row (10 source rows in all; matrix definition version
`2.1.0`). A `commonsense_repair` source is a changed (non-no-op) attempt with
`repair_phase == "commonsense"` and no personal target; the unchanged-attempt
exclusion still runs first, so commonsense no-ops are dropped. Destination
columns remain the 9 personal families. `commonsense_repair` is never a
destination column, so the diagonal exclusion never fires for it and all 9
destinations are candidate columns. Rules 2, 3 and 7 (single mapped personal
source, source False before, i != j) apply to the personal source rows only;
rules 4-6 (destination mapped, True before, known after) apply to every source.
Missing/unmapped/ambiguous/compound descriptors are not guessed. Eligibility
covers mapped instances, not necessarily every real-world requirement. Unknown
after states exclude the whole destination contribution, even if another member
fails. Multi-target attempts stay logged but are excluded from directional
attribution. Labels/provenance, scope, and concurrent failures do not change
these eligibility rules. Old empty R0 targets are never inferred at analysis time.

For each strategy s and eligible population E(s,i,j):

```text
candidate rate = count(candidate regression) / count(E)
accepted rate  = count(candidate regression AND accepted) / count(E)
```

The **candidate matrix** reports proposed repair harm for each strategy.
The **accepted matrix** measures harm entering the continuing trajectory. Rejected harmful proposals remain in both denominators and only the
candidate numerator. Low accepted harm for R2 may reflect rollback rather than
safer proposals. Zero support is None/blank, not zero. Observed zero harm is 0.0.
Unknown exclusions and mapping coverage must accompany interpretation. Repeated
attempts from a query are correlated; support counts do not establish independence.

The **secondary scope-conditioned matrix** uses exactly the same contributions
and eligibility, grouped by strategy, editable scope and perspective. Missing
scope is an explicit None/blank group, never slot/day/plan. No edit-distance or
changed-slot analysis is performed.

## API, identity and audit

`build_regression_matrix(records, run_id="default")` returns `contributions`,
`aggregate`, `aggregate_by_scope`, and `coverage`. Inputs may be record objects,
serialized dictionaries, or `{run_id, repair_attempt}` envelopes.
`build_contribution_table()`, `aggregate_contributions()` and
`summarize_matrix_coverage()` expose the same operations separately.

Attempt identity is (run_id, query_uid, step); contribution identity adds
perspective and source/destination family. Identical duplicates count once;
conflicts raise. Use separate run IDs for strategies/seeds/repetitions. Missing
UIDs remain unavailable and are excluded from distinct-query counts.

Flat contributions contain identities, source index/families, perspective,
eligibility, regression/acceptance, exclusion reasons, definition versions, and
canonical scope/provenance/feedback/concurrency/protection audit fields. Excluded
regression values are None. `descriptor_exclusions` is a JSON string. Exact
column names are in `CONTRIBUTION_COLUMNS` and `AGGREGATE_COLUMNS`.

Aggregates report counts/rate, distinct eligible attempts and non-null queries,
unknown-after exclusions and versions. `support_count == eligible_count == support_attempts`. The new `support_count`
field is an explicit denominator alias; the existing fields are retained.
Coverage reports zero/single/multi targets, target mapping statuses (instance
counts), missing descriptors/provenance/scope, isolated/concurrent failures,
eligible contributions, unknown-after exclusions and query counts, globally and
by strategy/scope. Unknown exclusions count eligible-source/PASS-before family
pairs once, not twice for perspectives. Coverage is not evidence of population
representativeness.

## CLI and outputs

```bash
python scripts/build_regression_matrix.py \
  --input attempts.jsonl --repair-strategy R0 --output-dir artifacts/matrix-r0
```

Accepted inputs are serialized JSONL records/envelopes, flat paired-runner streams,
CSV exports of full attempt records (non-string values JSON encoded; blank nullable
cells mean None),
and JSON histories with formal attempt records (step 0 is skipped). Histories
without records are rejected. Explicit `--run-id` overrides input identity;
otherwise supplied IDs or stable file-path hashes apply. Paired streams use
strategy-specific `matrix_run_id`. Use explicit identities for overlapping exports
or moved files. Multiple strategies require a filter for the two pivot outputs.

Outputs:

- `matrix_contributions.csv`
- `regression_matrix_long.csv` — primary strategy-level matrix
- `regression_matrix_by_scope_long.csv` — same columns plus `editable_scope`
- `regression_matrix_candidate.csv` and `regression_matrix_accepted.csv` — pivots
- `matrix_coverage.json`

Pivots retain blank unsupported/diagonal cells. Empty input yields header-only
long tables, blank pivots and zero coverage. No train/test selection is performed.
See the [strategy contract](REPAIR_ATTEMPTS.md) and [paired runner](REPAIR_COMPARISON.md).


### Paired rate and count exports

The CLI retains both legacy rate pivots and adds these aligned CSVs:

- `candidate_regression_rate.csv`
- `candidate_regression_support.csv`
- `candidate_regression_count.csv`
- `accepted_regression_rate.csv`
- `accepted_regression_support.csv`
- `accepted_regression_count.csv`

The same six files are written under `by_scope/<editable_scope>/` for each
observed scope (`unspecified` for missing scope). Source families are rows and
destination families are columns, with identical ordering in every file.
Support and regression counts are zero for unsupported cells and the structurally
excluded diagonal; their rates are blank. Positive support with no regressions
has rate `0.0`. Long tables retain all existing columns and add `support_count`.
Counts remain repair-attempt opportunities, not constraint-instance counts.
Multi-target attempts remain in contributions/coverage but add neither count.
Rejected candidates retain the existing accepted-trajectory denominator and
contribute zero accepted regressions; candidate regressions remain observable.

```python
from chinatravel.evaluation.regression_matrix import load_regression_matrix

matrix = load_regression_matrix(output_directory, perspective="candidate")
cell = matrix["trip_specification"]["monetary_budget"]
# {"rate": 0.4, "support_count": 5, "regression_count": 2}
```

Pivots and `load_regression_matrix` return 10 source rows (the 9 personal
families plus `commonsense_repair`) over 9 destination columns, e.g.
`matrix["commonsense_repair"]["monetary_budget"]`.

Pass a scope subdirectory to load scoped matrices, or `perspective="accepted"`
(`"accepted_trajectory"` also works). The loader validates matching axes and
count/rate consistency, returns `None` for missing rates, and supplies no risk
scoring policy. It requires the new paired exports; rebuild older exports from
existing records to use it. Existing rate filenames remain supported unchanged.
