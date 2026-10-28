# Contributions Map

This document makes it clear which files are **original ChinaTravel** and which are **our team's
contribution** (added or edited), and **who** worked on each, so anyone can tell at a glance what
we built versus what came from upstream.

## How to read this

- The real, runnable code lives where it always has (mostly in `chinatravel/`). We did **not**
  move files, because the package imports files by their location — moving them would break the
  code. This document is the map instead.
- **Added** = a brand-new file created by our team. **Edited** = an original ChinaTravel file we
  modified.
- **Author(s)** are listed **most-active first**, derived from git history: for each file we count
  how many commits since the upstream import each person authored, and list them in that order.
  A file with several names means several people touched it; the first name did the most commits.
- Everything not listed below is **original ChinaTravel, unchanged**.

### The fork point

The pristine upstream import is commit **`d3a4e7b`** ("Import ChinaTravel", branch
`setup/chinatravel`). Everything after it on `main` is our work.

```bash
# full list of added/modified files since the import
git diff --name-status d3a4e7b main

# who authored commits touching a specific file (most recent first)
git log d3a4e7b..main --format='%an' -- <path/to/file> | sort | uniq -c | sort -rn

# every change we made to a specific file
git diff d3a4e7b main -- <path/to/file>
```

### Team members (git identities)

| Name | Git identity used |
| --- | --- |
| En Rui | `En Rui` / `enruifung` (`enruistudy@gmail.com`) |
| Nancy Shen | `NancyShen1` |
| Jun Hang Soo | `Jun Hang Soo` (`jhangsoo13@gmail.com`) |
| Whitney Woo | `Whitney Woo` / `Whitney` (`e1249241@u.nus.edu`) |
| Jiarui | `jiaruiiiii` (`sherryl1205@gmail.com`) |
| Thydaphea | `thydaphea` |

---

## At-a-glance ownership

- **Shared framework + R0 + English/data loading + splits:** En Rui, Nancy Shen
- **Usage instrumentation (tokens / tool calls) + evaluation/matrix core + dashboard + ablation
  comparisons:** Nancy Shen
- **R1 (targeted repair) + its tests:** Whitney Woo
- **R2 (protected/rollback repair) + its tests:** Jiarui, Jun Hang Soo
- **R3 (adaptive scope) + experiment runs + result tables + analysis docs:** Jun Hang Soo
- **R4 (matrix-guided) + the `r4/` matrix pipeline + the `frontend/` demo:** Thydaphea, Jun Hang Soo
- **Subset splits + rerun bookkeeping:** Jun Hang Soo, En Rui

---

## The five repair strategies (`chinatravel/agent/nesy_verifier/repair_strategies/`)

| File | Author(s) | What it is |
| --- | --- | --- |
| `base.py` | Nancy Shen, En Rui | Base class / interface every strategy implements. |
| `__init__.py` | Jun Hang Soo, Thydaphea, Jiarui, Whitney Woo, Nancy Shen, En Rui | Strategy registry (`STRATEGY_FACTORIES`) + `create_repair_strategy`. Touched by everyone as each strategy was registered. |
| `r0.py` | Nancy Shen, Jiarui, En Rui | R0 whole-plan regeneration (baseline). |
| `r1.py` | Whitney Woo, Nancy Shen | R1 targeted / slot repair. |
| `r2.py` | Jiarui, Jun Hang Soo | R2 protected repair (tracks and can reject regressions). |
| `r3.py` | Jun Hang Soo, Nancy Shen | R3 adaptive-scope repair (slot → day → plan). |
| `r4.py` | Thydaphea, Jun Hang Soo | R4 constraint-interdependency-guided repair (reads the learned matrix). |

## Shared framework (`chinatravel/agent/nesy_verifier/`)

| File | Author(s) | What it is |
| --- | --- | --- |
| `shared_verifier.py` | Nancy Shen, En Rui | Shared verifier used by all strategies. |
| `shared_repair_loop.py` | Nancy Shen, En Rui, Jun Hang Soo, Whitney Woo | The verify-and-repair loop (scheduler, accept/reject, per-attempt logging). |
| `initial_state.py` | Nancy Shen | Builds the initial repair state. |
| `llm_modulo.py` *(edited)* | Nancy Shen, En Rui, Thydaphea | Refactored `solve()` for pluggable repair strategies; usage tracking; Windows path fixes. |
| `prompts/llm_modulo.py` *(edited)* | En Rui | Prompt rules (inner-city transport nesting, allowed activity types, required times). |
| `verifier/commonsense_constraint_nl.py` *(edited)* | En Rui, Whitney Woo | Language-aware fix: check English itineraries against the English sandbox. |

## Usage instrumentation (`chinatravel/agent/`)

| File | Author(s) | What it is |
| --- | --- | --- |
| `model_usage.py` | En Rui, Nancy Shen | Token/call counters + instrumented HTTP client. (En Rui fixed an `openai`/`httpx` clash that silently failed live calls.) |
| `system_usage.py` | Nancy Shen | `tool_api` decorator + tool/verification usage tracking. |
| `llms.py` *(edited)* | Nancy Shen | Usage instrumentation on `OpenAICompatibleLLM`. |
| `load_model.py` *(edited)* | Nancy Shen, En Rui | `repair_strategy` threading, per-strategy output dirs, OpenRouter support. |
| `utils.py` *(edited)* | En Rui, Whitney Woo | Windows-safe `Logger` (creates parent dirs, long-path prefix) + flush/close robustness. |
| `environment/world_env.py`, `environment/tools/**/apis.py` *(edited)* | Nancy Shen | `@tool_api` instrumentation on the sandbox tool methods. |

## Evaluation & matrix (`chinatravel/evaluation/`)

| File | Author(s) | What it is |
| --- | --- | --- |
| `regression_matrix.py` | Nancy Shen, En Rui, Whitney Woo | Builds the per-constraint-family regression matrix `M`. |
| `constraint_families.py` | Nancy Shen | Groups constraints into the 9 families. |
| `repair_attempt.py` | Nancy Shen | Per-attempt record schema + logging. |
| `repair_metrics.py` | Nancy Shen | Repair success / efficiency metrics. |
| `repair_comparison.py` | Nancy Shen, Thydaphea | Paired before/after comparison + run orchestration. |
| `edit_footprint.py` | Nancy Shen | Measures how much a repair changed. |
| `train_test_split.py` | Nancy Shen | Train/test split logic (leakage control). |
| `export_final_plans.py` | Jun Hang Soo, Thydaphea, Nancy Shen | Export final plans from a run. |
| `named_place_translation.py` | Jun Hang Soo | Translate Chinese place names to English at scoring time. |
| `rank.py` *(edited)* | En Rui | Scoring/rank adjustments. |
| `CONSTRAINT_FAMILIES.md`, `REPAIR_METRICS.md` | Nancy Shen | Specs/docs. |
| `REGRESSION_MATRIX.md` | Nancy Shen, Jun Hang Soo, En Rui | Matrix contract. |
| `REPAIR_ATTEMPTS.md`, `REPAIR_COMPARISON.md` | Jun Hang Soo, Nancy Shen | Attempt-log + comparison contracts. |

## Data loading & splits (`chinatravel/`)

| File | Author(s) | What it is |
| --- | --- | --- |
| `data/load_datasets.py` *(edited)* | En Rui | English query loading from the bilingual HF dataset; `hard_logic_py` parsing; train/test + stratified subset loading; `--lang en` default. |
| `evaluation/default_splits/subset_train.txt`, `subset_test.txt` | Jun Hang Soo, En Rui | The budget-sized stratified subsets used for the real experiments. |
| `evaluation/default_splits/pilot5.txt`, `combined_*`, `medium_*`, `p*base50`, `human1000`, `preference_base50` | En Rui | Pilot + stratified + preference UID lists. |
| `evaluation/splits/subset_origin.json` | Jun Hang Soo, En Rui | Maps subset UIDs to their base HF split (for difficulty slicing). |
| `evaluation/splits/combined_origin.json`, `pilot5_origin.json`, `medium_train_test_seed42.json` | En Rui | Origin maps / split manifests. |
| `symbol_verification/category_labels.py`, `category_taxonomy.json`, `CATEGORY_LABELS.md` | Nancy Shen | Constraint-category taxonomy. |
| `symbol_verification/dsl.py` *(edited)* | Nancy Shen | DSL execution changes. |
| `symbol_verification/concept_func.py` *(edited)* | En Rui | Concept-function fix. |

## R4 matrix pipeline (`r4/`)

Almost entirely **Thydaphea**, with **Jun Hang Soo** on several files. Includes the strategy
driver (`strategy.py`, `run_r4.py`, `run_r4_pipeline.py`), matrix building/selection
(`build_main_matrix.py`, `prepare_matrices.py`, `select_outcomes.py`, `commonsense_evidence.py`),
safety/migration helpers, the committed learned matrix
(`main_matrix_from_subset_train_r0_r3_10x10.csv` + `_probabilities.csv` + manifest), `README.md`,
and the `r4/tests/`.

## Scripts (`scripts/`)

| File | Author(s) |
| --- | --- |
| `experiment_setup/setup_project.py`, `experiment_setup/build_train_test_split.py` | Jun Hang Soo |
| `matrix_building/build_regression_matrix.py`, `matrix_building/build_main_matrix.py` | Jun Hang Soo |
| `result_analysis/evaluate_repair_run.py`, `build_repair_summary.py` | Jun Hang Soo |
| `result_analysis/build_test_result_tables.py` | Jun Hang Soo, Jiarui |
| `result_analysis/ablation_comparisons/*` | Nancy Shen |
| `analyze_repair_strategies.py`, `repair_analysis_r4.py`, `REPAIR_ANALYSIS.md` | Nancy Shen (+ Whitney Woo on `analyze_repair_strategies.py`) |

> Note: `scripts/experiment_setup/setup_project.py` was originally stubbed by En Rui and is now
> primarily maintained by Jun Hang Soo (git shows Jun Hang Soo with the most commits).

## Dashboard (`dashboard/`)

**Nancy Shen** — the entire Streamlit results dashboard (`app.py`, `pages/`, `components/`,
`data_loader.py`, `metrics.py`, its `tests/`, and the `*_REPORTING.md` docs) plus
`.streamlit/config.toml` and `requirements-dashboard.txt` / `requirements-analysis.txt`.

## Frontend demo (`frontend/`)

**Thydaphea** (with Jun Hang Soo on the README) — the planner demo app (`app.py`, `planner.py`,
`presentation.py`, `history.py`, `replay.py`, `storage.py`, demo data) and its replay tests.

## Experiments (`experiments/`) — who ran what

These folders hold run outputs (`attempts.jsonl`, `summaries.csv`, benchmark eval, regression
matrices, per-query plans). Attributed by who committed the run:

| Run | Ran by |
| --- | --- |
| `subset_train-r0` | Jun Hang Soo |
| `subset_train-r1` | Whitney Woo |
| `subset_train-r2` | Jiarui |
| `subset_train-r3-new` | En Rui |
| `subset_test-r0` | En Rui (5 queries reran after provider failures) |
| `subset_test-r1` | Whitney Woo |
| `subset_test-r2` | Jun Hang Soo |
| `subset_test-r3` | Jun Hang Soo (+ Jiarui); 1 query reran |
| `subset_test-r4` | Thydaphea (matrix-guided) |
| `archives_runs/`, `r4_signal_exploration/`, comparison reports | Jun Hang Soo |

Workflow/analysis docs: `experiments/Commands_to_test_queries.md` (Jun Hang Soo, Nancy Shen),
`REPAIR_METHOD_COMPARISON.md` + `repair_comparison_report.md` (Jun Hang Soo).
`test_result_analysis/` tables and README (Jun Hang Soo, Jiarui).

## Notebooks & docs (root)

| File | Author(s) |
| --- | --- |
| `framework_r0.ipynb`, `train_test_split_r0.ipynb` | En Rui (+ Jun Hang Soo, Nancy Shen) |
| `HANDOVER.md` | En Rui (+ Jun Hang Soo, Nancy Shen) |
| `README.md` *(edited)* | En Rui, Jun Hang Soo, Nancy Shen, Thydaphea |
| `CONTRIBUTIONS.md` | En Rui, Nancy Shen, Jun Hang Soo |
| `CLAUDE.md` | Jun Hang Soo, Jiarui |
| `docs/PRD_R3_adaptive_repair.md` | Nancy Shen, Jun Hang Soo |
| `docs/R2_rollback_how_it_works.pdf` | Jiarui |
| `matrices/README.md` | Jun Hang Soo, Thydaphea |

## Runners & project config (root)

| File | Author(s) | What |
| --- | --- | --- |
| `run_experiments.py` | Thydaphea, Nancy Shen | Canonical single-strategy study runner. |
| `run_exp.py` *(edited)* | Jun Hang Soo, Thydaphea, En Rui, Nancy Shen | `--repair_strategy` flag + runtime wiring. |
| `eval_exp.py` *(edited)* | Nancy Shen, En Rui | Eval entrypoint changes. |
| `eval_tpc.py`, `run_tpc.py` *(edited)* | En Rui | Default-language / wiring tweaks. |
| `requirements.txt`, `pyproject.toml` *(edited)* | En Rui | `pyarrow`, `python-dotenv`, narrowed `openai` pin (httpx fix). |
| `.env.example` (added), `.gitignore`, `chinatravel/.gitignore` *(edited)* | En Rui | Env template + ignore/track rules (track all `*.txt` splits). |

## Tests (`tests/`)

| File | Author(s) |
| --- | --- |
| `test_r1.py`, `test_r1_integration.py`, `test_r1_transport_cost_integration.py` | Whitney Woo |
| `test_r1_shared_loop.py` | Whitney Woo, Jun Hang Soo |
| `test_r2_rollback_repair.py` | Jiarui, Jun Hang Soo |
| `test_r3_adaptive_repair.py` | Jun Hang Soo, Nancy Shen |
| `test_frontend_replay.py`, `test_frontend_replay_app.py` | Thydaphea |
| `test_named_place_translation.py`, `test_commonsense_round_metrics.py`, `test_repeat_request_cache.py`, `test_subset_splits.py` | Jun Hang Soo |
| `test_ablation_comparisons.py`, `test_benchmark_postprocessing.py`, `test_category_labels.py`, `test_constraint_families.py`, `test_edit_footprint.py`, `test_repair_attempt_logging.py`, `test_repair_efficiency.py`, `test_repair_metrics.py`, `test_system_efficiency.py` | Nancy Shen |
| `test_analyze_repair_strategies.py` | Nancy Shen, Whitney Woo |
| `test_regression_matrix.py` | Nancy Shen, Jun Hang Soo, En Rui, Whitney Woo |
| `test_repair_comparison.py` | Nancy Shen, Jun Hang Soo, Thydaphea |
| `test_repair_intent_contract.py` | Nancy Shen, Whitney Woo, Jun Hang Soo |
| `test_repair_scheduling.py` | Nancy Shen, En Rui, Jun Hang Soo |
| `test_shared_verifier_reliability.py` | Nancy Shen, En Rui |
| `test_train_test_split.py` | Nancy Shen, Jun Hang Soo, En Rui |
| `test_runtime_configuration.py` *(edited)* | Whitney Woo |

---

*This map reflects the diff between `d3a4e7b` (ChinaTravel import) and `main`, with authorship taken
from git history (most-active author first per file). Experiment output files under
`experiments/**` and generated tables under `test_result_analysis/**` are summarised by run rather
than listed individually. To refresh after new work, regenerate with the commands in "The fork
point" above. (There is a stray empty file named `python` at the repo root, added accidentally —
safe to delete.)*
