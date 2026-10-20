# Repair metrics

`compute_attempt_metrics(record)` returns a flat attempt row;
`summarize_repair_history(history)` supplies query/strategy summaries to
`summaries.csv`. Formal records in `attempts.jsonl`, with the saved step-0
verification for initial/final state metrics, reproduce these results.

| Metric | Definition | Level | Missing-value behavior |
| --- | --- | --- | --- |
| `repair_success_rate` | False -> True fixes / False before | Attempt; defined-rate run mean | None for zero denominator |
| `targeted_repair_success_rate` | Explicit targets False before and True after / explicit targets False before | Attempt; pooled run ratio | None if no eligible targets; invalid indices rejected safely |
| `new_violation_rate` | True -> False regressions / True before | Attempt; defined-rate run mean | None for zero denominator |
| `net_repair_gain` | Fixed minus newly violated | Attempt; cumulative run total | Unknown transitions contribute neither |
| Accepted effects | Candidate changes only on acceptance | Attempt/run | Rejected proposals contribute zero accepted changes |
| `repair_success`, `attempts_until_success` | Accepted verifier `passed`; attempts consumed until first accepted pass | Run | None without recorded verified success/state |
| `changed_slot_count`, `total_comparable_slots`, `changed_slot_rate` | Changed structural day/activity positions, including nested transport | Attempt/run | None for malformed/unavailable plans; empty union has undefined rate |
| `repair_model_calls`, `verification_model_calls`, `model_calls` | Observed HTTP dispatches in repair, verification, whole attempt | Attempt; run sums | None for uninstrumented/external clients |
| `failed_model_calls` | Model-endpoint HTTP errors or transport exceptions | Attempt; run sum | None without dispatch tracking |
| Input/output/total token deltas | Provider-reported prompt/completion/total usage in the attempt | Attempt; complete run sums | None when any constituent request omits that usage channel |
| `repair_time_seconds` | Monotonic elapsed `repair()` generation time | Attempt; run sum | None on old records |
| `verification_time_seconds` | Monotonic candidate-verification time | Attempt; run sum | 0 if not reached; None on old records |
| `attempt_time_seconds` | Monotonic generation through verification/acceptance or failure | Attempt; run sum | None on old records |
| Attempts, acceptance/rejection | Record counts and acceptance flags | Run | Zero-denominator rates are None |
| Escalation/highest scope | Observed increases between successive scope levels; maximum scope level | Run | None if any scope level cannot be determined |

## Outcomes and scope

Targets are original unique 1-based indices; no targets are inferred. Multi-target
attempts still have targeted-success metrics. None states are neither PASS nor
FAIL and cannot become fixes or regressions. The general repair rate and targeted
rate are distinct. Run targeted success pools eligible target observations;
`mean_targeted_repair_success_rate` is the unweighted mean of defined attempt
rates. Totals can count the same constraint on multiple attempts.

Final personal satisfaction is True / (True + False); no known states yields
None. All-personal-pass requires a nonempty all-True vector and is not overall
itinerary validity. Verified `repair_success` uses the accepted full verifier
outcome, including its commonsense/technical checks.

`rejected_attempts`/`rejection_rate` count all nonaccepted attempts, including
execution failures. `failed_attempts` separates exceptions;
`decision_rejected_attempts` and `decision_rejection_rate` exclude exceptions
and describe completed rejection decisions (R2 rollback when that policy exists).
Per-scope attempt counts include an unavailable bucket. Escalation counts an
observed level increase once, regardless of reason text; it does not infer an
escalation before the first logged attempt. Scope completeness is reported.

## Observed requests, usage and time

`model_usage.py` instruments the shared OpenAI-compatible client's HTTP transport.
Only POST dispatches to chat-completions/responses endpoints count, including SDK
retries and failed dispatches. `__call__`, `chat`, response parsing and strategy
attempts do not increment it, avoiding nested-wrapper double counting. Production
uses the SDK's default HTTP client settings with this transport. Tests use an
HTTP mock transport; no SDK or network is needed. Only synchronous, nonstreaming
calls through the supplied instrumented client are covered. Custom clients must
expose reliable cumulative usage snapshots or remain unavailable.

One normalizer accepts response usage objects or dictionaries and both
prompt/completion and input/output names. Reported total tokens are preserved;
when absent they are derived only if both reported components exist. Every
request missing a channel marks that attempt's channel incomplete, even if a
later retry reports usage. Failed requests do not get invented zero tokens.
Public legacy counters retain observed partial sums; standardized deltas and R0
saved query totals use completeness checks. Before/after counter snapshots are
observed cumulative sums and may be partial; their validated deltas are the
analysis measurements. A total-only provider response can give a known total
while component channels remain unavailable.

Tokens and `model_calls` cover the whole attempt, including verification and any
model-backed acceptance using the same client. Repair/verification call segments
are separate; a total may additionally include acceptance calls. Native shared
verification is symbolic and makes no model calls. Timing excludes persistence
and initial preparation. Rejected candidates retain all costs. Exceptions produce
a rejected record with the error and observed costs before propagation; when
verification was not completed, after states are unknown. Targets may remain
unavailable if the strategy failed before returning intent.

Each run sum requires every constituent value; completeness flags distinguish
missing measurements. Initial-only histories have zero repair totals and
undefined rates. Initial generation/shortlisting calls, tokens and timing are
saved separately in `initial_state.json` generation metadata, once per query,
and never charged once per strategy. `repair_attempt_count != model_call_count`.

## Operational edit footprint

`extract_itinerary_slots` accepts the raw itinerary list or a full plan with an
`itinerary` list. Each day has an explicit positive integer `day` and an ordered,
variable-length `activities` list. The slot key is `(day, zero_based_activity_index)`.
Meals (`breakfast`, `lunch`, `dinner`), attractions, accommodation, trains and
flights are activities. Inner-city transport belongs to the destination activity
and is part of that slot's value, not an additional slot.

Canonical activity values include only observed schema content: type, position,
origin/destination, times, price/cost, tickets, rooms/room_type and TrainID/FlightID.
Nested raw transport dictionaries or translated segment lists retain their
ordered endpoint/mode/time/cost/distance/quantity content. Outer dictionary order,
JSON formatting, surrounding string whitespace, and unrecognized debug metadata
are ignored. Missing transport, `[]` and the prompt's `"empty"` sentinel mean no
transport. Comparisons use structured values, not whole-plan string inequality.

For the union of slot keys, count one change whenever a key is inserted, deleted,
or its canonical value differs. Thus `changed_slot_count = changed union keys`,
`total_comparable_slots = union size`, and `changed_slot_rate = changed / union`.
An empty union has counts 0 and rate None. Malformed/unavailable plans have all
three fields None. This is candidate footprint, including rejected candidates,
against the preceding accepted raw plan. It is independent of `editable_scope`,
which describes intended/permitted scope.

There are no persistent activity IDs in the inspected schema. TrainID/FlightID
identify services, not arbitrary activity instances. This intentionally operational
position metric can count downstream positions after insertion/deletion and counts
reordering as changed positions. It is not a minimal semantic edit distance or a
count of changed entities. Moving an activity to another day changes both keys.
No semantic matching, new plan IDs or schema changes are required.

Summaries include complete summed counts/pooled rate, defined-only
`mean_changed_slot_count`, `mean_changed_slot_rate`, and
`footprint_measured_attempts` so missing coverage is visible. Historical nullable
fields remain readable; footprints are not retroactively inferred from old records.

## System effort: tools, verifier executions, and complete execution

| Metric | Definition | Level | Missing-value behaviour |
| --- | --- | --- | --- |
| `tool_call_count`, `tool_call_counts_by_type` | Actual public tool API invocations, including repeats, retries and exceptions | Attempt and strategy | None on historical records; 0 / {} when observed with no calls |
| `successful_tool_call_count`, `failed_tool_call_count` | API returns normally / raises | Attempt and strategy | None on historical records |
| `verification_count` | Top-level shared-verifier executions actually entered, including exceptions | Attempt | None on historical records; 0 when not reached |
| `repair_verification_count`, `repair_verification_iterations` | Verifier executions during strategy execution after the reused initial state | Strategy | None on historical attempt-only data |
| `initial_verification_count` | Executions during shared initialization (or local initial verification for standalone loop summaries) | Query/strategy context | None if the initial execution was not instrumented |
| `verification_count_total` | Shared initial plus repair verifier executions; initial count is contextual and must not be summed across paired strategies | Query/strategy context | None if either component is unknown |
| `total_execution_time_s`, `strategy_execution_time_s` | Direct monotonic elapsed time around complete strategy execution, including rejection, retries and synchronous checkpoint overhead | Strategy | None for old results; never reconstructed by summing attempts |
| `initial_generation_time_s` | Monotonic collection/shortlisting/generation latency before initial verification | Shared initial state | None for external preparation functions that do not report it |
| `shared_initialization_time_s` | Direct elapsed preparation, including initial generation and initial verification | Shared initial state | None on historical results |
| `initial_generation_tool_calls` | Public API executions before initial verification | Shared initial state | None if preparation cannot distinguish the phases |
| `shared_initialization_tool_calls` | Public API executions throughout shared preparation | Shared initial state | None on historical results |
| `model_call_count`, `prompt_tokens`, `completion_tokens`, `total_tokens` | Model usage snapshot deltas around complete strategy execution | Strategy | None for unavailable/incomplete channels |

`SystemUsage` uses a context-local collector, reused across nested wrappers and
reset for each independent query preparation/strategy. The public API methods
are decorated at their definitions, covering both WorldEnv commands and direct
calls from symbolic constraints, commonsense checks and transport translation.
The dispatcher itself is not counted. The actual registered names are:

- `accommodations_keys`, `accommodations_select`, `accommodations_nearby`
- `attractions_keys`, `attractions_select`, `attractions_nearby`,
  `attractions_id_is_open`, `attractions_types`
- `restaurants_keys`, `restaurants_select`, `restaurants_nearby`,
  `restaurants_id_is_open`, `restaurants_cuisine`,
  `restaurants_with_recommended_food`
- `goto`, `intercity_transport_select`, `poi_lat_lon_search`, `next_page`

No weather or budget-calculator API is registered. Arithmetic helpers and model
calls are not tools. A genuine nested public API call is counted separately:
`goto` can invoke `poi_lat_lon_search` and can recursively invoke `goto` for a
fallback. Private routing helpers, cache reads and constructors are not counted.
A normally returned `No solution`, invalid-query message, or False availability
result counts as a completed API invocation, not an exception failure. These
counters distinguish exception outcomes, not semantic usefulness.

The shared verifier is decorated independently. Nested entry wrappers share a
depth guard, so the loop wrapper and actual verifier count one execution, not
two. Its structural, commonsense, translation and personal-check phases are one
verification execution. Any actual tool APIs they invoke still count as tools.
Additional explicit top-level verification in a future strategy is counted too.
A supplied initial verification snapshot does not itself constitute execution.

Per-attempt counters persist in `RepairAttemptRecord` / `attempts.jsonl`.
Complete execution counters and direct elapsed time persist under
`system_metrics` in each query/strategy result; summary CSV uses those final
measurements. In-progress checkpoints may contain only completed-attempt
metrics. A caught strategy exception finalizes system metrics before the failed
result is saved. Shared preparation counters/timing and initial tokens remain
in `initial_state.json`; they are contextual columns, not additional repair
costs. Structured type distributions are JSON encoded in CSV cells.

Model calls, tool calls, attempts and verifier executions remain independent.
Tool accounting covers the listed synchronous APIs while a collection scope is
active. New tool APIs must be decorated; asynchronous/background work requires
explicit context propagation and completion before the execution scope ends.
