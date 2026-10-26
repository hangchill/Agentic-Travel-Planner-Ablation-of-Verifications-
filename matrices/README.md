# R4 matrix storage

Keep reusable regression matrices and pooled R4 inputs here.

- `scripts/build_regression_matrix.py` defaults to `<strategy>/`, such as `R0/`.
- Both main-matrix builder entry points default to `pooled/main_matrix.csv` plus `pooled/main_matrix_manifest.json`.
- The [full workflow](../r4/README.md) uses `<source-run-id>/R0/` through `R3/` and `<source-run-id>/pooled/` to keep batches separate.

Explicit `--output-dir` and `--output` paths override these defaults. Rerunning with the same output paths replaces the existing matrix files. Keep source directories and manifests unchanged after pooling because R4 validates their provenance and hashes. If moving existing matrices here, rebuild the pooled matrix and manifest from their new source paths.

Experiment results remain under `experiments/`. Per-run matrix snapshots stay alongside the run inputs there. Synthetic smoke matrices remain within the clearly labeled smoke-test output directory.
