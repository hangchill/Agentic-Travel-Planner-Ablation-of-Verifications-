# DSA4213 Group Project — Verification-Guided Travel Planner

This repository is adapted from the original [ChinaTravel benchmark](https://github.com/search?q=ChinaTravel&type=repositories) for our DSA4213 group project.

Our project investigates whether modelling constraint interdependencies can improve verification-guided repair in LLM-based travel planning.

We use the existing ChinaTravel planner and compare five repair strategies.

| Strategy | Description |
|---|---|
| R0 | Whole-plan regeneration (baseline) |
| R1 | Targeted repair |
| R2 | Protected repair |
| R3 | Adaptive-scope repair |
| R4 | Constraint-interdependency-guided repair |

### Verification is held constant (the experimental control)

Across all five strategies, **only the repair step is ablated — the verification is the
same.** Every strategy's plan is checked by the one shared verifier
(`chinatravel/agent/nesy_verifier/shared_verifier.py::verify_plan`), which re-checks the
**whole itinerary against all constraints** after every repair attempt. R0–R4 differ only in
*which parts of the plan may change* during repair, never in *how the plan is checked*. This
keeps the comparison apples-to-apples: any difference in results is attributable to the repair
method, not to the verifier.

Note there are two "baselines" in the repo, and they are not the same:

- **Project R0** (`--repair_strategy R0`) runs through the shared repair loop and shared
  verifier — **the same verification R1–R4 use**. This is the baseline we ablate against.
- **Legacy ChinaTravel** (no `--repair_strategy`) uses the original, separate verification
  path and is *not* the comparison baseline.

The original ChinaTravel documentation is preserved below this section.

## Quick Setup for Group Members

### 1. Clone the repository

```bash
git clone <YOUR-REPOSITORY-URL>
cd Agentic-Travel-Planner-Ablation-of-Verifications-
```

### 2. Set up Python

Use Python 3.12 (tested with 3.12.8).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

For Windows, activate the environment using `.venv\Scripts\activate`.

### 3. Download the ChinaTravel sandbox

```bash
python scripts/setup_project.py
```

This automatically downloads and extracts **both** official sandboxes:

- English sandbox → `chinatravel/environment/database_en/` (used by default)
- Chinese sandbox → `chinatravel/environment/database/`

You do not need to download either sandbox manually. Our experiments default to the English sandbox (`--lang en`).

### 4. Configure OpenRouter

Copy the environment template:

```bash
cp .env.example .env
```

For Windows PowerShell, use `Copy-Item .env.example .env`.

Open `.env` and replace the placeholder with our OpenRouter API key (found in CANVAS).

```dotenv
CHINATRAVEL_OPENAI_API_KEY=OUR_GROUP_API_KEY
CHINATRAVEL_OPENAI_BASE_URL=https://openrouter.ai/api/v1
```

On macOS/Linux, load the environment variables:

```bash
set -a
source .env
set +a
```



**Do not commit `.env` to GitHub.**

### 5. Run R0 to check your setup

```bash
python run_exp.py \
  --agent LLM-modulo \
  --repair_strategy R0 \
  --llm deepseek/deepseek-chat \
  --splits medium \
  --index e20241028160845920703 \
  --refine_steps 5 \
  --oracle_translation
```

This runs one medium-difficulty ChinaTravel case using the shared R0 framework. We use **DeepSeek V3** (`deepseek/deepseek-chat`) through OpenRouter as our model — it is far cheaper than GPT-4.1 (~15x on input tokens) and runs the full pipeline cleanly, which lets us afford the repair experiments on our limited budget.

`--lang en` is the default, so it no longer needs to be passed (add `--lang zh` only if you specifically want the Chinese sandbox). For the comparative experiments, keep the repair budget fixed at `--refine_steps 5` across every strategy (R0–R4) so the comparison is fair and R3 has room to escalate its repair scope.

**English queries:** the ChinaTravel query files on Hugging Face are bilingual — each query carries both a Chinese (`nature_language`) and an English (`nature_language_en`) version. When you run with `--lang en`, the loader automatically downloads the same dataset, uses the English query text, and translates the city names to English so everything resolves against the English sandbox (`database_en`). No separate English query download or local query files are needed; an English request produces an English itinerary.

**Note:** Running any model through OpenRouter incurs API costs (DeepSeek V3 is our low-cost default).

Results are saved under `results/`, while repair histories and logs are saved under `cache/`.

## For Teammates — Implementing R1–R4

The shared framework and R0 are already implemented. You do not need to rewrite the original planner.

### Main files

All these files are inside `chinatravel/agent/nesy_verifier/`.

| File | Purpose |
|---|---|
| `repair_strategies/base.py` | Common interface for all repair methods |
| `repair_strategies/r0.py` | Example implementation |
| `shared_verifier.py` | Checks constraints and separately records technical verification errors |
| `shared_repair_loop.py` | Handles repair attempts, acceptance/rejection and logging |
| `llm_modulo.py` | Main agent and strategy selection |

For implementation and historical R0 results, see `framework_r0.ipynb` and
`train_test_split_r0.ipynb`. The current subset UID lists are `subset_train`
(60 queries: 20 easy / 20 medium / 20 human) and `subset_test` (30 queries:
10 easy / 10 medium / 10 human), balanced equally across difficulty on both
sides. The shared `pilot5` set (5 queries: 2 easy / 1 medium / 2 human) is a
subset of `subset_train`. The full-dataset `combined_train` / `combined_test`
and `medium_train` / `medium_test` splits are also available.
Use the same saved population and model settings when comparing strategies.

**Runner responsibilities:** `run_experiments.py` is the canonical registered
repair-strategy study runner. `run_exp.py` remains the general ChinaTravel
launcher for other agents, baselines, and original LLM-modulo workflows.

```bash
python run_experiments.py --strategy R0 --splits pilot5 --max-steps 6 \
  --lang en --llm YOUR_PROVIDER_MODEL_ID --run-id pilot5-r0
python run_experiments.py --strategy R1 --splits pilot5 --max-steps 6 \
  --lang en --llm YOUR_PROVIDER_MODEL_ID --run-id pilot5-r1
```

Raw evidence is written to `results/experiments/<RUN_ID>/` (gitignored), including
`run_manifest.json`, `attempts.jsonl`, and query checkpoints. Resume with the same
arguments plus `--resume`; use `--retry-failed` with resume to retry failed pairs.
This is checkpoint-based resume, not skipping arbitrary existing final-plan files.

Run the independent offline stages explicitly:

```bash
python scripts/build_repair_summary.py --input results/experiments/pilot5-r1
python scripts/evaluate_repair_run.py --run-dir results/experiments/pilot5-r1
python scripts/build_regression_matrix.py \
  --input results/experiments/pilot5-r1/attempts.jsonl \
  --output-dir results/experiments/pilot5-r1/regression_matrix
```

See [the experiment workflow](experiments/Commands_to_test_queries.md) and
[the evidence/summary contract](chinatravel/evaluation/REPAIR_COMPARISON.md).
Registered implementations are currently R0, R1, R2, R3, and R4. Registered strategies use the shared scheduler (personal repairs first, at most five, then repeated commonsense repairs; all rounds used unless the plan passes), capped at six
proposals; explicit smaller budgets are respected.

### How to implement your strategy

Create your assigned file inside `repair_strategies/`, such as `r1.py`, `r2.py`, `r3.py` or `r4.py`.

Follow the interface in `base.py`:

```python
def repair(self, problem, raw_plan, verification_results, context, llm):
    ## Implement your repair strategy here.

    return RepairResult(
        repaired_plan=new_plan,
        metadata={"strategy": "R1"},
    )
```

Your strategy receives the current raw itinerary, verification feedback, travel information and LLM adapter. It must return a proposed raw itinerary.

If your method needs to reject a proposed repair, override the `accept()` method.

After implementing your strategy, register it in `llm_modulo.py` and test it on one case before running larger experiments.

**Current status:** The shared framework and R0 are implemented and tested end-to-end. The shared verifier detects invalid itinerary structures, transport translation failures and verifier execution errors separately from genuine constraint violations, and is **language-aware** (it checks English itineraries against the English sandbox, fixing earlier false "unavailable transport" errors). Experiments run on **DeepSeek V3** by default (far cheaper than GPT-4.1) and logging is **cross-platform** (Windows long-path + nested-dir fixes). With both sandboxes installed the full test suite passes (277 tests, 0 failures, 0 errors). See `framework_r0.ipynb` for runnable proof cells and `train_test_split_r0.ipynb` for the split + R0 experiment.

R1, R2, R3, and R4 are all implemented and registered (R3P was merged into R3's ladder and removed). See `framework_r0.ipynb` for implementation details, testing results and remaining limitations.
---

# Original ChinaTravel Documentation

The original ChinaTravel README, including installation details, evaluation instructions, acknowledgements, licence and citation, is retained below.

> **Note for our project:** the original docs below state that the run/evaluation scripts default to Chinese. In **our** fork that default has been changed to English (`--lang en`); pass `--lang zh` only if you want the Chinese sandbox. Our group-specific instructions are in the **Quick Setup for Group Members** section above.

---

<center>
  <h1>[ICLR'26] ChinaTravel: An Open-Ended Travel Planning Benchmark with Compositional Constraint Validation for Language Agents</h1>
</center>

[English](README.md) | [简体中文](README.zh-CN.md)

ChinaTravel is a real-world travel-planning benchmark for language agents. It
combines structured sandbox data, natural-language requests, executable DSL
constraints, commonsense validation, and preference-based scoring.

[![Webpage](https://img.shields.io/badge/Webpage-Visit-blue)](https://www.lamda.nju.edu.cn/shaojj/chinatravel/)
[![Paper](https://img.shields.io/badge/Paper-View-red)](https://openreview.net/forum?id=0YRVlxY9BH)
[![Queries](https://img.shields.io/badge/Queries-HuggingFace-yellow)](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel)
[![Queries](https://img.shields.io/badge/Queries-ModelScope-blue)](https://modelscope.cn/datasets/Cbphcr/ChinaTravel)
[![Sandbox](https://img.shields.io/badge/Sandbox-HuggingFace-orange)](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel-Sandbox)
[![Sandbox](https://img.shields.io/badge/Sandbox-ModelScope-blue)](https://modelscope.cn/datasets/Cbphcr/ChinaTravel-Sandbox)
[![TPC@IJCAI2026](https://img.shields.io/badge/Competition-TPC%40IJCAI2026-green)](https://chinatravel-competition.github.io/IJCAI2026/)
[![TPC@IJCAI2025](https://img.shields.io/badge/Competition-TPC%40IJCAI2025-green)](https://chinatravel-competition.github.io/IJCAI2025/)
[![TPC@AIC2025](https://img.shields.io/badge/Competition-TPC%40AIC2025-green)](TPC@AIC2025/readme.md)

## 🏆 News

### TPC@IJCAI 2026

ChinaTravel was selected as the official benchmark for the Travel Planning
Challenge at IJCAI 2026. The challenge focused on agentic systems for practical,
constraint-rich travel planning. See the
[official competition website](https://chinatravel-competition.github.io/IJCAI2026/).

### TPC@IJCAI 2025

ChinaTravel was selected as the official benchmark for the Travel Planning
Challenge at IJCAI 2025. The challenge invited language agents to solve
real-world travel-planning tasks under complex constraints. See the
[official competition website](https://chinatravel-competition.github.io/IJCAI2025/).

### TPC@AIC 2025

ChinaTravel also supported the Travel Planning Challenge at AIC 2025. The
competition setup, metrics, submission format, and evaluation environment are
retained in the [competition archive](TPC@AIC2025/readme.md).

## 📝 Changelog

### 2026.08

The 2026.08 release is the maintained post-competition version of ChinaTravel.
It consolidates the benchmark, evaluator, bilingual environment, and data
tooling developed during and after TPC@IJCAI 2026:

- OpenAI-compatible model runtime supporting Chat Completions and the Responses
  API;
- explicit Chinese and English query/sandbox selection through `--lang zh` and
  `--lang en`;
- hardened evaluation for entity grounding, activity chronology, transport
  validation, meal counting, hard-logic execution, invalid-plan scoring,
  deterministic data loading, and cached evaluation;
- modular synthetic-query generation with a constraint catalog, controllable
  sampling, independent audit, and query-only release export;
- Chinese-to-English DSL/query translation with rule and LLM audit, selective
  repair, conservative re-audit, and human-adjudication workflows;
- reproducible export of canonicalized English sandbox data, synchronized query
  and sandbox releases on Hugging Face and ModelScope, and release checksums;
- repository-relative, Git-ignored `artifacts/` outputs for portable local
  workflows.

### 2025.09

- Published the champion solution of the TPC@IJCAI 2025 DSL track. We thank
  [@evergreenee](https://github.com/evergreenee) for the contribution.

### 2025.06

- Fixed commonsense-evaluation error collection.
- Fixed the pure-neural agent pipeline.
- Fixed Hugging Face dataset loading.
- Improved exception handling in syntax verification.

### 2025.05

- Updated logs for the latest version.
- Published the TPC evaluation code.

### 2025.04

- Added local query loading: a non-default `--splits NAME` value resolves to
  `chinatravel/evaluation/default_splits/NAME.txt`, whose lines identify the
  query files to load.
- Published a detailed constraint classification in the
  [evaluation documentation](chinatravel/symbol_verification/readme.md).
- Introduced the LLM-modulo baseline with a ground-truth symbolic verifier,
  based on *Robust Planning with Compound LLM Architectures: An LLM-Modulo
  Approach* and its
  [reference implementation](https://github.com/Atharva-Gundawar/LLM-Modulo-prompts).
- Added local inference support for Qwen3-8B and Qwen3-4B.

## 📦 Data Releases

| Resource | Hugging Face | ModelScope |
| --- | --- | --- |
| Query dataset | [LAMDA-NeSy/ChinaTravel](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel) | [Cbphcr/ChinaTravel](https://modelscope.cn/datasets/Cbphcr/ChinaTravel) |
| Bilingual sandbox | [LAMDA-NeSy/ChinaTravel-Sandbox](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel-Sandbox) | [Cbphcr/ChinaTravel-Sandbox](https://modelscope.cn/datasets/Cbphcr/ChinaTravel-Sandbox) |

The ModelScope repositories mirror the official Hugging Face query and sandbox
releases. Both query repositories provide the Phase 1 splits and the complete
2,000-query `TPC2026_phase2` config, including its 100-query `competition_test`
split.

### TPC@IJCAI 2026 Query Sets

- [Phase 1 competition test queries (1,000)](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel/viewer/test/human1000)
- [Phase 2 complete release (2,000)](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel/viewer/TPC2026_phase2/full)
- [Phase 2 official evaluation subset (100)](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel/viewer/TPC2026_phase2/competition_test)

The Phase 1 link contains the participant-facing query set. Evaluator-only
Oracle annotations are not part of that public split. The same public query
release is also available from the
[ModelScope mirror](https://modelscope.cn/datasets/Cbphcr/ChinaTravel).

## 🗂️ Repository Map

| Path | Purpose |
| --- | --- |
| `chinatravel/` | Core agents, bilingual sandbox, DSL, and evaluators |
| `agent_env/` | Structured tools, CLI/HTTP/MCP adapters, and split harness |
| `synthetic_query_generation/` | Synthetic query generation and independent audit |
| `scripts/` | Translation, repair, and fixed-sandbox export utilities |
| `tests/` | Regression tests for evaluator, language, DSL, and data tools |
| `run_exp.py`, `run_tpc.py` | Agent execution entrypoints |
| `eval_exp.py`, `eval_tpc.py` | Standard and TPC evaluation entrypoints |

## 🚀 Installation

Python 3.12 or newer is required by `pyproject.toml`.

With `uv`:

```bash
uv sync
source .venv/bin/activate
```

Or with Conda and pip:

```bash
conda create -n chinatravel python=3.12
conda activate chinatravel
pip install -r requirements.txt
```

Download the official bilingual sandbox from
[Hugging Face](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel-Sandbox)
or [ModelScope](https://modelscope.cn/datasets/Cbphcr/ChinaTravel-Sandbox), and
place it as:

```text
chinatravel/environment/database/       # Chinese sandbox
chinatravel/environment/database_en/    # English sandbox
```

> [!IMPORTANT]
> The `next` branch requires the current official sandbox release. It does
> not rewrite legacy English concept labels or POI aliases at runtime. Older
> `database_en` snapshots are unsupported and can produce different tool output
> or evaluation failures. Query, plan, and DSL entity names must match the
> installed sandbox exactly.

The requested language must exist locally. The standard run/evaluation scripts
default to Chinese for backward compatibility; pass `--lang en` explicitly for
English data.

## 🤖 Model Runtime

ChinaTravel accepts built-in aliases such as `deepseek`, `gpt-4o`, and
`glm4-plus`, or any model exposed through an OpenAI-compatible endpoint.

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://your-provider.example/v1"

# chat: OpenAI-compatible Chat Completions (default)
# responses: OpenAI Responses API
export CHINATRAVEL_OPENAI_WIRE_API="chat"

# Optional provider-specific token field.
export CHINATRAVEL_OPENAI_TOKEN_LIMIT_ARG="max_tokens"
```

Additional runtime variables include:

- `CHINATRAVEL_OPENAI_MODEL`: default model when `--llm` is omitted;
- `CHINATRAVEL_OPENAI_API_KEY`: key override before `OPENAI_API_KEY`;
- `CHINATRAVEL_OPENAI_BASE_URL`: base URL override before `OPENAI_BASE_URL`;
- `CHINATRAVEL_OPENAI_RAISE_ERRORS=1`: surface provider errors while debugging;
- `CHINATRAVEL_OPENAI_STRICT_TOOLS=1`: export strict OpenAI tool schemas.

Responses mode requires `openai>=1.66.0`. API keys must remain in environment
variables or ignored local configuration files.

## ▶️ Running Agents

Run an English or Chinese split:

```bash
python run_exp.py \
  --splits easy \
  --agent LLMNeSy \
  --llm provider/model-name \
  --lang en

python run_exp.py \
  --splits easy \
  --agent LLMNeSy \
  --llm provider/model-name \
  --lang zh
```

To expose oracle annotations to an algorithm that explicitly requires them:

```bash
python run_exp.py \
  --splits human \
  --agent LLM-modulo \
  --llm provider/model-name \
  --refine_steps 10 \
  --oracle_translation \
  --lang en
```

`--oracle_translation` exposes `hard_logic_py` and `hard_logic_nl`. Normal
participant-facing runs should omit it. Query files must use the current JSON
schema; when present, `hard_logic_py` must be a JSON list rather than a
string-encoded list.

Results are written under `results/<method>/`.

## 📊 Evaluation

Evaluate a generated result directory with the same language as the query and
sandbox data:

```bash
python eval_exp.py --splits human --method YOUR_METHOD --lang en
python eval_tpc.py --splits tpc_phase1 --method YOUR_METHOD --lang en
```

The TPC evaluator reports schema, commonsense, hard-constraint, FPR, and
preference metrics. Plans that fail required validity checks contribute zero to
the affected preference average; preference scores are not a bypass for an
invalid itinerary.

The hardened evaluator additionally enforces:

- database grounding for referenced entities and transports;
- chronological, non-overlapping activities and valid transport departure
  ordering;
- valid intercity transport placement and type-independent position handling;
- at most one hotel breakfast per day for the free-breakfast exception;
- exact entity names and canonical concept values from the installed sandbox;
- safe DSL execution and legacy apostrophe normalization.

For reproducible offline analysis of persisted R0/R1/R2/R3/R4 repair runs, see
[Repair analysis](scripts/REPAIR_ANALYSIS.md). This reads saved evidence without
rerunning generation, verification, or benchmark evaluation. R4 TEST analysis stays
separate from the R0–R3 TRAIN comparison tables.

## 🛠️ Agent Environment and Harness

`agent_env` exposes ChinaTravel through structured Python, CLI, HTTP, MCP, Chat
Completions tool-call, and Responses function-call interfaces.

```bash
python -m agent_env --lang en tools
python -m agent_env --lang en call attractions_keys '{"city":"Shanghai"}'
CHINATRAVEL_LANG=en python -m agent_env.mcp_stdio
```

For split-level harness execution:

```bash
cp agent_env/config.toml.example agent_env/config.toml
python agent_env/scripts/solve_script_with_harness.py
```

The tracked example defaults to English. The local `config.toml` is ignored
because it may contain provider credentials. See the
[Agent Environment guide](agent_env/README.md) for OpenCode, Codex, resume,
output, HTTP, and MCP details.

## 🧩 Synthetic Query Generation

The generator samples executable constraints only from already valid seed
plans, validates every candidate, validates the final combination again, and
writes an auditable manifest.

The examples below assume they are run from the repository root. Generated
files use the repository-relative, Git-ignored `artifacts/` directory; replace
it with any explicit output location when integrating the pipeline elsewhere.

```bash
python -m synthetic_query_generation seed-queries \
  --output-dir artifacts/synthetic/seed_queries \
  --num-records 100 \
  --lang en \
  --seed 2026

python -m synthetic_query_generation from-plans \
  --plans-dir results/seed_planner \
  --output-dir artifacts/synthetic/generated \
  --num-records 100 \
  --lang en \
  --seed 2026 \
  --copy-seed-plans

python -m synthetic_query_generation.audit \
  --dataset-dir artifacts/synthetic/generated \
  --expected-records 100 \
  --profile full \
  --lang en
```

Constraint families and individual template keys can be enabled, disabled, or
prioritized independently. See [Synthetic Query Generation](synthetic_query_generation/README.md).

## 🌐 Translation and Data Repair

The translation pipeline supports OpenAI-compatible Chat Completions APIs,
custom `base_url`, headers, model parameters, concurrency, and top-level
`extra_body` request fields. It combines deterministic checks with LLM review
and changes only records selected by the configured audit policy.

```bash
cp translation_api_config.example.json translation_api_config.json
export TRANSLATION_API_KEY="your-key"

python scripts/build_translation_assets.py
python scripts/audit_phase1_translations.py
python scripts/repair_phase1_translations.py
```

See [Translation and Audit Pipeline](scripts/TRANSLATION_PIPELINE.md).

For maintainers migrating a legacy English snapshot into the canonical release
format, the offline exporter can be run without modifying its source:

```bash
python scripts/export_fixed_sandbox.py artifacts/sandbox/ChinaTravel_sandbox_en_fixed \
  --archive artifacts/sandbox/ChinaTravel_sandbox_en_fixed.zip
```

Normal users should download the current Hugging Face or ModelScope release
instead. The archive produced by this maintenance tool contains a manifest,
change report, and checksums. See
[Fixed Sandbox Export](scripts/SANDBOX_EXPORT.md).

## ✅ Tests

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q chinatravel agent_env scripts synthetic_query_generation tests
```

The regression suite covers bilingual propagation, query resolution, evaluator
grounding and scoring, chronology, meal limits, performance caches, safe DSL
control flow, synthetic constraints, and translation repair.

## 📚 Documentation

- [Chinese README / 中文说明](README.zh-CN.md)
- [Environment](chinatravel/environment/readme.md)
- [Constraint verification](chinatravel/symbol_verification/readme.md)
- [Agent environment](agent_env/README.md)
- [Synthetic query generation](synthetic_query_generation/README.md)
- [Translation and audit](scripts/TRANSLATION_PIPELINE.md)
- [Fixed sandbox export](scripts/SANDBOX_EXPORT.md)
- [Post-competition release validation](docs/RELEASE_VALIDATION.md)
- [TPC@AIC 2025](TPC@AIC2025/readme.md)

## 🏆 Competition Archives

- [TPC@IJCAI 2026](https://chinatravel-competition.github.io/IJCAI2026/)
- [TPC@IJCAI 2025](https://chinatravel-competition.github.io/IJCAI2025/)

## 🙏 Acknowledgements

We thank [Stefan Schneider](https://github.com/stefanbschneider) and Team
fabiundstefan, including [Fabian Missbrenner](https://github.com/fabufab), for the
responsible disclosure and careful documentation of evaluator and scoring
issues. Their reports materially informed the chronology, transport, meal, and
validity fixes included in this release.

We also thank
[@450112489](https://github.com/450112489),
[@zihaocheng-buaa](https://github.com/zihaocheng-buaa),
[@277CPS](https://github.com/277CPS),
[@DuanchuWang](https://github.com/DuanchuWang),
[@evergreenee](https://github.com/evergreenee),
[@yishu031031](https://github.com/yishu031031), and
[@luck-lak](https://github.com/luck-lak) for actionable reports on data,
evaluation, prompts, setup, and documentation. We are additionally grateful to
[@ploract](https://huggingface.co/ploract) and
[@lucmek](https://huggingface.co/lucmek) for Hugging Face dataset corrections,
and to [Niels Rogge](https://github.com/NielsRogge) for encouraging the public
sandbox release on Hugging Face.

## 📄 License

The code and documentation in this repository are licensed under the
[MIT License](LICENSE). The official query and sandbox datasets are licensed
under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Third-party components retain their respective licenses.

## ✉️ Contact

For questions, contact [Jie-Jing Shao](mailto:shaojj@lamda.nju.edu.cn),
[Bo-Wen Zhang](mailto:221900200@smail.nju.edu.cn), or
[Xiao-Wen Yang](mailto:yangxw@lamda.nju.edu.cn).

## 📌 Citation

```bibtex
@inproceedings{shao2026chinatravel,
  title     = {ChinaTravel: An Open-Ended Travel Planning Benchmark with Compositional Constraint Validation for Language Agents},
  author    = {Jie-Jing Shao and Bo-Wen Zhang and Xiao-Wen Yang and Baizhi Chen and Siyu Han and Pang Jinghao and Wen-Da Wei and Guohao Cai and Zhenhua Dong and Lan-Zhe Guo and Yu-Feng Li},
  booktitle = {The Fourteenth International Conference on Learning Representations},
  year      = {2026},
  url       = {https://openreview.net/forum?id=0YRVlxY9BH}
}
```
