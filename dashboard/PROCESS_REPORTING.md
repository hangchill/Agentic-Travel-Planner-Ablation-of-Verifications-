# Table 3: Repair Process / Efficiency

The process tab follows the PC/CS table-first design: difficulty × strategy report,
round outcomes, cost/runtime, observed-round diagnostics, round strategy comparison,
and additional diagnostics. Shared reporting discovery, cohort filtering, controls,
pivots, population guards, charts and CSV downloads are reused. PC and CS numerical
mappings/behavior are unchanged.

## Audited source of truth

Before implementation, inspected:

- `scripts/result_analysis/build_test_result_tables.py`: `build_queries()`,
  `summed()`, `round_data()` and `table_process()`.
- `test_result_analysis/<strategy>/table3_repair_process.csv` and `per_query.csv`.
- Checkpoint `repair_history`, `repair_attempts` and saved attempts.
- Existing dashboard trajectory/process/counter helpers.
- `RepeatRequestCache`, cache logging and usage deltas in
  `chinatravel/agent/nesy_verifier/shared_repair_loop.py`.
- `model_usage.py`: transport dispatch/failure counters, including retries.

The main table reads generated Table 3 CSV cells. For a smaller filtered cohort it
calls the original `table_process()` on saved per_query rows. No scorer, experiment,
repair/verifier call, matrix builder or model/provider is run by the dashboard.
Proposal filters select query cohorts; round sections retain their complete
observed trajectories, matching the PC/CS convention.

## Main Table 3 mapping

All source rows below are in table3_repair_process.csv / table_process(). The
original Easy, Medium, Human and All columns are retained (Medium displayed Med).
Available difficulty/strategy combinations are discovered, including future R0/R1.

| Displayed metric | Exact source row | Denominator / missingness | Evidence |
|---|---|---|---|
| Queries with complete token data | [per query] Queries with token data | Queries with nonmissing tokens_spent; includes recorded zero totals | Saved repair-process reporting |
| Avg tokens per query (complete token data) | [per query] Avg tokens spent per query (queries with complete token data) | Mean nonmissing complete per-query totals; source rounding retained; no complete queries → Unavailable | Saved repair-process reporting |
| Rounds with no token count | [per query] Rounds with no recorded token count | Sum rounds_missing_tokens | Saved repair-process reporting |
| Avg tokens, all queries (lower bound) | [per query] Avg tokens spent per query - known values only, all queries (lower bound) | Mean tokens_spent_known over all queries, including their observed partial sums | Saved repair-process reporting |
| Avg repair time per query (s) | [per query] Avg repair time per query (s) | Mean nonmissing complete sums of repair_time_seconds; source rounding retained | Saved repair-process reporting |
| Queries with >=1 round making changes | [per query] Queries with at least one round that changed the plan | Count changed >0 | Saved loop-verifier process reporting |
| Δ PC passed per changed round | [per query] Avg change in PC passed per changed round (loop verifier) | Each query's mean over its changed rounds, then macro mean over queries with defined changed-round means | Saved loop-verifier reporting |
| Δ CS errors per changed round | [per query] Avg change in CS errors per changed round (loop verifier; negative = fewer errors) | Same within-query then across-query averaging | Saved loop-verifier reporting |
| Rounds in total | [round-wise] Repair rounds in total | Sum rounds (history entries after initial) | Saved process reporting |
| % rounds: model call failed | Unavailable | No established Table 3 row; raw failure flags belong to separate diagnostics | Not reconstructed in main table |
| % rounds: plan changed | [round-wise] % of rounds where the plan changed | Sum changed / sum rounds ×100; zero rounds → Unavailable | Saved process reporting |
| % rounds: unchanged, from cache | [round-wise] % of rounds unchanged - answered from cache (exact repeat of an earlier request) | Sum unchanged_cache / sum rounds ×100 | Saved process reporting |
| % rounds: unchanged, new request | [round-wise] % of rounds unchanged - from a different request (model called) | Sum unchanged_other / sum rounds ×100; residual category, not proof of dispatch | Saved process reporting |

These are report aliases only. Missing source rows stay Unavailable. Raw attempts
are not used to rebuild the main report's missing model-failure percentage.
Existing per-100k-token efficiency rows are not added to the requested main row
list; the underlying generated Table 3 outputs remain unchanged.

## Token coverage and runtime semantics

`build_queries()` uses `summed(attempt.total_tokens_delta)` for tokens_spent.
`summed()` returns a value only for a nonempty list in which every value is known.
One missing delta makes the whole query's complete total unavailable. An empty
attempt list also yields unavailable complete tokens, even when its known-token
lower bound is zero. The dashboard preserves this existing reporting convention.

`tokens_spent_known` sums nonmissing deltas, with missing entries contributing zero
only to the **lower bound**. `rounds_missing_tokens` counts null deltas. No input/
output-token inference, missing-count imputation, or cache-savings estimate is
substituted for the reporting definition.

“Avg tokens, all queries (lower bound)” is not a complete estimate of total token
consumption: unrecorded usage is absent from its partial sums. Recorded zero is
valid observed data; missing is not a true zero-cost observation.

The cost table's completeness percentage is the existing complete-query count
from Table 3 divided by the selected query count ×100. A visible warning appears
below **80%**, an explicitly displayed UI coverage threshold rather than a changed
metric definition or statistical significance claim.

`repair_time_s` is the complete sum of per-attempt repair_time_seconds, not wall
clock experiment duration or initialization cost. A missing attempt time leaves
the query total unavailable; the team helper averages defined query totals only.
Tokens and seconds have separate charts and scales.

Cost/runtime table sources:

| Field | Source / denominator |
|---|---|
| Queries | Selected per_query.csv population size |
| Complete-token queries | Table 3 complete-token count |
| Token completeness % | Complete-token count / selected queries ×100 |
| Avg tokens/query (complete) | Corresponding Table 3 cell |
| Avg tokens/query lower bound | Corresponding Table 3 cell |
| Missing-token rounds | Corresponding Table 3 cell |
| Avg repair time/query | Corresponding Table 3 cell |

## Changed-round effects and cache semantics

`round_data()` compares JSON-sorted `candidate verification.translated_plan` with
the accepted translated plan in place before that proposal. On acceptance only,
the current accepted state advances. A changed rejected R2 candidate is still a
changed round for Table 3.

- PC delta = candidate True count minus prior accepted True count. Positive means
  improvement; negative means deterioration. UNKNOWN→True contributes, unlike
  the distinct False→True fix-event metric used by other diagnostic tables.
- CS delta = candidate commonsense_errors list length minus prior accepted list
  length. Negative means improvement; positive means deterioration. These are
  loop messages, not benchmark check categories.

The existing helper applies changed → cached-unchanged → other-unchanged in that
priority. Its three categories are mutually exclusive and exhaustive. A changed
candidate with a cache hit remains **changed**. Unchanged with llm_cache_hits >0
is cached; all remaining unchanged rounds are unchanged_other. Missing cache
markers default to zero in this original classification.

The last category's source label says “different request (model called)”, but the
actual classifier does not require model_calls >0 or an explicit request identity.
The dashboard preserves its counts and calls it the reporting residual; it does
not claim every such round made a genuinely new request or a model dispatch.

RepeatRequestCache keys exact messages, positional arguments and call options.
A hit returns the stored reply without invoking the wrapped LLM for that matching
request; replies from raising calls are not cached. Cache-hit rounds are still
verified, and an attempt can have additional model calls or retries. Therefore a
hit proves request-level reuse, not a zero-call/zero-cost whole round. The UI does
not claim or estimate aggregate token/cost savings.

## Repair round outcomes

Plan changed / Unchanged cache / Unchanged new request counts come from selected
per_query.csv changed/unchanged_cache/unchanged_other. Their percentages divide by
selected rounds. Source counts must be complete; missing/zero denominators stay
Unavailable. They are shown separately from the diagnostic failure flag.

“Model call failed (overlapping)” counts rounds with an explicitly recorded
failed_model_calls >0. That counter counts observed model transport failures
(including retry/verification dispatches), not a separate exclusive repair result.
A failure can coexist with a changed candidate or a cache hit. Its count and
percentage are only shown with complete round/counter coverage; otherwise they
are Unavailable and evidence N remains visible. It is never added to the three
outcome counts to force a 100% partition. The supplementary bar chart explicitly
labels the overlap.

## Repair process by round — loop/process diagnostics

The diagnostic adapter calls the unchanged `round_data()` on a two-entry history:
the saved preceding accepted verification and that proposal's history entry. This
reuses exact classification and delta definitions without independently rebuilding
them. The full accepted chronology comes from the existing trajectory() helper.
Missing translated plans leave the round classification/effects Unavailable;
missing PC/CS verification fields leave the corresponding delta Unavailable.

The main CSV remains authoritative, including its original legacy defaults. More
conservative missing-evidence handling in the diagnostic adapter is not silently
used to overwrite saved main-table values.

| Round metric | Source / definition / denominator | Missing handling |
|---|---|---|
| # queries reaching round | Distinct persisted query IDs at that step | Observed proposals only; not inferred scheduler state |
| # / % model call failures | Rounds with failed_model_calls >0 / all observed rounds at step | Whole-step count/rate unavailable if any counter unknown |
| # / % plan changed | Original round_data classification / observed rounds at step | Unavailable with incomplete classification evidence |
| # / % unchanged from cache | Original unchanged_cache classification / observed rounds | Same |
| # / % unchanged from new request | Original unchanged_other residual / observed rounds | Same; does not establish dispatch |
| Avg tokens | Mean known raw total_tokens_delta at that step | Missing deltas excluded, never filled with zero |
| Missing token counts | Count of unknown raw deltas at that step | Identity-only observations have unavailable costs |
| Avg repair time | Mean known raw repair_time_seconds at step | Missing times excluded |
| Δ PC passed per changed round | Mean defined candidate-minus-prior-accepted True-count delta among changed proposals at that step | Not the whole-report within-query macro average; missing verification excluded |
| Δ CS errors per changed round | Mean defined candidate-minus-prior-accepted message-count delta among changed proposals at step | Same; signs preserved |
| Classification evidence N | Known translated-plan classifications | Shown independently |
| Failure counter evidence N | Nonmissing failure counters | Shown independently |
| Token evidence N | Nonmissing token deltas, including observed zero | Shown independently |

Only observed step IDs are shown. No Initial/Final columns or forward-filled
stopped queries are introduced. Independent trial histories are not concatenated.
Round charts use the exact numerical comparison cells, with gaps unconnected.
Query population guards block incompatible comparisons; no silent intersection or
TRAIN substitution is used. Main, cost and round comparisons retain model/settings/
initial-plan compatibility warnings and provenance/freshness visibility.

## Additional diagnostics audit

Existing per_query.csv rounds support mean/median observed proposals per query.
Persisted model_calls and verification_count support complete per-query sums and
means, provided observed proposal counts cover the query's reported rounds.
Known zero-round queries can contribute zero repair-counter totals. Missing
counters/coverage are not treated as zero. The exact logged stop_reason supports
budget-exhaustion percentages over queries with known reasons, even for early
stops; no claim is made that the numerical limit was reached.

changed_slot_count supports complete changed-slot-event sums per query, averaged
over queries with complete footprint evidence. Repeated edits count as repeated
events, not unique modified slots. Every secondary mean displays valid-query N.
Accepted PC fix/regression events and CS message changes already appear in PC/CS;
they are not duplicated or relabelled as universal “violation” fixes. A benchmark
CS check-level fix/new-violation identity is not persisted for every round and
remains unsupported.

All CSV downloads use the currently displayed dataframe after active controls.
No experiment artifacts, pipeline numerical outputs, metric definitions, repair
logic or matrix construction are changed.
