# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This is a fork of the **ChinaTravel** benchmark (ICLR'26), used as a **baseline** for a
DSA4213 group project on **verification-guided repair** in LLM travel planning. The project
keeps ChinaTravel's `LLM-modulo` planner and compares five repair strategies on top of it.

The upstream ChinaTravel code (agents, bilingual sandbox, DSL, evaluators, translation
pipeline, synthetic query generation) is kept largely unchanged. **The project's own work
lives in `chinatravel/agent/nesy_verifier/`.** See `framework_r0.ipynb` for the design
rationale, R0 test results, and known limitations, and the "Project Goal & Research Design"
section below for the full research plan.

## Project Goal & Research Design

### Research question

> **Can modelling constraint interdependencies improve the effectiveness *and* efficiency
> of verification-guided repair in LLM-based travel planning?**

The ChinaTravel `LLM-modulo` loop generates an itinerary, runs a symbolic verifier, tells
the LLM which constraints failed, and asks for a fix — repeating until the plan passes or a
repair budget is exhausted. **Every claim in this project is measured relative to the R0
baseline** (the vanilla whole-plan-regeneration loop).

### Hypotheses (all vs. R0)

- **H1 (effectiveness).** Giving the LLM a **constraint-interdependency matrix `M`** (which
  constraints tend to break which others) improves repair performance.
- **H2 (efficiency).** Long verify→repair chains hurt — context rot and growing token usage.
  A matrix that tells the model which constraints matter most should reduce repair rounds
  and tokens.
- **H3 (implicit).** Which *editing-scope policy* (R1 / R2 / R3) produces the most
  informative and best-performing matrix? Comparing the repair strategies is itself how we
  decide which matrix to trust.

### The constraint-interdependency matrix `M`

`M` is a **directional regression-risk matrix**: `M[i→j]` = the tendency that acting to
satisfy constraint-type *i* causes constraint-type *j* to **regress** (go from passing to
failing). This is exactly the "fixing one thing breaks another" signal that motivates the
project.

- **Raw signal already exists in code.** `shared_repair_loop.py::compare_constraint_results`
  emits per-step transitions `{fixed, newly_violated, still_failed, still_passed, unknown}`,
  logged for every attempt in `cache/<method>/problem_<id>_repair_history.json`. The
  **`newly_violated`** set (paired with what the step was trying to fix) is the estimator
  for `M[i→j]`.
- **Axes are constraint *types*, not per-query indices.** Personal constraints are arbitrary
  per-query DSL snippets (`hard_logic_py`), so a *universal* matrix must aggregate to
  constraint categories. Commonsense categories come from the ChinaTravel taxonomy
  (Cross-city transport, Inner-city transport, Attractions, Restaurants, Accommodation,
  Time, Space — see `chinatravel/symbol_verification/readme.md`). **Open point:**
  personal-constraint typing (a classification of `hard_logic_py` snippets) is not yet
  defined and is required before personal constraints can enter a universal `M`.
- **Signal quality differs by strategy.** R1 (targeted — only the failed slot changes) gives
  the **cleanest causal `i→j` signal**; R0 (whole-plan regeneration — everything can change)
  is the **noisiest**.

### Repair strategies

Each strategy is a `BaseRepairStrategy` subclass in `repair_strategies/`, implementing
`repair()` (propose a new raw itinerary) and optionally `accept()` (reject a candidate).
R0–R3 differ only in **which parts of the plan may change** and **when a proposal is
accepted**; R4 adds matrix guidance on top.

| Strategy | Mechanism | Known limitation |
|---|---|---|
| **R0** Whole-plan regeneration (baseline) | Verify → tell the LLM which constraints failed → ask for an **entirely regenerated** itinerary → repeat until pass or budget hit. | May needlessly rewrite parts that were already correct. |
| **R1** Targeted | Only **flagged** itinerary slots (fields a failed critic names) may be replaced; code **blocks** any edit to unflagged fields. The LLM is asked only for new values for the failed constraints' slots. | Freezing everything else can make a newly-surfaced constraint unfixable within the locked scope. |
| **R2** Protected (rollback) | Full rewrite allowed, but if a revision breaks **any critic that previously passed** (e.g. introduces a budget/timing violation), the proposal is **rejected and the last accepted itinerary is restored**; the LLM is told what it broke. | Rollback can stall progress if every rewrite trades one violation for another. |
| **R3** Adaptive scope | Repairs all failures of the current phase together (the shared loop's schedule: personal iterations first, at most 5, then commonsense iterations while errors remain, back to personal if one breaks a personal constraint; all 6 used unless the plan passes or nothing is left to fix). Starts as R1 (targeted: only the slots the failures localize to), then widens on a **fixed schedule** of 2 iterations per rung: slot (iters 1–2) → day (3–4) → whole plan (5+). Every iteration advances the ladder, commonsense included, so the rung follows the loop's step number; each commonsense iteration uses the current rung (so repeated commonsense iterations widen too) and lists the passing personal constraints as "must remain satisfied" (`protected_constraint_indices`). Bookings (hotel, outbound/return train or flight) stay frozen below plan scope unless a failing constraint is about one ("booking unlock", see the `r3.py` header): personal constraints first (hotel/room, intercity, quoted booking names, inner-city leg rules, and over-budget trips via their costliest bookings), then commonsense errors that point at a booking. Re-verifies **all** constraints after each attempt. | More complex control; widening scope reintroduces R0-style regression risk late in the loop; commonsense errors accumulate unseen during the personal phase. |
| **R4** Dependency-aware (matrix-guided) | Uses `M` to pick the **smallest** set of itinerary variables that fixes the violation while minimizing regression risk. | Depends on a good `M`; adds an optimization layer (see below). |

Implementation hooks: strategies are registered in a zero-argument factory map,
`repair_strategies.STRATEGY_FACTORIES` (in `repair_strategies/__init__.py`), and
`llm_modulo.py` dispatches via `create_repair_strategy(name)` — no more hardcoded
`if/elif`. The loop driver is `run_repair_loop` in `shared_repair_loop.py`; acceptance
(R2's rollback) belongs in `accept()`, while R3 keeps the default always-accept and does
its scope-widening inside `repair()` on a fixed iteration schedule (`rounds_per_rung`,
default 2).

### R4 — dependency-aware / matrix-guided repair

**Objective.** Rather than regenerate freely, R4 chooses a minimal, low-regression edit:

```
minimize   EditCost(ΔP) + RegressionRisk(ΔP; M)
subject to the failed constraint becoming satisfied
```

The LLM proposes replacements; a **symbolic/optimization layer** controls which parts may
change and verifies the objective constraints. Because restaurant / attraction / transport
choices are **discrete**, integer / constraint programming fits here — not gradient descent.

**Three scenarios for where `M` comes from** (how the matrix is given to the R4 agent):

1. **S1 — best single matrix.** Take the single best-performing matrix among those produced
   by R0–R3 and give it to the R4 agent. *(needs train/test split)*
2. **S2 — fused universal matrix.** Combine the R0–R3 matrices into one matrix representative
   of universal constraint interdependencies (e.g. a weighted function). *(needs train/test
   split)*
3. **S3 — per-query self-generated matrix.** For each query the agent builds its own matrix,
   then re-runs the repair using it. *(per-query; no train split — see evaluation below)*

#### Evaluation of Scenario 3 (requested)

S3 is the odd one out and should be treated carefully:

- **It tests a different hypothesis.** S3 measures *instance-level* dependency exploitation,
  not the *universal* interdependency claim (H1) that motivates the project. It answers a
  different question than S1/S2.
- **It likely *increases* compute, opposing H2.** A per-query discovery pass plus an
  exploitation pass is more tokens/rounds per query, not fewer. It only wins if the second
  pass converges enough faster to offset the first — so it must be reported as **net** cost
  at a **fixed compute/token budget** versus R0, not as a raw win.
- **Estimation is weak.** A single query exposes only a handful of constraints and one repair
  trajectory, so its matrix is near-binary/sparse ("these two conflicted once") rather than a
  probabilistic estimate — little to generalize from.
- **Confound.** Extra passes mean more repair attempts, so any improvement may come from more
  compute rather than from the matrix itself.
- **Recommendation.** Treat S3 as a separate **online/adaptive ablation**, not part of the
  universal-matrix comparison. If kept: fix the total budget, report net rounds/tokens, and
  **warm-start** the per-query matrix from the S2 universal matrix instead of estimating from
  n=1. Consider dropping it if the core claim is universal interdependency.

### Splits & evaluation protocol

- **R0–R3 repair-method comparison:** run on the **whole dataset (no splits)**. This yields
  each method's raw performance *and* each method's matrix.
- **R4 S1/S2:** use a **train split** to build/select `M`, then evaluate the matrix-guided
  agent on a **held-out test split**. R0 is reported on **both** splits for reference.
- **R4 S3:** per-query, so no training split is involved.

### Metrics (efficiency-focused, all reported relative to R0)

| Metric | Meaning | Source in saved result |
|---|---|---|
| Final pass rate | Fraction of plans that satisfy all constraints at the end of repair | verifier `passed` / `error_info` |
| Step-5 pass rate | The same, as of the end of step 5, i.e. before the last round; shows what step 6 gained or broke | per query in `phase_outcomes.csv` (`step5_*`, plus `cs_*` for what the commonsense rounds did together: `cs_attempts` rounds, first round's step/scope, errors before the first vs after the last); per strategy in `pass_rates.csv` (both written by `scripts/build_repair_summary.py`, which holds all of this code) |
| Repair rounds to convergence | Steps until pass, or hitting `--refine_steps` | length of `history` in the repair-history log |
| Token usage | LLM input/output tokens consumed | `input_token_count`, `output_token_count`, `input_token_maxx` |
| Cache hits | Requests a strategy repeated exactly within a query, answered by the shared repeat-request cache instead of the model (a sign the strategy got stuck); tokens saved vs. tokens spent | per query in `llm_cache_hits.csv` (`llm_cache_hits`, `rounds_with_cache_hit`, `cache_hit_round_rate`, `first_cache_hit_step`, `tokens_spent`, `tokens_saved`, `tokens_without_cache`), written by `scripts/build_repair_summary.py`; per attempt in `repair_metadata.llm_cache_*` |
| Wall-clock / inference time | Total and LLM-only time | `elapsed_time(sec)`, `llm_inference_time(sec)` |

(These fields are populated in `llm_modulo.py`; per-step transitions and metadata are in
`problem_<id>_repair_history.json`.)

### Novelty

Prior LLM-Modulo work only implemented **R0** (whole-plan regeneration). The editing-scope
policies (R1–R3) and the dependency-aware, matrix-guided repair (R4) are the project's
contribution — repair studies the published LLM-Modulo line has not done.

### Current implementation status

| Strategy | Status |
|---|---|
| R0 | Implemented & tested end-to-end |
| R3 | Implemented & registered; unit-tested offline (ladder, localization, slot-freeze merge, contract-conforming metadata, and an end-to-end `run_repair_loop` record-validation test in `tests/test_r3_adaptive_repair.py`) |
| R1 | Implemented & registered (`r1.py`, tests in `tests/test_r1*.py`). Like every strategy, R1 uses the full budget unless the plan passes: unchanged-plan attempts are recorded and use a round (the loop no longer stops R1 on a no-op) |
| R2 | Implemented & registered (`r2.py`, tests in `tests/test_r2_rollback_repair.py`). Subclasses R0 (same prompt/feedback via `R0WholePlanRepair._build_feedback`); `accept()` rejects any candidate with a personal True→False regression, so the loop keeps the last accepted plan. Broken constraint indices are remembered per query (`_broken_constraints`) and appended to every later prompt. UNKNOWN (`None`) results and new commonsense errors do not trigger rollback. Unlike R0, an unparsable reply or a candidate with no activities / the wrong day count does not raise: R2 keeps the current plan with `failure_reason: "no_valid_repair_candidate"` (a robustness difference to keep in mind when comparing R2 with R0). R2 has no skip rule of its own any more: an exact repeat request (seen in `experiments/pilot5-r2-v1`, where R2 echoed the plan at temperature 0) is served by the shared loop's per-query repeat-request cache, which applies to every strategy alike |
| R4 | Implemented & registered (`r4.py`); needs `CHINATRAVEL_R4_MATRIX`, and `run_experiments.py` only allows it on training splits with ≤5 explicit `--index` queries |
| R3P | Removed — the shared loop's phase schedule (then 5+1) made it identical to R3. Old results stay in `experiments/r3p_deepseek-chat_pilot5/` |

## Setup

Python **3.12** is required (`.python-version` pins 3.12). Two supported flows:

```bash
# uv (preferred — pyproject.toml is the source of truth)
uv sync && source .venv/bin/activate

# or pip
pip install -r requirements.txt
```

The benchmark needs the sandbox database, which is **not** in git. Download it with:

```bash
python scripts/setup_project.py   # fetches + extracts into chinatravel/environment/database/
```

Configure the LLM endpoint by copying `.env.example` to `.env` and filling in the
OpenRouter key (`CHINATRAVEL_OPENAI_API_KEY`, `CHINATRAVEL_OPENAI_BASE_URL`,
`CHINATRAVEL_OPENAI_MODEL`). On Windows, activate with `.venv\Scripts\activate`. Never
commit `.env`.

## Common commands

```bash
# Run the repair framework on one case (the project's main entrypoint):
python run_exp.py --agent LLM-modulo --repair_strategy R0 \
  --llm openai/gpt-4.1 --splits medium --index e20241028160845920703 \
  --refine_steps 2 --oracle_translation --lang zh

# Full test suite (unittest, not pytest — despite .pytest_cache existing):
python -m unittest discover -s tests -p 'test_*.py' -v

# A single test module / case:
python -m unittest tests.test_shared_verifier_reliability -v
python -m unittest tests.test_shared_verifier_reliability.ClassName.test_method -v

# Byte-compile check across the main packages:
python -m compileall -q chinatravel agent_env scripts synthetic_query_generation tests

# Evaluate a results directory (same --lang as the run):
python eval_exp.py --splits human --method YOUR_METHOD --lang en
python eval_tpc.py --splits tpc_phase1 --method YOUR_METHOD --lang en
```

Key `run_exp.py` flags: `--repair_strategy {R0..R4}` selects the project's shared repair
loop (omit it to use upstream ChinaTravel's original loop); `--oracle_translation` exposes
`hard_logic_py`/`hard_logic_nl` and is **required** for `LLM-modulo`; `--refine_steps` is
the repair-attempt budget; `--lang {zh,en}` picks the sandbox/query language (defaults to
`zh`). Results are written to `results/<method>_<strategy>/`; per-query prompts and repair
histories go to `cache/<method>_<strategy>/`.

## Repair framework architecture (the part the project changes)

All project-specific code is under `chinatravel/agent/nesy_verifier/`. The flow when a
`--repair_strategy` is set:

1. **`llm_modulo.py`** (`LLMModuloAgent.solve`) generates the initial itinerary, then — if
   `repair_strategy_name` is set — instantiates the strategy via
   `create_repair_strategy(name)` and calls `run_repair_loop` instead of the legacy
   ChinaTravel loop. **New strategies are registered by adding a zero-argument factory to
   `STRATEGY_FACTORIES` in `repair_strategies/__init__.py`** (lazy import inside the
   factory) — no edit to `llm_modulo.py` is needed. It returns the final plan with
   verification results, token/time stats, and writes `problem_<id>_repair_history.json`.

2. **`shared_repair_loop.py`** (`run_repair_loop`) is the strategy-agnostic driver. It
   verifies the current plan, asks the strategy to `repair()`, verifies the candidate, asks
   the strategy to `accept()`, and records every attempt (including rejected ones) with a
   before/after constraint `transitions` diff. The *accepted* plan and candidate are kept
   separate — comparisons are always against the current accepted plan.

3. **`shared_verifier.py`** (`verify_plan`) is the shared verifier. Its defining design
   choice: it keeps **genuine constraint violations** separate from **technical failures**.
   `error_info` (what repair prompts try to fix) contains only real commonsense + personal
   violations, while verifier crashes, transport-translation failures, DSL evaluation
   errors, and structural/schema problems live on their own channels. Any technical error
   forces `passed=False`, and personal-constraint results are tri-state: `True`/`False`/
   `None` (`None` = could not be evaluated, never conflated with a real pass/fail).

4. **`repair_strategies/base.py`** defines the interface every strategy implements:
   `BaseRepairStrategy.repair(problem, raw_plan, verification_results, context, llm) ->
   RepairResult` and an optional `accept(current_verification, candidate_verification) ->
   bool` (default: always accept, as R0 does). **`repair_strategies/r0.py`** is the worked
   example to copy from.

### Implementing a new strategy (R1–R4)

Add `repair_strategies/rN.py` subclassing `BaseRepairStrategy`; have `repair()` return a
`RepairResult(repaired_plan=..., metadata={...})`. Override `accept()` if the strategy
should reject some proposals. Then register it by adding a zero-argument factory to
`STRATEGY_FACTORIES` in `repair_strategies/__init__.py` (see the `_r0` / `_r1` / `_r3` entries).
Test on one case via `run_exp.py` before larger runs. **R0 and R3 are the worked examples
to copy from** (`r0.py` for the simple whole-plan case, `r3.py` for stateful scope control).

**Standardized repair output contract.** `metadata` is no longer free-form: the loop runs
it through `normalize_repair_intent_metadata` and builds a validated `RepairAttemptRecord`
(see `chinatravel/evaluation/REPAIR_ATTEMPTS.md` and `repair_attempt.py`). The record is
**enforced at runtime** — non-conforming metadata raises. Canonical *intent* keys a strategy
may emit: `strategy` (→ `repair_strategy`), `target_constraint_indices` (unique, **1-based**
`hard_logic_py` indices), `editable_scope` (`"slot"`/`"day"`/`"plan"`), `scope_level`
(int `1`/`2`/`3`, must agree with `editable_scope` via `{1:slot, 2:day, 3:plan}`),
`escalation_reason`, `target_provenance`, `protected_constraint_indices`, `decision_reason`.
Everything else stays in `repair_metadata` as debug payload and **must not reuse a canonical
field name** (`step`, `scope`, etc. are stripped/rejected). Do **not** emit
`concurrent_failed_constraint_indices` / `concurrent_commonsense_failure_count` — the loop
derives those authoritatively. R3's metadata block in `r3.py` is the reference for a
scope-based strategy.

Important: strategies operate on the **raw** (pre-translation) itinerary; the shared
verifier translates a copy internally. Iterations, per-attempt wall time
(`repair_time_seconds`), and token deltas are measured by the loop — a strategy does not
compute them. `metadata["llm_inference_time"]` (a debug key) is still summed into the
agent's reported inference time, so set it if you call the LLM.

## Upstream ChinaTravel layout (mostly unchanged)

- `chinatravel/agent/` — planners (`LLMNeSy`, `RuleNeSy`, `LLM-modulo`, `ReAct`, `TPCAgent`).
  `load_model.py` builds the runtime and output dirs (`create_agent_runtime`); it appends
  `_<strategy>` to the method name when a repair strategy is set.
- `chinatravel/environment/` — the sandbox `WorldEnv` and domain tool APIs; `database/`
  (zh) and `database_en/` (en) hold the downloaded data and are git-ignored.
- `chinatravel/symbol_verification/` — the DSL executor (`dsl.py`), constraint concept
  functions (`concept_func.py`), and hard-constraint handling. Personal constraints are
  Python DSL snippets in `hard_logic_py`, executed sandboxed with a restricted builtin set.
- `chinatravel/evaluation/` — the hardened evaluator (schema, commonsense, hard-constraint,
  FPR, preference metrics) used by `eval_exp.py` / `eval_tpc.py`. Non-default `--splits
  NAME` resolves to `chinatravel/evaluation/default_splits/NAME.txt`.
- `agent_env/` — standalone CLI/HTTP/MCP wrapper over the sandbox (`python -m agent_env …`),
  independent of the repair framework.
- `scripts/`, `synthetic_query_generation/` — translation/data tooling and synthetic query
  generation; relevant only for dataset maintenance, not the repair experiments.

## Gotchas

- Tests use **`unittest`**, not pytest, despite the `.pytest_cache/` directory.
- The marker string `"Raise error in symoblic commonsense feedback"` in `shared_verifier.py`
  contains an intentional upstream typo ("symoblic") that must match verbatim — do not
  "fix" it.
- `--lang` must match locally installed sandbox data; the English sandbox must be the
  current official release (legacy `database_en` snapshots are unsupported).
- The untracked `data/` directory holds NYC-style exploratory CSV/parquet datasets separate
  from the ChinaTravel sandbox.
