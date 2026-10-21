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
R0 and R3 are currently implemented.

| Strategy | Expected intent | Optional strategy-specific fields |
| --- | --- | --- |
| R0 | All current False personal indices; scope `plan` | Emits `target_provenance="r0_failed_feedback"` and actual feedback indices/count |
| R1 | Selected target indices; scope `slot` | `scope_level=1` |
| R2 | Selected target indices; scope `plan` | `protected_constraint_indices`, reliable `decision_reason`; override `accept()` for rollback |
| R3 | All current False personal indices (repaired together); current `slot`/`day`/`plan` scope | Matching `scope_level` 1/2/3, `escalation_reason` when widening, `target_provenance="r3_adaptive_scope"`, actual feedback indices/count |

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
