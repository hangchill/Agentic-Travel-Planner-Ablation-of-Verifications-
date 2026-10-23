# Experiments — workflow

| # | Step | Command | Output |
| --- | --- | --- | --- |
| 1 | Run strategy | `python run_experiments.py --strategy <STRATEGY> --splits <SPLIT> --llm deepseek/deepseek-chat --lang en --max-steps <MAX_STEPS> --output-dir experiments --run-id <RUN_ID>` | Run folder `experiments/<RUN_ID>/` (`queries/`, `attempts.jsonl`, `run_manifest.json`) |
| 2 | Benchmark eval | `python scripts/evaluate_repair_run.py --run-dir experiments/<RUN_ID>` | `experiments/<RUN_ID>/benchmark_eval/` (`schema`, `commonsense`, `logical_py` CSVs) |
| 3 | Summaries | `python scripts/build_repair_summary.py --input experiments/<RUN_ID>` | `experiments/<RUN_ID>/summaries.csv` |
| 4 | Regression matrix | `python scripts/build_regression_matrix.py --input experiments/<RUN_ID>/attempts.jsonl --output-dir experiments/<RUN_ID>/regression_matrix --repair-strategy <STRATEGY>` | `experiments/<RUN_ID>/regression_matrix/` CSVs |

On Windows, run `$env:PYTHONUTF8 = "1"` in the terminal first, or step 2 fails to read the saved JSON.

## Populating the placeholders

- **`<STRATEGY>`**: one of `R0`, `R1`, `R3`, `R3P`. Use the same value in steps 1 and 4.
- **`<SPLIT>`**: a file name, without `.txt`, from `chinatravel/evaluation/default_splits/`, e.g. `pilot5`, `subset_train`, `subset_test`.
- **`<MAX_STEPS>`**: the repair budget. Use `6` for all registered strategies (or an explicit smaller budget).
- **`<RUN_ID>`**: a new folder name for this run, written as `<split>-<strategy>` in lowercase, e.g. `subset_train-r3p`. Use the same value in all four steps. If a run stops partway, rerun step 1 with the same `<RUN_ID>` plus `--resume`.


## Repair strategies => tests what splits?
R0 :  
 - subset_test (for baseline results)
 - Subset_train (Expected that matrix will be noisiest): can be left for last (to save cost)  

R1 - R3 : 
- Subset_train (Just to learn the matrix), 
- Subset_test (for results using different repairs)

R4 : 
- ONLY Subset_test (using learned matrix for hypothesis results)
1. Scenario 1 : Single matrix from R0 to R4
2. Scenario 2 : Fused matrix combining into 1 universal matrix (weighted sum or smth) 

## Evaluation: 
Main Comparisons can only be made on results obtained by subset_test

We can do comparisons on results of train set (but theres no point to do that) 
 - Except to gather more metrics just to double check with another split that its not just coincidence (eg. hopefully a certain metric scores similar to test set and train set )