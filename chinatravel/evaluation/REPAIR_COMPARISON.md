# Paired repair comparisons (Phase 4)

Only R0 was present when this runner was added. The strategy registry is
`chinatravel.agent.nesy_verifier.repair_strategies.STRATEGY_FACTORIES`; it maps
names to zero-argument factories returning fresh strategy instances. R0 loads
lazily. Future owners register their own implementations here; there is no
filesystem guessing or fallback to R0. No R1–R4 implementation is supplied.

## Initial-state extraction

`LLMModuloAgent._generate_initial_plan()` contains the original initialization,
information collection, shortlisting, context construction, generation and
parsing steps. It returns `InitialRepairState`. Normal `solve()` calls this once,
then continues its original legacy/shared verification and repair path.

`prepare_initial_repair_state(problem, prob_idx=None)` calls the same generation
method and verifies the plan once. The serializable snapshot contains:

```text
query_uid
problem
raw_initial_plan
initial_verification
repair_context
environment_context          language; runtime objects are not serialized
generation_metadata          original response, token totals and timing
```

Initial usage includes the original query preparation calls. Existing timer
limitations remain; the runner does not invent missing provider usage or call
counts. Repair summaries cover repair attempts, not initial preparation.

The shared loop accepts optional `initial_verification` and `history_callback`.
Omitting both preserves its existing verification path and history structure.
The paired runner passes independent copies of the saved initial verification;
candidate verification uses the ordinary verifier without semantic changes.

## CLI

```bash
python run_repair_comparison.py \
  --splits medium --index QUERY_UID \
  --lang zh --llm MODEL \
  --repair-strategies R0 \
  --max-steps 10 --run-id paired-trial-01
```

Available options include:

```text
--repair-strategies R0 R1 R2 R3
--skip-unavailable
--output-dir results/repair_comparison
--run-id ID
--temperature FLOAT
--top-p FLOAT
--seed INT
--resume
--retry-failed                 requires --resume
```

Unavailable methods fail before query/model setup unless explicitly skipped.
Skipped methods are recorded in the manifest and pair outputs. Oracle fields
are always retained (`oracle_translation=True`); the existing native query
loader and model/agent factories are reused. No query adapter/splitter is added.
If no run ID is supplied, a UUID is generated. A new invocation refuses to
overwrite an existing run directory.

The manifest records UTC timestamp, Git commit and tracked-diff hash, relevant
implementation hash, split/source, ordered query UIDs, query-content hashes,
language, model identifier, available/requested/skipped strategies, repair budget,
oracle setting, accessible model request settings, and optional local seed.
Python/NumPy seeds do not guarantee provider determinism. The raw initial plan
and context are shared exactly; stochastic repair responses are not guaranteed
to be identical or order-independent. Local seeds are restarted on invocation,
not restored to a mid-run random-generator state on resume.

## Independence and hashes

For each query, preparation runs once and its state is atomically saved before
any strategy runs. The SHA-256 initial plan hash uses sorted-key, compact UTF-8
JSON serialization. A separate full-state hash detects saved context or snapshot
tampering. Every pair stores the same initial plan hash and initial plan.

The runner deep-copies problem, plan, context and initial verification for each
loop. It constructs fresh strategy objects. The CLI constructs fresh model,
agent and `WorldEnv` objects per pair and supplies a bound transport translator
with that query's independent problem state. Factory inputs are detached too.
No generation/selection is repeated for a repair pair. Python API callers must
honor the `runtime_factory` contract: return an independent model/environment
runtime per pair; arbitrary injected collaborators cannot be made isolated by
copying an SDK client.

## Outputs and identity

```text
results/repair_comparison/<run_id>/
  run_manifest.json
  attempts.jsonl
  summaries.csv
  queries/<escaped-uid-and-digest>/
    initial_state.json
    <escaped-strategy-and-digest>.json
    initial_failure.json       only when preparation fails
  logs/                        original initial-generation/agent logs
```

Escaped names plus digests avoid path traversal and case/encoding collisions.
Pair JSON contains invocation/run identity, query, strategy, initial plan hash,
initial raw plan/verification, final accepted raw plan/verification, repair
history, serialized attempt records, central summary metrics, execution status,
stop reason and exception. `completed` means execution completed; verified
personal outcomes and aggregate verifier `passed` are separate fields.

`summaries.csv` uses `summarize_repair_history()` without reimplementing formulas,
plus invocation run ID, query/strategy identity, initial hash and execution
status. Identity is supplied even when step 0 alone contains no identity.

`attempts.jsonl` is flat: each serialized attempt plus invocation `run_id` and
`matrix_run_id=<run_id>/<strategy>`. Query/strategy identity is explicit. The
matrix loader strips those two transport fields and uses `matrix_run_id` as
the strategy-specific run identity, preventing different methods at the same
query/step from colliding. Existing matrix definitions remain unchanged.

```bash
python scripts/build_regression_matrix.py \
  --input results/repair_comparison/paired-trial-01/attempts.jsonl \
  --repair-strategy R0 --output-dir artifacts/matrix-r0
```

R0 now logs all current False personal constraints as targets with
`target_provenance="r0_failed_feedback"` and `editable_scope="plan"`. Exactly one
mapped failed target can enter the strict primary matrix. Multiple targets are
retained but excluded from directional attribution; unknown states are not
targets. The runner itself never infers targets. Canonical intent lives directly
on the record, with debug metadata kept separate. See
[Metadata required from repair strategies](REPAIR_ATTEMPTS.md#metadata-required-from-repair-strategies)
for exact R0/R1/R2/R3 contracts and the distinction between targets and editable
scope. R1–R4 remain unimplemented.

The candidate matrix is the primary comparison of proposed repair behavior.
The accepted matrix measures safeguards/outcomes, so rollback can drive R2's
accepted regression rate down without making its proposals intrinsically safer.
Scope-conditioned aggregation is secondary and preserves primary eligibility.
These estimate observed associations, not causal dependencies. Slot/edit-footprint
analysis remains deferred.

## Checkpointing, failure and resume

Pair JSON files are authoritative. They are written using a same-directory
temporary file, flushed/fsynced and atomically replaced. Completed proposals
checkpoint after the loop records them. Initial generation, each completed
proposal and final pair completion have durable snapshots. A strategy exception
records its type/message and completed attempt prefix, then other methods
continue. An exception before a proposal completes does not fabricate an attempt
record. Preparation failure is recorded separately and other queries continue.

JSONL and CSV indexes are rebuilt atomically from pair checkpoints, rather than
appended. This avoids duplicate attempts on repeated/resumed execution.
Old records are normalized through the canonical reader when rebuilding JSONL;
legacy intent is promoted to direct fields without changing stored old pair files.
No targets are invented for old R0 attempts that did not record them. A crash
between file replacements may leave indexes stale; resume rebuilds them before
work. A directory lock prevents concurrent writers. After a hard process crash,
inspect the recorded PID and remove a stale `.comparison.lock` manually before
resuming; locks are never silently stolen.

```bash
python run_repair_comparison.py ... --run-id paired-trial-01 --resume
```

Resume requires matching configuration, query contents/order, strategy availability,
and recorded implementation/settings. Saved initial state hashes are checked.
Completed/skipped pairs are never rerun. Failed pairs remain recorded unless
`--retry-failed` is supplied. Interrupted `running` pairs restart from the saved
initial state; failed-pair retries do likewise, replacing their prior attempt
stream rather than mixing two trajectories. There is no mid-attempt continuation
or exactly-once guarantee for a provider request interrupted before checkpoint.
Missing initial state alongside pair checkpoints raises instead of generating
a different starting plan. A failed preparation with no initial snapshot may be
retried on resume. Sandbox contents/provider behavior are not fingerprinted;
keep those fixed externally. No live end-to-end claim is made by mock tests.
