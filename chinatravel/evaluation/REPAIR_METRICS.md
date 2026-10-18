# Central repair metrics

`repair_metrics.py` exposes two pure functions, returning flat dictionaries for
CSV or JSONL. They do not run verification, call models, or change repair policy.

```python
compute_attempt_metrics(record)       # RepairAttemptRecord or its serialized dict
summarize_repair_history(history)     # shared loop's history list
```

## Candidate versus accepted trajectory

Candidate regression is **PASS before proposal -> FAIL in proposed candidate**.
Accepted regression is **PASS in accepted trajectory -> FAIL after an accepted
repair**. A rejected proposal retains all its candidate fixes and regressions,
but contributes zero accepted fixes, regressions, and net gain. Accepted rates
for rejection are zero when their denominator exists, otherwise `None`.

For each attempt:

| Metric | Definition |
| --- | --- |
| `failed_before_count` / `passed_before_count` | Exact False / True counts before the proposal |
| `fixed_count` | Count of False -> True transitions |
| `newly_violated_count` | Count of True -> False transitions |
| `repair_success_rate` | Fixed / failed before |
| `targeted_repair_success_rate` | Explicit targets changing False -> True / explicit targets False before |
| `new_violation_rate` | Newly violated / passed before |
| `net_repair_gain` | Fixed minus newly violated |
| `candidate_all_personal_constraints_pass` | All candidate states True, or None for an empty vector |

Rates with zero denominators are `None`. Targets are 1-based; missing targets
remain absent and yield `None` for targeted success. General success needs no
target metadata. Accepted metrics use the same definitions after rollback.
`None` constraint states count as neither PASS nor FAIL, and never as fixes or
regressions. A nonempty vector containing any None cannot pass the all-pass check.

## Run summaries

The initial state comes from step-0 `verification.personal_constraints`. Only
accepted attempts replace that state. Candidate totals include rejected
proposals; accepted totals exclude their effects. Totals count transitions,
so a constraint repaired more than once can contribute more than once.
Mean rates are unweighted means of defined attempt rates; undefined values are
excluded, and no defined observations yields `None`.

Final satisfaction is True count / known (True + False) count. No known states
yields `None`. Final all-personal-pass requires a nonempty all-True vector;
an empty vector yields `None`. These cover **personal constraints only**, not
overall itinerary validity, commonsense checks, schema checks, or other errors.

The summary validates increasing steps, matching entry/record steps, consistent
query/strategy identities when available, and continuity of before states with
the accepted trajectory. Missing records are rejected rather than silently
dropping attempts. Legacy histories without formal records need conversion.
Identity comes from records; an initial-only history returns `None` for query
and strategy because step 0 does not contain them.

## Efficiency and missing data

Input/output deltas are preserved. Their total is defined only when both are
available. Each run-level token channel is summed only if every attempt supplies
that channel; otherwise its total is `None`. `token_data_complete` is true only
when both channels are complete. Missing usage is never replaced by zero.
Repair time follows the same completeness rule, with `timing_data_complete`.
Durations cover repair calls only, not verification or initial generation.

For zero attempts, sums are zero and completeness is vacuously true: no repair
usage is required. Acceptance and mean rates remain undefined. These totals do
not measure initial-generation or whole-query usage, and present counters do not
guarantee the provider reported every billed token.

Each attempt contributes `attempt_count=1`, with `accepted` encoded as 0/1.
`model_calls=None` at both levels: there is no reliable structured model-call
counter, and an attempt may contain multiple calls. Attempt count is not model
call count.
