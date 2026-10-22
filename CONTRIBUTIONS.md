# Contributions Map

This document makes it clear which files are **original ChinaTravel** and which
are **our team's contribution** (added or edited), so anyone can tell at a glance
what we built versus what came from upstream.

## How to read this

- The real, runnable code lives where it always has (mostly in `chinatravel/`).
  We did **not** move files, because the package imports files by their location —
  moving them would break the code. This document is the map instead.
- **Added** = a brand-new file created by our team.
- **Edited** = an original ChinaTravel file we modified (the original version is
  the one upstream; our changes are summarized here).
- **Author** = the team member(s) who contributed to it.
- Everything not listed below is **original ChinaTravel, unchanged**.

### Reproduce the exact diff yourself

The authoritative source of truth is git. The commit `d3a4e7b` ("Import ChinaTravel")
is the pristine upstream import; everything after it on `main` is our work.

```bash
# full list of added/modified files
git diff --name-status d3a4e7b main

# see every change we made to a specific file
git diff d3a4e7b main -- <path/to/file>
```

---

## Our contribution

### New modules — agent / repair framework (`chinatravel/agent/`)

| File | Author | What it is |
| --- | --- | --- |
| `chinatravel/agent/model_usage.py` | Nancy Shen (+ En Rui fix) | LLM usage instrumentation: token/call counters and an instrumented HTTP client wrapper. (En Rui later fixed an `openai`/`httpx` version clash here — see note below — that was making every live model call fail silently.) |
| `chinatravel/agent/system_usage.py` | Nancy Shen | `tool_api` decorator and system-usage tracking for tool/verification calls. |
| `chinatravel/agent/nesy_verifier/shared_verifier.py` | En Rui, Nancy Shen | Shared verifier used across repair strategies. |
| `chinatravel/agent/nesy_verifier/shared_repair_loop.py` | En Rui, Nancy Shen | Shared repair loop that drives the verify-and-repair cycle. |
| `chinatravel/agent/nesy_verifier/initial_state.py` | Nancy Shen | Builds the initial repair state for the LLM-Modulo agent. |
| `chinatravel/agent/nesy_verifier/repair_strategies/__init__.py` | En Rui, Nancy Shen | Factory (`create_repair_strategy`) for selecting a repair strategy. |
| `chinatravel/agent/nesy_verifier/repair_strategies/base.py` | En Rui | Base class for repair strategies. |
| `chinatravel/agent/nesy_verifier/repair_strategies/r0.py` | En Rui, Nancy Shen | R0 baseline repair strategy. |

### New modules — evaluation (`chinatravel/evaluation/`)

| File | Author | What it is |
| --- | --- | --- |
| `chinatravel/evaluation/constraint_families.py` | Nancy Shen | Groups constraints into families for analysis. |
| `chinatravel/evaluation/edit_footprint.py` | Nancy Shen | Measures the edit footprint of a repair. |
| `chinatravel/evaluation/regression_matrix.py` | Nancy Shen | Builds the per-constraint regression matrix (`build_regression_matrix`). |
| `chinatravel/evaluation/repair_attempt.py` | Nancy Shen | Repair-attempt data model and logging. |
| `chinatravel/evaluation/repair_comparison.py` | Nancy Shen | Paired before/after repair comparison. |
| `chinatravel/evaluation/repair_metrics.py` | Nancy Shen | Repair success / efficiency metrics. |
| `chinatravel/evaluation/train_test_split.py` | Nancy Shen | Train/test split logic for the evaluation data. |
| `chinatravel/evaluation/CONSTRAINT_FAMILIES.md` | Nancy Shen | Docs for constraint families. |
| `chinatravel/evaluation/REGRESSION_MATRIX.md` | Nancy Shen | Docs for the regression matrix. |
| `chinatravel/evaluation/REPAIR_ATTEMPTS.md` | Nancy Shen | Docs for repair-attempt logging. |
| `chinatravel/evaluation/REPAIR_COMPARISON.md` | Nancy Shen | Docs for repair comparison. |
| `chinatravel/evaluation/REPAIR_METRICS.md` | Nancy Shen | Docs for repair metrics. |

### New top-level scripts / notebook

| File | Author | What it is |
| --- | --- | --- |
| `framework_r0.ipynb` | En Rui | Notebook explaining the R0 framework implementation and tests, with runnable proof cells. |
| `train_test_split_r0.ipynb` | En Rui | Notebook documenting the deterministic train/test split and how it is wired into the experiment runner, with runnable proof cells. |
| `chinatravel/evaluation/splits/medium_train_test_seed42.json` | En Rui | Saved train/test split manifest (seed 42) for the `medium` queries. |
| `chinatravel/evaluation/default_splits/medium_train.txt`, `medium_test.txt` | En Rui | Train/test UID lists consumed by `--splits medium_train` / `medium_test`. |
| `chinatravel/evaluation/default_splits/combined_train.txt`, `combined_test.txt` | En Rui | Stratified 70/30 train/test UID lists spanning `easy`+`medium`+`human` (same difficulty mix on both sides), consumed by `--splits combined_train` / `combined_test`. |
| `chinatravel/evaluation/default_splits/subset_train.txt`, `subset_test.txt` | En Rui | Budget-sized 100-query stratified subset (69 train / 31 test, ~equal easy/medium/human on both sides), consumed by `--splits subset_train` / `subset_test`. Used for the actual DeepSeek-V3 experiments given limited API credit. |
| `chinatravel/evaluation/default_splits/pilot5.txt` | En Rui | Shared 5-query pilot set (2 easy / 1 medium / 2 human) that R0 was run on first. Every team member runs their strategy (R1–R4) on `--splits pilot5` for an initial apples-to-apples comparison before scaling to the full subset. |
| `chinatravel/evaluation/splits/combined_origin.json`, `subset_origin.json` | En Rui | Map each stratified-split UID to its base Hugging Face split, so the loader fetches each query from the right place (and results can be sliced by difficulty). |
| `experiments/r0_combined_sample/*.json` | En Rui | Committed R0 baseline results (English, `--refine_steps 5`) for a 5-query sample spanning the combined split (easy/medium/human), so teammates get identical result files without re-running the paid LLM. Produced and documented by `train_test_split_r0.ipynb`. |
| `experiments/r0_medium_sample/*.json` | En Rui | Earlier R0 sample on 5 `medium` queries, kept for reference. |
| `run_repair_comparison.py` | Nancy Shen | Entry point to run the paired repair comparison experiment. |
| `scripts/build_regression_matrix.py` | Nancy Shen | Build the regression matrix from logged attempts. |
| `scripts/build_train_test_split.py` | Nancy Shen | Generate the train/test split config. |
| `scripts/setup_project.py` | En Rui | Download/setup the ChinaTravel sandbox and configure `.env`. |

> Note: these files stay at their current locations because the test suite imports
> them by path (e.g. `import run_repair_comparison`, `from scripts.build_regression_matrix import ...`).
> Moving them would break those tests.

### New tests (`tests/`)

| File | Author |
| --- | --- |
| `tests/test_constraint_families.py` | Nancy Shen |
| `tests/test_edit_footprint.py` | Nancy Shen |
| `tests/test_regression_matrix.py` | Nancy Shen |
| `tests/test_repair_attempt_logging.py` | Nancy Shen |
| `tests/test_repair_comparison.py` | Nancy Shen |
| `tests/test_repair_efficiency.py` | Nancy Shen |
| `tests/test_repair_intent_contract.py` | Nancy Shen |
| `tests/test_repair_metrics.py` | Nancy Shen |
| `tests/test_shared_verifier_reliability.py` | En Rui |
| `tests/test_system_efficiency.py` | Nancy Shen |
| `tests/test_train_test_split.py` | Nancy Shen |

---

## Edited original files

The original versions are upstream ChinaTravel (commit `d3a4e7b`). Our changes:

| File | Author | What we changed |
| --- | --- | --- |
| `chinatravel/agent/nesy_verifier/llm_modulo.py` | En Rui, Nancy Shen | Major: refactored `solve()` to support pluggable repair strategies (`repair_strategy`), split out initial-plan generation and repair-state preparation, and wired in model/system usage tracking. Also sanitizes the model name in the per-problem log directory (e.g. `openai/gpt-4.1` -> `openai_gpt-4.1`) so logging works on Windows, where a `/` in a path component is treated as a directory separator. |
| `chinatravel/agent/llms.py` | Nancy Shen | Added LLM usage instrumentation to `OpenAICompatibleLLM` (instrumented HTTP client, `reset_usage`/`usage_snapshot`, usage recording around requests). |
| `chinatravel/agent/load_model.py` | En Rui | Added a `repair_strategy` parameter threaded into the runtime; separate output dirs per strategy; OpenRouter support in `init_llm` (passes the full `provider/model` id when using an OpenRouter base URL). |
| `chinatravel/agent/nesy_verifier/prompts/llm_modulo.py` | En Rui | Added prompt rules: inner-city transport must live in `transports`, restricted the set of valid activity types, and required `start_time`/`end_time`. |
| `chinatravel/data/load_datasets.py` | En Rui | (1) `_validate_query_record` now parses string-encoded `hard_logic_py` (from the Hugging Face dataset) into real lists via `ast.literal_eval`, then validates list-of-strings structure. (2) English query loading now reads from the bilingual Hugging Face dataset (previously it required local files that did not exist): added `_adapt_record_to_english()` which promotes `nature_language_en` to `nature_language` and translates `start_city`/`target_city` to English via `CITY_NAMES`, so `--lang en` runs end-to-end. (3) Added train/test subset loading: `_hf_base_split()` and `_read_split_uids()` let a split named `<base>_train`/`<base>_test` reuse the base Hugging Face split and filter by the UIDs in `default_splits/<name>.txt`, so `--splits medium_train` works without local query files. (4) Added stratified combined-split loading: `_load_combined_split()` / `_combined_origin_map()` handle `--splits combined_train`/`combined_test`, fetching each UID from its origin base split (easy/medium/human) via `combined_origin.json`. (5) Default `--lang` changed to `en`. |
| `chinatravel/environment/world_env.py` | Nancy Shen | Added `@tool_api("next_page")` instrumentation to `next_page`. |
| `chinatravel/environment/tools/accommodations/apis.py` | Nancy Shen | Added `@tool_api` decorators to tool methods (`keys`, `select`, `nearby`). |
| `chinatravel/environment/tools/attractions/apis.py` | Nancy Shen | Added `@tool_api` decorators (`keys`, `select`, `id_is_open`, `nearby`, `get_type_list`). |
| `chinatravel/environment/tools/restaurants/apis.py` | Nancy Shen | Added `@tool_api` decorators (`keys`, `select`, `id_is_open`, `nearby`, `restaurants_with_recommended_food`, `get_cuisine_list`). |
| `chinatravel/environment/tools/intercity_transport/apis.py` | Nancy Shen | Added `@tool_api("intercity_transport_select")` to `select`. |
| `chinatravel/environment/tools/transportation/apis.py` | Nancy Shen | Added `@tool_api("goto")` to `goto`. |
| `chinatravel/environment/tools/poi/apis.py` | Nancy Shen | Added `@tool_api("poi_lat_lon_search")` to `search`. |
| `run_exp.py` | En Rui | Added a `--repair_strategy {R0..R4}` CLI flag and passed it into `create_agent_runtime`. |
| `requirements.txt` | En Rui | Added `pyarrow==19.0.1`; narrowed the `openai` pin's upper bound as part of the httpx-compatibility fix. |
| `pyproject.toml` | En Rui | Narrowed the `openai` dependency upper bound as part of the httpx-compatibility fix. |
| `README.md` | En Rui | Added our setup/usage instructions (OpenRouter, repair strategies, framework notes). |
| `.gitignore` / `chinatravel/.gitignore` | En Rui | Added ignore rules for our caches/outputs. |
| `.env.example` | En Rui | Added example environment variables for our API configuration (new file). |

---

*This map reflects the diff between `d3a4e7b` (ChinaTravel import) and `main`.
If you add or edit files, please update the relevant row, or regenerate the lists
with `git diff --name-status d3a4e7b main`.*
