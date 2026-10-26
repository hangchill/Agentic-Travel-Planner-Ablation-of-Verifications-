# R4: matrix-guided repair (training only)

Yes: the whole workflow can run from `Agentic-Travel-Planner-Ablation-of-Verifications-`, with experiment results under `experiments/` and reusable matrices under `matrices/`. The canonical R4 helpers and tests now live in that repository's `r4/` directory. This README is also kept at the originally requested workspace `r4/README.md` location for reference.

You do **not** need to call `run_r4.py` or `run_r4_pipeline.py` for the pooled workflow below. Use the existing root `run_experiments.py` with `--strategy R4 --r4-matrix PATH`. It calls `chinatravel/agent/nesy_verifier/repair_strategies/r4.py` through the shared repair loop. That strategy file implements repairs; the experiment runner handles query loading, initial generation, model setup, checkpoints, and logging. Running the strategy file directly does not perform an experiment.

The repo-local `r4/run_r4.py` remains an optional runner for comparing individual source matrices or pooling them automatically. `r4/run_r4_pipeline.py` optionally chains generation, evaluation, summaries, and matrices. Neither is an extra required stage in the commands below. Some internal setup code is shared with these helpers.

## Before running

Run PowerShell commands from the GitHub repository root:

```powershell
Set-Location 'D:\NUS\AY2627_Year_4\AY2627_Y4_Sem1\DSA4213_NLP\dsa4213_grpproject\Agentic-Travel-Planner-Ablation-of-Verifications-'
```

Use a working Python environment with the project's requirements installed, the configured model credentials in `.env`, and the required ChinaTravel environment databases available. These commands assume `python` resolves to that environment. If needed, replace `python` with your interpreter's full path. The workspace's existing `..\.venv` currently points to a missing Python 3.12 executable; recreate or repair that environment before relying on it. For a fresh repo-local environment after installing Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The dataset loader resolves `subset_train` using the checked-in training UID list and origin map. Benchmark evaluation uses the reference queries saved by the run. No command below selects `subset_test`, a test partition, or `pilot5`. The dataset loader may fetch the underlying Hugging Face base datasets to locate training records; split membership is determined by the training allowlist.

**Current R4 pilot limits:** at most five distinct training queries and six repairs per query. The commands deliberately select the same first five sorted `subset_train` IDs for R0-R3 and R4. They do not run every UID in `subset_train`. To build R0-R3 evidence from all training UIDs, omit `--index $trainIds` in step 1; R4 still has its five-query pilot limit. Running R4 over the entire training subset would require a separate change to those limits.

This workflow learns the matrix from training observations and evaluates R4 on training queries. Those scores describe training behavior, not held-out generalization. R0-R3 share one initial plan per query within their paired run; the later R4 run generates a new initial plan, so its scores are not a comparison from the same initial plan as R0-R3.

## Full workflow

Run these blocks in the **same PowerShell session**. Each live generation stage makes model calls and incurs the configured provider's usage. Use a fresh batch ID for each run.

```powershell
$ErrorActionPreference = 'Stop'
$batch = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$model = 'deepseek/deepseek-chat'
$seed = 4213
$trainIds = @(Get-Content .\chinatravel\evaluation\default_splits\subset_train.txt |
    Where-Object { $_.Trim() } | ForEach-Object { $_.Trim() } |
    Sort-Object -Unique | Select-Object -First 5)
if ($trainIds.Count -ne 5) { throw 'Expected five training query IDs' }
$sourceId = "r0-r3-subset-train-$batch"
$r4Id = "r4-subset-train-$batch"
$sourceRun = ".\experiments\$sourceId"
$r4Run = ".\experiments\$r4Id"
$matrixRoot = ".\matrices\$sourceId"
$pooledMatrix = "$matrixRoot\pooled\main_matrix.csv"
```

### 1. Run R0-R3 on the selected training queries

One invocation runs all four strategies independently from the same initial state for each query. Each strategy has up to six repairs; R4's later run has its own six-repair budget.

```powershell
python -X utf8 .\run_experiments.py `
  --strategy R0 R1 R2 R3 `
  --splits subset_train --index $trainIds `
  --llm $model --lang en --max-steps 6 --seed $seed `
  --output-dir .\experiments --run-id $sourceId
if ($LASTEXITCODE -ne 0) { throw 'R0-R3 generation failed' }
```

Use `R3`, not `R3P`: they are separate registered strategies.

### 2. Evaluate the saved R0-R3 final plans

```powershell
python -X utf8 .\scripts\evaluate_repair_run.py --run-dir $sourceRun
if ($LASTEXITCODE -ne 0) { throw 'R0-R3 evaluation failed' }
```

This writes per-strategy benchmark exports and scores under `$sourceRun\benchmark_eval\`. It does not generate or repair plans.

### 3. Build R0-R3 process summaries

```powershell
python -X utf8 .\scripts\build_repair_summary.py --input $sourceRun
if ($LASTEXITCODE -ne 0) { throw 'R0-R3 summary failed' }
```

Output: `$sourceRun\summaries.csv`.

### 4. Build one regression matrix per strategy

The script is named **`build_regression_matrix.py`**. All four matrices use the formal attempt stream from step 1, filtered by exact strategy label.

```powershell
foreach ($strategy in @('R0', 'R1', 'R2', 'R3')) {
  python -X utf8 .\scripts\build_regression_matrix.py `
    --input "$sourceRun\attempts.jsonl" `
    --repair-strategy $strategy `
    --output-dir "$matrixRoot\$strategy"
  if ($LASTEXITCODE -ne 0) { throw "Matrix building failed for $strategy" }
}
```

Each directory contains `candidate_regression_count.csv`, `candidate_regression_support.csv`, `candidate_regression_rate.csv`, and `matrix_contributions.csv`, plus other diagnostics. These derive from repair attempts, not from benchmark scores or the summary CSV. If a strategy produces no usable contribution rows, the pooling stage rejects the empty provenance; gather more training attempts before pooling.

Without `--output-dir`, `scripts/build_regression_matrix.py` writes to `matrices/<repair-strategy>/` (for example `matrices/R0/`). It infers the strategy when the input contains exactly one strategy; an empty input without a strategy label uses `matrices/unclassified/`. The explicit paths above keep separate batches together and avoid reusing the same output directory across runs. Explicit relative output paths are resolved from the current working directory; defaults are anchored to the repository root.

### 5. Pool R0-R3 into the R4 main matrix

```powershell
python -X utf8 .\scripts\build_main_matrix.py `
  --splits subset_train --perspective candidate `
  --input-dir "$matrixRoot\R0" `
  --input-dir "$matrixRoot\R1" `
  --input-dir "$matrixRoot\R2" `
  --input-dir "$matrixRoot\R3" `
  --output $pooledMatrix
if ($LASTEXITCODE -ne 0) { throw 'Pooling failed' }
```

This validates that the inputs contain one matrix per R0-R3 strategy and only selected-split training UIDs. Pooling sums regression counts and eligible support, then divides. It does not average probabilities. Outputs: `$pooledMatrix`, the adjacent `main_matrix_manifest.json`, and a `<matrix-stem>_probabilities.csv` grid for viewing.

The main matrix has ten source and ten destination families, using `commonsense_repair` on both axes. Its CSV stores 100 cells with counts, attempt support, distinct-query support, probabilities, and per-strategy counts/support. The probability grid has ten rows and ten destination columns; `unavailable` means there is no measured probability, and `not_applicable` marks the structural diagonal.

The original nine destination columns pool the exported R0-R3 pivots. The commonsense destination is reconstructed from each source run's saved `queries/*/R*.json` repair histories when the input points to that run or its `regression_matrix/` folder. A changed repair must have one explicit mapped failing personal target, a complete commonsense PASS before the repair, and a complete commonsense result afterward. Only a PASS-to-FAIL transition counts as a regression. Rejected candidates never become the next before state. Unknown verification, no-ops, and already-failing destinations are excluded.

When a run has no saved histories, its commonsense destination counts/support stay blank. Available runs can still contribute, with supported cells marked `observed_partial` when a source run is missing or incomplete. The manifest records available strategies, exclusion counts, eligible attempts, and hashes of all history inputs. With the current subset training runs, R1 histories are unavailable; R0, R2, and `subset_train-r3-new` histories are available. An observed probability with only a few attempts or one query should not be interpreted as a reliable population estimate.

Without `--output`, both `scripts/build_main_matrix.py` and `r4/build_main_matrix.py` write to `matrices/pooled/main_matrix.csv` with an adjacent manifest. `r4/prepare_matrices.py` defaults to `matrices/training_matrices/`, and the optional full pipeline writes its output regression matrices to `matrices/<r4-run-id>/<strategy>/`.

Keep the source matrix directories and manifest available and unchanged: R4 checks their recorded hashes and training provenance. The run also stores an immutable snapshot of the pooled matrix and manifest inside `experiments/<r4-run-id>/inputs/pooled/`.

Optional setup check, without model calls (uses a **different** run ID):

```powershell
python -X utf8 .\run_experiments.py `
  --strategy R4 --r4-matrix $pooledMatrix `
  --splits subset_train --index $trainIds --query-limit 5 `
  --llm $model --lang en --max-steps 6 --seed $seed `
  --output-dir .\experiments --run-id "$r4Id-check" --dry-run
if ($LASTEXITCODE -ne 0) { throw 'R4 setup check failed' }
```

### 6. Run R4 using the pooled training matrix

```powershell
python -X utf8 .\run_experiments.py `
  --strategy R4 --r4-matrix $pooledMatrix `
  --splits subset_train --index $trainIds --query-limit 5 `
  --llm $model --lang en --max-steps 6 --seed $seed `
  --output-dir .\experiments --run-id $r4Id
if ($LASTEXITCODE -ne 0) { throw 'R4 generation failed' }
```

`--r4-matrix` accepts one pooled R0-R3 matrix and requires `--strategy R4` alone. It validates training IDs, matrix provenance, and pilot budgets before loading query records or initializing models. Without `--index`, it selects the first `--query-limit` sorted training IDs (default five). This entry point requires a fresh run ID; resume is not supported here.

The R4 algorithm reads the fixed historical matrix on each attempt and ranks current personal failures by estimated regression risk to passing constraint families. The prompt receives advisory risks and support; the model can choose which failures to repair together and may edit the whole plan. Shared verification records actual fixes/regressions. The matrix is not updated during the run. R4 uses the shared schedule of up to five personal repairs and one commonsense repair, with early stopping when appropriate.

### 7. Evaluate R4

Real saved plans from the run's named training or test split can be evaluated even when the guidance matrix is synthetic; the evaluation population records the actual split/partition and matrix provenance. Matrix evidence remains restricted to training data. Mock-runtime smoke runs remain excluded from benchmark scoring.

```powershell
python -X utf8 .\scripts\evaluate_repair_run.py --run-dir $r4Run
if ($LASTEXITCODE -ne 0) { throw 'R4 evaluation failed' }
```

The evaluation command scores the final accepted plan from each strategy checkpoint, using the same policy as R0-R3. R4 results go under `$r4Run\benchmark_eval\R4-<strategy-hash>\`. Both `benchmark_summary.json` and `evaluation_population.json` record `outcome_policy: final_accepted` and the actual evaluation split/partition. Missing final verification stays an empty failed plan in the evaluation population; the exporter never substitutes a selected, earlier, or rejected candidate.

`r4_selection_and_costs.json` and the per-query selected-outcome exports remain historical diagnostics and cost records. They do not determine the benchmark inputs. The normal evaluation command does not call `r4/evaluate_selected.py`. Older `benchmark_eval/selected/` scores describe the earlier best-outcome policy and are not the primary final-accepted results.

For additional trial-final diagnostics, pass `--include-trials` to the evaluation command.
These optional results go under `benchmark_eval/trials/<strategy>/`.

Optional R4 process summary:

```powershell
python -X utf8 .\scripts\build_repair_summary.py --input $r4Run
if ($LASTEXITCODE -ne 0) { throw 'R4 summary failed' }
```

## Files to inspect

Reusable matrices go under the repository's `matrices/`; experiment results and per-run input snapshots go under `experiments/`:

```text
experiments/
  r0-r3-subset-train-<batch>/
    run_manifest.json
    attempts.jsonl
    summaries.csv
    queries/
    benchmark_eval/
  r4-subset-train-<batch>/
    inputs/pooled/main_matrix.csv
    inputs/pooled/main_matrix_manifest.json
    run_manifest.json
    r4_run_metadata.json
    attempts.jsonl
    r4_selection_and_costs.json
    queries/<query>/
      reference/query.json
      initial_state.json
      final_state.json
      repair_history.json
      computational_cost.json
      final_itinerary.json
      trials/<strategy>-<hash>.json
    benchmark_eval/R4-<strategy-hash>/
matrices/
  r0-r3-subset-train-<batch>/
    R0/  R1/  R2/  R3/
    pooled/main_matrix.csv
    pooled/main_matrix_manifest.json
```

Per-query `repair_history.json` uses the R2 checkpoint field names:
`run_id`, `matrix_run_id`, `query_uid`, `repair_strategy`, `initial_plan_hash`,
`initial_raw_plan`, `initial_verification`, `final_accepted_plan`, `final_verification`,
`repair_history`, `repair_attempts`, `execution_status`, `stop_reason`, `exception`, and
`system_metrics`. R4 adds `matrices_used`, `selected_matrix_used`, `selected_source`,
`selected_step`, selection details, initial-generation usage, all-trial `costs`, and
complete per-trial checkpoints. Flattened history/attempt entries identify their trial
and matrix. Steps are local to each trial.

`final_state.json` contains the selected R4 output under `final_accepted_plan` and
`final_verification`; the raw final accepted state of each trial stays in `trials/`.
`reference/query.json` and the hashed `initial_state.json` retain the original inputs.
The former `r4_selected_outcome.json` is superseded by `final_state.json`.

Matrix labels are `R0`, `R1`, `R2`, `R3`, or `pooled`. Matrix records include the
snapshot path relative to the run, hashes, perspective, and synthetic-fixture status.
If the initial plan wins, `selected_source` is `initial` and `selected_matrix_used`
is null; `matrices_used` still lists the guidance matrices used by the trials.
Shared initialization is counted once; repair usage includes every trial.

To consolidate a historical run without model or benchmark calls:

```powershell
python -X utf8 -m r4.migrate_run --run-dir .\experiments\<r4-run-id>
```

Migration verifies initial states, references, trial evidence, selected plans, costs,
matrix hashes, and saved benchmark files. Existing trial-final benchmark scores are
preserved under `diagnostics/benchmark_trials/`; the migration helper retains the
historical selected-outcome layout. After migration, run `scripts/evaluate_repair_run.py`
to produce the primary final-accepted scores under `benchmark_eval/R4-<strategy-hash>/`.
`layout_migration.json` records verification and historical metadata. Historical
evidence and implementation hashes are preserved.

## Matrix and cost interpretation

`P(destination family j regresses | repair targets source family i) = count(i,j) / support(i,j)`.

Unsupported cells remain blank and use a recorded neutral `0.5` fallback in R4. Zero support is not learned evidence. The official matrix builder attributes personal regression evidence only to explicit single-target attempts; multi-target R0/R3 attempts may leave many cells unsupported. A successful pipeline does not establish that the matrix has useful statistical support.

`attempts.jsonl` records proposals, no-ops, rejections, failures, verification transitions, targets, scope, token usage, calls, and timings. `r4_selection_and_costs.json` and the per-query `computational_cost.json` include initial generation/verification once and all repair attempts, including attempts after the selected outcome. Missing provider usage remains `null`. Dollar costs remain `null`; token counts do not establish charges. Offline benchmark evaluation is separate post-processing.

## Offline checks from the repository root

```powershell
python -X utf8 -m unittest discover -s .\r4\tests -v
python -X utf8 .\r4\smoke_test.py --include-r1
```

The smoke check fabricates four source matrices and uses mock generation/verification, with no real model calls or query payloads. It reads the training UID allowlist. Outputs are clearly labeled synthetic under `experiments/r4_smoke/`; they are execution/accounting checks, not benchmark results.
