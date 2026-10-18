# Repair metrics

`compute_attempt_metrics(record)` accepts a record or serialized dictionary and
returns a flat row. `summarize_repair_history(history)` summarizes step 0 plus
formal repair-attempt entries. Neither calls models or verification.

| Attempt metric | Definition |
| --- | --- |
| `failed_before_count`, `passed_before_count` | Exact False and True counts |
| `fixed_count` | False -> True transitions |
| `newly_violated_count` | True -> False transitions |
| `repair_success_rate` | Fixed / failed before |
| `targeted_repair_success_rate` | Explicit failed targets fixed / explicit failed targets |
| `new_violation_rate` | Newly violated / passed before |
| `net_repair_gain` | Fixed minus newly violated |
| `candidate_all_personal_constraints_pass` | Nonempty all-True candidate; None for empty vector |

Zero denominators yield `None`. Unknown states count as neither passes nor
failures and cannot be fixes/regressions. Missing targets are not inferred.
Accepted-trajectory metrics use candidate changes only when accepted; rejected
proposals contribute zero accepted changes, retaining their candidate effects.

Run summaries reconstruct the accepted state from step 0 and accepted attempts.
They reject inconsistent before states, steps, or mixed run identities. Final
personal satisfaction is True / (True + False), excluding unknowns; no known
states yields None. An all-personal-pass flag requires a nonempty all-True
vector. It does not establish overall itinerary validity.

Totals count transitions, including repeated repairs of a constraint. Mean rates
are unweighted means of defined attempt rates; no defined values yields None.
Each token channel is totaled only when all attempts supply it. Combined tokens
require both channels; missing usage/time remains None with completeness flags.
An initial-only history has zero repair totals, complete empty usage data,
undefined rates, and unavailable query/strategy identity. Initial-generation
costs are separate. `attempt_count=1` is not a model-call count; `model_calls=None`.

See the [record contract](REPAIR_ATTEMPTS.md), [storage](REPAIR_COMPARISON.md),
and [matrix methodology](REGRESSION_MATRIX.md).
