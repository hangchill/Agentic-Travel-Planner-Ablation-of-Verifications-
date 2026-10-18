# Repair attempt logging

Each completed proposal in `run_repair_loop()` has a validated, JSON-serializable
`RepairAttemptRecord` under `history[step]["repair_attempt"]`. Existing history
keys and the step-0 entry are preserved. Step 0 is initial verification, not a
repair proposal. Candidate verification remains in the existing `verification`
field even when rejected. `accepted_plan_after` is the accepted **raw itinerary**;
for rejection it is the itinerary from before the proposal. Both record vectors
describe the proposed change, including regressions rejected by the strategy.

Each record also includes `query_uid: str | None` from `problem["uid"]` when
it is a string (otherwise `None`), and `constraint_descriptors: list[dict]`.
Descriptors preserve query order with `constraint_index` starting at 1 and the
exact source `hard_logic_py` value. A `hard_logic_nl` value is included only when
the query has a corresponding list entry; missing or shorter descriptions are
safe. No normalized categories or inferred labels are added. Missing constraint
definitions produce `[]`. Older serialized records lacking these two fields
load with `query_uid=None` and `constraint_descriptors=[]`.

## Canonical record and defaults

Analysis fields live directly on `RepairAttemptRecord`; `repair_metadata` holds
only prompt/response, LLM timing and other noncanonical strategy/debug material.
The legacy history `metadata` key also retains debug material for existing timing
readers. Neither location duplicates canonical intent on new writes.

The Phase 4.1 fields and defaults are:

```python
target_provenance: str | None = None
editable_scope: str | None = None          # slot, day, plan only
scope_level: int | None = None            # 1=slot, 2=day, 3=plan
concurrent_failed_constraint_indices: list[int] = []
concurrent_commonsense_failure_count: int | None = None
feedback_personal_constraint_indices: list[int] | None = None
feedback_commonsense_failure_count: int | None = None
protected_constraint_indices: list[int] = []
escalation_reason: str | None = None
decision_reason: str | None = None
```

Lists use independent default factories. Concurrent failed indices are derived
from exact `False` values in the before vector; True/None are excluded. The
shared loop derives concurrent commonsense count from BEFORE `commonsense_errors`
when available; no list means unavailable (`None`), while an empty list means 0.
Unknown feedback indices are `None`; explicitly no feedback is `[]`. Existing
target/protected lists use `[]` for none/not available for compatibility. All
index lists are unique, 1-based positions in original `hard_logic_py` order.
Scope level must agree with editable scope when both are present. No scope
called `unknown` is emitted: unavailable scope is `None`.

`normalize_repair_intent_metadata()` is the single metadata extraction/migration
implementation. Old serialized records load with safe defaults and can promote
intent from `repair_metadata`. Explicit top-level fields win, including None/[];
no old targets are inferred from failure vectors. Legacy `scope="plan"` and
`scope="whole_plan"` map to `editable_scope="plan"`. Other unambiguous slot/day
values map directly. Uninterpretable legacy scope details are preserved as debug
`legacy_scope_details`, without guessing a scope. New writes contain no `scope`.
Old missing concurrent failed indices can be recovered exactly from before states;
unrecorded commonsense/feedback counts remain unavailable.

## Metadata required from repair strategies

Owners provide only intent the shared loop cannot derive. Canonical input keys:

```text
target_constraint_indices, target_constraint_labels (optional), target_provenance,
editable_scope, scope_level (optional), feedback_personal_constraint_indices,
feedback_commonsense_failure_count, protected_constraint_indices,
escalation_reason, decision_reason
```

Optional fields may be omitted. Existing `strategy` identity is accepted and
promoted to record `repair_strategy` (class name fallback). The loop derives
before/after states, concurrent failure context, transitions, acceptance and
available efficiency information. Do not reproduce those fields in metadata.
`decision_reason` is optional; report it only when it reliably describes the
actual accept/reject decision. No new accept-method interface is imposed.

R0 now emits the following intent, plus strategy identity/prompt/response/timing:

```python
{
    "target_constraint_indices": failed_indices,  # all and only current False
    "target_provenance": "r0_failed_feedback",
    "editable_scope": "plan",
    "feedback_personal_constraint_indices": failed_indices,
    "feedback_commonsense_failure_count": supplied_commonsense_count,
}
```

This describes the existing shared-verifier feedback: all False personal errors
are sent verbatim along with commonsense errors. The commonsense feedback count
counts occurrences actually present in `error_info`. Missing source commonsense
information leaves it `None`. Unknown personal checks are never targets. R0 does
not reduce a multiple-failure target set to one for attribution.

R1 owner example (contract only; not implemented):

```python
{"target_constraint_indices": [2], "target_provenance": "explicit",
 "editable_scope": "slot", "scope_level": 1,
 "feedback_personal_constraint_indices": [2]}
```

R2 owner example:

```python
{"target_constraint_indices": [2], "target_provenance": "explicit",
 "editable_scope": "plan", "protected_constraint_indices": [1, 3, 4, 5]}
```

R2's candidate regressions remain observable even when rollback rejects them.
Protected indices describe intent, not a reason to discard candidate evidence.

R3 owner examples (each is per attempt):

```python
{"target_constraint_indices": [2], "target_provenance": "explicit",
 "editable_scope": "slot", "scope_level": 1}

{"target_constraint_indices": [2], "target_provenance": "explicit",
 "editable_scope": "day", "scope_level": 2,
 "escalation_reason": "repeated_targeted_failure"}

{"target_constraint_indices": [2], "target_provenance": "explicit",
 "editable_scope": "plan", "scope_level": 3,
 "escalation_reason": "repeated_day_failure"}
```

**Target is not editable scope.** Widening permission to rewrite a day/plan does
not automatically target every constraint. Feedback may include other failures;
record the feedback actually supplied separately. `target_constraint_labels`
are optional source labels, never inferred categories. Changed-slot/edit-footprint
analysis remains deferred pending agreement on stable slot identities.

Transition groups partition the personal constraints. If either side is `None`,
the index belongs to `unknown`, never pass/fail. The contract validates groups
against the before/after vectors. Target indices describe intent, not causality.

Token counters are snapshotted around `strategy.repair()` only; missing counters
produce `None`, and deltas use available cumulative counters. Provider counters
that omit usage cannot establish actual token consumption. Repair duration uses
a monotonic timer and excludes candidate verification and acceptance.

`exception` is nullable and currently `None`: request, verification, parsing, and
acceptance exceptions retain their existing propagation behavior. This phase
records completed proposals; it does not add exception recovery. The paired
runner checkpoints completed proposals through the shared history callback;
normal R0 also persists returned history. Failed verification states and
rejected completed proposals are recorded.
