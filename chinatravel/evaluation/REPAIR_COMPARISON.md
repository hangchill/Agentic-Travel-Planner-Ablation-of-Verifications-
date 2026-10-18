# Paired repair experiments and storage

The runner generates and verifies one initial plan per query, then runs registered
strategies from independent copies of that plan, context and verification.
Only R0 is currently registered. Future owners add zero-argument factories to
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
failure is stored as `initial_failure.json`; incomplete proposals are not
fabricated as completed attempts. Other queries/strategies continue after errors.

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
