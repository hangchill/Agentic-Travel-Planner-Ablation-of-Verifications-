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

Repair owners may populate `RepairResult.metadata` with:

```python
{
    "strategy": "R1",
    "target_constraint_indices": [1, 3],
    "target_constraint_labels": ["budget", "hotel"],
    "editable_scope": {"day": 1},
}
```

All keys are optional. Missing targets become empty lists; the logger never
infers targets from failures or transitions. Indices refer to **1-based positions
in `problem["hard_logic_py"]`**, matching verifier feedback and transitions.
Supply unique, in-range integer indices and string labels when available.
Labels may be omitted independently; they need not have the same count as indices.
`strategy` falls back to the strategy class name. `editable_scope` and other
metadata are preserved without interpretation. Metadata and plans must be JSON
serializable; invalid supplied records raise rather than silently corrupt logs.

Transition groups partition the personal constraints. If either side is `None`,
the index belongs to `unknown`, never pass/fail. The contract validates groups
against the before/after vectors. Target indices describe intent, not causality.

Token counters are snapshotted around `strategy.repair()` only; missing counters
produce `None`, and deltas use available cumulative counters. Provider counters
that omit usage cannot establish actual token consumption. Repair duration uses
a monotonic timer and excludes candidate verification and acceptance.

`exception` is nullable and currently `None`: request, verification, parsing, and
acceptance exceptions retain their existing propagation behavior. This phase
records completed proposals; it does not add exception recovery or incremental
disk persistence. Failed verification states and rejected completed proposals
are recorded. The caller continues to persist the returned history as before.
