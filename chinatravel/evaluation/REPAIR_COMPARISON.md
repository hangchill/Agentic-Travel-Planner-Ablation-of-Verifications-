# Paired repair experiments and storage

The runner generates and verifies one initial plan per query, then runs registered
strategies from independent copies of that plan, context and verification.
R0, R1, R3 and R3P are currently registered. Future owners add zero-argument factories to
`repair_strategies.STRATEGY_FACTORIES`; unavailable methods never fall back to R0.
See the [strategy contract](REPAIR_ATTEMPTS.md).

```bash
python run_repair_comparison.py \
  --splits medium --index QUERY_UID --lang zh --llm MODEL \
  --repair-strategies R0 --max-steps 10 --run-id paired-01
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
results/repair_comparison/<run_id>/
  run_manifest.json
  attempts.jsonl
  summaries.csv
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
records, central summary metrics, execution status, stop reason and exception.
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

Checkpoints and rebuilt JSONL/CSV indexes use atomic replacement. Resume repairs
stale indexes and reads old records through the canonical reader. A run lock
prevents simultaneous writers; after a hard crash, inspect the PID and remove
its stale lock manually. There is no exactly-once provider-request guarantee if
interruption occurs before checkpoint. Keep sandbox/provider versions fixed
externally. See [metrics](REPAIR_METRICS.md), [matrix methodology](REGRESSION_MATRIX.md),
and `python run_repair_comparison.py --help` for options.


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
python scripts/build_train_test_split.py \
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
python run_repair_comparison.py --splits SOURCE --llm MODEL \
  --repair-strategies R0 --split-manifest artifacts/train_test.json \
  --partition train --run-id train-r0
python scripts/build_regression_matrix.py --input attempts.jsonl \
  --repair-strategy R0 --split-manifest artifacts/train_test.json \
  --partition train --output-dir artifacts/train-matrix
```

The paired runner selects the saved partition from the existing native query
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
