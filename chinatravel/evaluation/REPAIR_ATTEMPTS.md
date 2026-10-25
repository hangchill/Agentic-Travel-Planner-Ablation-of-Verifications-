# Repair strategy and attempt contract

Implement `BaseRepairStrategy.repair()` and return:

```python
return RepairResult(
    repaired_plan=repaired_plan,
    metadata={
        "target_constraint_indices": [2],
        "editable_scope": "slot",
    },
)
```

Targets are unique, original **1-based `hard_logic_py` indices**. Scope is
`slot`, `day`, or `plan`; strategy owners enforce the permitted edits. Target
and scope are independent: widening edits does not automatically widen targets.
Register a zero-argument factory in `repair_strategies.STRATEGY_FACTORIES`.
R0, R1, R2, R3 and R4 are currently implemented.

| Strategy | Expected intent | Optional strategy-specific fields |
| --- | --- | --- |
| R0 | All current False personal indices; scope `plan` | Emits `target_provenance="r0_failed_feedback"` and actual feedback indices/count |
| R1 | Selected target indices; scope `slot` | `scope_level=1` |
| R2 | Selected target indices; scope `plan` | `protected_constraint_indices`, reliable `decision_reason`; override `accept()` for rollback |
| R3 | Personal phase: all current False personal indices (repaired together), current `slot`/`day`/`plan` ladder scope. Commonsense phase: `[]`, scope = current ladder rung | Matching `scope_level` 1/2/3, `escalation_reason` when widening, `target_provenance="r3_adaptive_scope"`, actual feedback indices/count, `protected_constraint_indices` (the passing personal constraints listed as "must remain satisfied") in the commonsense phase |

For a multi-target attempt (e.g. R3 or R0 with several failures), the record
shows the constraints the repair broke (`newly_violated`) alongside the whole
target set (`target_constraint_indices`). It does not say which individual
target caused each break.

Other optional audit keys are `target_constraint_labels`, `target_provenance`,
`feedback_personal_constraint_indices`, and `feedback_commonsense_failure_count`.
Labels and provenance are not required by matrix eligibility. `strategy` may
supply the recorded method name; otherwise the class name is used. A scope level
must agree with its scope when both are present. Decision reasons must describe
the actual accept/reject decision, not an assumed outcome.

## Shared responsibilities

The loop verifies proposals, compares before/after states, records acceptance,
and derives available token/timing and concurrent-failure information. Owners
need no separate verifier, logger, database, metrics, or matrix implementation.
Query/verifier inputs are detached snapshots; mutations cannot rewrite stored
outcomes. Return the proposal through `RepairResult` and acceptance through the
Boolean `accept()` result. Rejected candidate outcomes remain observable.

`RepairAttemptRecord` is the standardized observation of a repair attempt.
It contains intent, raw candidate and accepted-after plans, original constraint
descriptors, tri-state before/after vectors, transitions, and efficiency fields.
Canonical fields live directly on the record; `repair_metadata` is for prompts,
responses and other debug material. Initial verification is history step 0,
not a repair attempt. Existing history fields remain available.

- `False` means failed; `None` means unknown and is never an inferred target.
- Concurrent failed indices come from exact False values before repair.
- Concurrent commonsense count comes from BEFORE `commonsense_errors`.
- Missing counts/scope are `None`. Feedback indices distinguish unavailable
  (`None`) from explicitly none (`[]`). Target/protected lists retain `[]` for
  none/unavailable. All index lists are unique and 1-based.
- Efficiency fields are derived centrally; see the [metric definitions](REPAIR_METRICS.md)
  for dispatch counting, token completeness and generation/verification/attempt timing.
- Failed attempts retain their exception and measured costs before propagation.
  Unevaluated candidate states are unknown. The paired runner also stores the
  exception on the pair result; owners do not manually report efficiency totals.

R0 sends every False personal failure plus commonsense feedback already supplied
by the shared verifier. It excludes unknown personal checks and preserves all
multiple targets. Feedback commonsense count measures supplied occurrences.

Old records remain readable: intent in metadata is promoted, unambiguous legacy
scope is mapped, and explicit top-level fields win. Unrecorded targets/feedback
are not invented. New writes use only canonical fields.

See [paired storage/resume](REPAIR_COMPARISON.md), [metrics](REPAIR_METRICS.md),
and the [matrix definition](REGRESSION_MATRIX.md). Operational changed-slot
semantics are defined in the metrics document.

### Shared scheduling

The shared loop respects `min(max_steps, 6)` total proposals, including rejected
and unchanged proposals. Default experiment/LLM-modulo repair budgets are six;
explicit smaller budgets are not increased. A run uses the whole budget unless it
stops early, which happens only when the plan passes or when every personal
constraint is True and no commonsense failures remain. At most five proposals are
personal repairs; commonsense repairs may repeat.

`context["repair_phase"]` explicitly selects `personal` or `commonsense` without
changing the strategy method signature. Full verification is retained as context.
Strategies must honor this intent: personal repairs prioritize False/UNKNOWN
personal constraints; commonsense repairs target commonsense failures, even if
personal failures remain. R0 filters its feedback accordingly; R1 selects its
commonsense transport handler explicitly. Direct calls without phase context
retain historical strategy behavior.

Each proposal's phase is chosen from the current accepted state:

- a personal constraint is False or UNKNOWN (UNKNOWN is not True) and fewer than
  five personal proposals were made → `personal`;
- otherwise, commonsense failures exist → `commonsense` (repeated while they
  remain; after five personal proposals the remaining proposal goes here);
- personal still False/UNKNOWN after five personal proposals and no commonsense
  failures → `personal` again (the budget is still used);
- otherwise (all personal True, no commonsense failures) → stop.

So personal repair has priority; commonsense repair follows once personal
constraints pass; a commonsense proposal that breaks a personal constraint sends
the next proposal, if budget remains, back to personal repair. Accepted state
determines every transition.

The loop never stops a run because a strategy made no progress: unchanged
proposals (including R1 no-ops) are recorded and each consumes a proposal.

Every strategy calls the model through the loop's per-query repeat-request cache
(`RepeatRequestCache`): a request identical to one already sent for the query
(same messages and options) reuses the earlier reply without a model call. No
strategy has a skip rule of its own. Each attempt's `repair_metadata` records
`llm_cache_hits`, `llm_cache_saved_input_tokens`, `llm_cache_saved_output_tokens`
and `llm_cache_saved_unknown`; `scripts/build_repair_summary.py` summarises them
per query in `llm_cache_hits.csv`.
Exceptions remain recorded and raised, rather than spending further proposals.

Attempt JSON adds nullable `repair_phase` (historical default `None`) and
`target_commonsense_errors: list[str]` (historical default `[]`). The latter records
scheduled commonsense feedback targets; strategy-specific `target_commonsense_error`
may identify a narrower chosen error in debug metadata. Scheduled commonsense
proposals always carry empty personal target indices/labels; concurrent personal
failures remain separately recorded. They count normally in summaries and costs,
but remain zero-target exclusions from the unchanged primary directional matrix.


The shared scheduling policy applies to **all registered strategies** executed through
`shared_repair_loop`, including R3. R3 takes its phase from the loop; a direct
call without a phase shows all failures. Every step, commonsense included,
advances R3's ladder, so the rung follows the step number (steps 1-2 slot, 3-4
day, 5-6 plan) and each commonsense step uses the current rung. The
former R3P variant (an internal phase
selector) is removed because the shared loop now does that scheduling.
Registered strategies share the same total cap of six.
The legacy `repair_strategy=None` baseline does not use this scheduler and is
outside this refactor. Historical evaluator directory names and unrelated agent
action budgets are unchanged. A strategy reporting a different executed phase
raises an execution error; the record retains the mismatch for diagnosis.


For explicitly scheduled R3 commonsense attempts, only commonsense violations
select targets and editable scope. Schema errors remain in verification/history
and evaluation but do not enter the scheduled repair objective. Direct calls
without shared phase intent retain historical schema-targeting behavior.
