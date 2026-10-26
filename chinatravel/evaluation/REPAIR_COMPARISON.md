# Repair experiment evidence and offline evaluation

Use `run_experiments.py` for single-strategy runs. It writes raw evidence only;
benchmark, summary, and matrix generation are independent offline steps. Paired
experiments sharing one initial plan remain available through the lower-level
`chinatravel.evaluation.repair_comparison.run_comparison()` Python API.

The runner generates and verifies one initial plan per query, then runs registered
strategies from independent copies of that plan, context and verification.
R0, R1, R2, R3 and R4 are currently registered. Future owners add zero-argument factories to
`repair_strategies.STRATEGY_FACTORIES`; unavailable methods never fall back to R0.
See the [strategy contract](REPAIR_ATTEMPTS.md).

```bash
python run_experiments.py \
  --splits medium --index QUERY_UID --lang zh --llm MODEL \
  --strategy R0 --max-steps 10 --run-id paired-01
```

Other options: `--skip-unavailable`, `--output-dir`, `--temperature`, `--top-p`,
`--seed`, `--resume`, `--retry-failed`. A UUID is generated when run ID is omitted.
Oracle fields are retained through the native loader. The manifest records query
source/UIDs/content hashes, model/settings, language, strategy availability,
repair budget, seed, Git/source fingerprints, timestamp and reuse policy.
Local seeds do not guarantee provider determinism or restore mid-run RNG state.

`InitialRepairState` stores query, raw plan, verification, strategy context and
available initial-generation usage. `prepare_initial_repair_state()` reuses the
same generation steps as normal R0. Normal `solve()` retains its verification
path; optional shared-loop snapshot/callback arguments support paired runs.

The CLI creates fresh strategy/model/agent/environment runtimes per pair. Problem,
plan, context and initial verification are deep-copied. Every pair records the
same sorted-JSON SHA-256 `initial_plan_hash` for a query; a full-state hash also
checks saved context integrity. Python callers must supply isolated runtimes via
`runtime_factory`; SDK clients are not blindly deep-copied. Repairs may remain
stochastic even though their initial inputs are identical.

## Storage

```text
results/experiments/<run_id>/
  run_manifest.json
  attempts.jsonl
  summaries.csv  # created only by the offline summary builder
  queries/<escaped-query-uid-and-digest>/
    initial_state.json
    <escaped-strategy-and-digest>.json
```

**attempts.jsonl is the canonical raw repair-attempt stream for analysis. No
database is required.** Each line is a standardized record plus invocation
`run_id` and strategy-specific `matrix_run_id=<run_id>/<strategy>`. Matrix tooling
accepts it directly. Pair JSON checkpoints are authoritative for crash recovery
and rebuild the analysis stream without appending duplicates.

Pair results contain initial/final raw plans and verification, history, attempt
records, execution status, stop reason and exception. Historical paired checkpoints
may also contain cached central summary metrics.
`completed` means execution completed, not all constraints passed. Summaries use
`repair_metrics.py` and add run/query/strategy/hash/status fields. Preparation
failure is stored as `initial_failure.json`. Failed repair attempts retain costs
and an exception, with unknown outcomes when unevaluated; they are not labelled
completed proposals. Other queries/strategies continue after errors. See the
[efficiency definitions](REPAIR_METRICS.md) for measured versus unavailable fields.

## Resume

Use the same CLI configuration and `--run-id ... --resume`. Configuration, query
contents/order, available strategies and implementation/settings must match.
Initial snapshots are reused and checked, not regenerated over existing pairs.
Completed/skipped pairs stay untouched; failed pairs retry only with
`--retry-failed`. Interrupted pairs and failed-pair retries restart from the saved
initial state, replacing their old attempt prefix rather than combining runs.

Checkpoints and rebuilt JSONL indexes use atomic replacement. Resume repairs
stale indexes and reads old records through the canonical reader. A run lock
prevents simultaneous writers; after a hard crash, inspect the PID and remove
its stale lock manually. There is no exactly-once provider-request guarantee if
interruption occurs before checkpoint. Keep sandbox/provider versions fixed
externally. See [metrics](REPAIR_METRICS.md), [matrix methodology](REGRESSION_MATRIX.md),
and `python run_experiments.py --help` for options.


## Train/test boundary

The native loader exposes `easy`, `medium`, `human`, `preference_base50`, and
`preference0_base50` through `preference5_base50`, plus configured local splits.
These names are query sources, not this project's train/test allocation. No native
query JSON payloads are checked out locally, so native semantic variant groups
cannot be established from local records. The public release exporter preserves
only uid/cities/days/people/constraints/prompt; it drops generation provenance.
Current public ChinaTravel query schema does not expose semantic prompt-variant
groups; therefore each query UID is its own group when no explicit field exists.
Never infer a group by wording, UID prefix, constraints, embeddings, or an LLM.

`train_test_split.py` chooses the first available nonempty string field in this
priority: `semantic_case_id`, `case_id`, `base_case_id`, `parent_case_id`, then
`source_plan_uid`; otherwise the query's `uid` (`query_uid` in the audit).
The synthetic generator explicitly records `source_plan_uid` and generates
`variants_per_plan`. Grouping these together is a conservative source-plan
holdout: sampled constraints may differ, so this does not claim semantic
identity. Generate the split from pre-release records to retain that provenance.
Do not treat filenames or `seed_plan_path` as undocumented semantic identities.

```bash
python scripts/experiment_setup/build_train_test_split.py \
  --input path/to/queries.json --output artifacts/train_test.json \
  --train-fraction 0.7 --seed 42
```

Inputs: query JSON arrays, UID-keyed JSON maps, JSONL records, or directories of
individual query JSON files (use a synthetic dataset's `data/` directory).
Duplicate UIDs fail. At least two groups are required. Groups are ranked by
SHA-256 of JSON `[seed, group_id]` (UTF-8); input order cannot affect allocation.
The first `floor(train_fraction * group_count)` groups go to TRAIN, clamped to
leave both partitions nonempty. The default is 70% of **groups**, seed 42; query
counts can differ from 70% when group sizes differ.

The versioned JSON manifest includes algorithm/seed/ratio/grouping priority,
`train` and `test` UID lists, `groups[group_id] = {split, query_uids}`, and
`queries[uid] = {group_id, grouping_field}`. Validation requires exact membership,
unique UIDs, disjoint partitions, and every group's complete membership in its
single assigned partition. Consumers validate the full manifest before filtering.
This prevents known groups from crossing partitions; absent provenance cannot be
recovered, so the UID fallback cannot guarantee absence of unknown variants.

```bash
python run_experiments.py --splits SOURCE --llm MODEL \
  --strategy R0 --split-manifest artifacts/train_test.json \
  --partition train --run-id train-r0
python scripts/matrix_building/build_regression_matrix.py --input attempts.jsonl \
  --repair-strategy R0 --split-manifest artifacts/train_test.json \
  --partition train --output-dir artifacts/train-matrix
```

The experiment runner selects the saved partition from the existing native query
loader, validates grouping metadata against the manifest, and records manifest
hash/partition in resume compatibility. All partition queries must be available
in the chosen source; `--index` may further restrict that partition. For TEST use
`--partition test` with the same saved manifest. Run registered R0/R1/R2/R3 on
TRAIN, then registered R0/R1/R2/R3/R4 on held-out TEST as they become available.
This does not register or implement unavailable strategies.

**The final R4 matrix must be estimated from TRAIN trajectories only. TEST
attempts must never contribute to that matrix.** The matrix CLI filter is opt-in
and precedes the unchanged eligibility/formula computation. Missing/unknown
attempt UIDs fail loudly; TEST rows are excluded for `--partition train`. Coverage
records the partition and manifest-byte SHA-256. Without these two flags existing
unrestricted diagnostics remain available. Filtered TEST matrices are diagnostics
only, never R4 training inputs. Keep the saved manifest fixed throughout the study.

### Recommended offline workflow

`run_experiments.py` is the single-strategy evidence-only entrypoint. It calls
`run_comparison(..., raw_only=True)` directly; no repair logic is duplicated.
It does not run benchmark evaluation, summaries, or matrices automatically.
The lower-level Python API retains paired initial-plan reuse and its legacy
summary mode for compatibility; `_rebuild_indexes()` is preserved.

```bash
python run_experiments.py --splits pilot5 --strategy R0 --lang zh \
  --llm YOUR_PROVIDER_MODEL_ID --max-steps 5 --seed 42 --run-id pilot5-r0
python scripts/result_analysis/evaluate_repair_run.py --run-dir results/experiments/pilot5-r0
python scripts/result_analysis/build_repair_summary.py --input results/experiments/pilot5-r0
python scripts/matrix_building/build_regression_matrix.py \
  --input results/experiments/pilot5-r0/attempts.jsonl \
  --output-dir results/experiments/pilot5-r0/regression_matrix
```

Choose a registered strategy and an identifier supported by your configured
endpoint. The experiment CLI accepts `--split-manifest ... --partition train`
and `--index UID` for exact population selection. Do not build R4's training
matrix from TEST runs. None of the post-processing steps starts another step.

Raw output under `results/experiments/<RUN_ID>/`:

- `run_manifest.json`: selected UIDs, strategies, language, partition, hashes/settings
- `attempts.jsonl`: regression-ready formal proposal records and usage deltas
- `queries/<uid-hash>/reference/query.json`: reference query saved before generation
- `queries/<uid-hash>/initial_state.json`: initial verification and generation metadata
- `queries/<uid-hash>/initial_failure.json`: exception if initialization failed
- `queries/<uid-hash>/<strategy-hash>.json`: accepted state, full repair history,
  attempt records, raw execution counters, status and exception
- runtime logs/cache where configured

The new runner does not calculate `summary_metrics` or create `summaries.csv`,
benchmark outputs, or matrices. Existing summaries are not deleted on resume.
Raw-only resume is compatibility-checked separately from legacy paired runs.

The offline summary command reads only the manifest, pair checkpoints, initial
state metadata and initial-failure records. It does not need the redundant
attempt stream and does not load models, tools, queries from the network, or rerun
verification. It refuses a locked run. Optional `--output PATH` leaves the run's
normal summary untouched. Legacy paired checkpoints are supported, and their
cached `summary_metrics` are ignored in favor of reconstruction.

`summarize_checkpoint()` reuses `summarize_repair_history()` and the existing
execution-counter override order. Final states follow accepted history; rejected
candidates affect proposal diagnostics but not final accepted satisfaction.
Initial failures retain undefined metrics, not zeros. Missing checkpoints get
explicit `missing_checkpoint` rows. Strategy exceptions/stop reasons are exported.

Efficiency definitions are unchanged: attempt deltas and pair `system_metrics`
are repair/strategy execution only. `total_execution_time_s` is strategy runtime,
not initial generation plus repair. `shared_initialization_time_s`,
`initial_generation_time_s`, and their tool counts are separate initialization
fields. `verification_count_total` includes initialization when known. Token and
model-call deltas do not silently add generation usage; generation usage remains
available in `initial_state.json` metadata. Missing historical counters remain
unknown; they cannot be reconstructed by inventing values or rerunning calls.

The benchmark wrapper reuses `eval_exp.evaluate_final_plans()` and the export
adapter, producing `benchmark_eval/<strategy-hash>/plans/<UID>.json`,
`evaluation_population.json`, detailed benchmark CSVs and `benchmark_summary.json`.
It uses accepted-final translated plans and the exact experiment population,
including failed/invalid plans. New runs retain reference queries even when
initialization fails. Older initial-failure-only runs require original references
via the adapter's `queries` argument. Benchmark scores remain separate from repair
summaries. Matrix exports and formulas are unchanged.

### Summary CSV columns

Columns are the sorted union of defined row keys, as in the legacy exporter.
All-initial-failure runs therefore have only identity/status/exception columns;
unavailable quality/efficiency values are absent or blank. Normal completed rows
use the existing metric schema plus `exception` and `stop_reason`:

```text
acceptance_rate
accepted_attempts
accepted_cumulative_net_repair_gain
accepted_total_fixed
accepted_total_newly_violated
attempts
attempts_scope_day
attempts_scope_plan
attempts_scope_slot
attempts_scope_unavailable
attempts_until_success
changed_slot_count
changed_slot_rate
completion_tokens
cumulative_net_repair_gain
decision_rejected_attempts
decision_rejection_rate
escalation_count
exception
execution_status
failed_attempts
failed_model_calls
failed_tool_call_count
final_all_personal_constraints_pass
final_failed_count
final_personal_constraint_satisfaction_rate
final_unknown_count
footprint_measured_attempts
highest_scope_level
initial_failed_count
initial_generation_time_s
initial_generation_tool_calls
initial_plan_hash
initial_unknown_count
initial_verification_count
mean_changed_slot_count
mean_changed_slot_rate
mean_new_violation_rate
mean_repair_success_rate
mean_targeted_repair_success_rate
model_call_count
model_call_data_complete
model_calls
prompt_tokens
query_uid
rejected_attempts
rejection_rate
repair_attempt_count
repair_model_calls
repair_strategy
repair_success
repair_tool_calls
repair_verification_count
repair_verification_iterations
run_id
scope_data_complete
shared_initialization_time_s
shared_initialization_tool_calls
stop_reason
strategy_execution_time_s
successful_tool_call_count
targeted_repair_success_rate
timing_data_complete
token_data_complete
tool_call_count
tool_call_counts_by_type
total_attempt_time_seconds
total_comparable_slots
total_execution_time_s
total_fixed
total_input_tokens_delta
total_newly_violated
total_output_tokens_delta
total_repair_time_seconds
total_targeted_failed_before
total_targeted_fixed
total_token_data_complete
total_tokens
total_tokens_delta
total_verification_time_seconds
verification_count_total
verification_model_calls
```
