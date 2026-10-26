# HANDOVER — DSA4213 Verification-Guided Travel-Planner Repair

> Self-contained brief for an AI assistant who **cannot** access this repo. Everything you
> need to continue the project is here. Where a claim is uncertain or an existing doc is
> stale, it is flagged explicitly. Last verified against `main` @ commit `3b47d9a`
> (Merge PR #21 "eval-matrix-infra"), working tree clean.

---

## 1. Project in one paragraph + research question

This is a fork of the **ChinaTravel** benchmark (an LLM travel-planning benchmark with a
symbolic constraint verifier). The group project holds the **verifier constant** and ablates
only the **repair step**: when a generated itinerary fails a constraint, how should the planner
fix it? We compare repair strategies R0–R4.

**Research question:** *Can modelling constraint interdependencies make repair more effective —
i.e. fix the failing constraint without cascading new violations into constraints that were
already passing?* The flagship deliverable is an **interaction / regression matrix**
`M[i][j] = P(constraint family j breaks when repairing family i)`. R4 (planned) is the
matrix-guided strategy that should use `M` to avoid cascades.

### Strategy table

| Strategy | What it does | Status |
|---|---|---|
| **R0** | Whole-plan regeneration (baseline). Feeds verifier errors into the original ChinaTravel `BACK_PROMPT`, asks the LLM to regenerate the entire itinerary. | **Done, registered** |
| **R1** | Targeted / slot repair. Edits only the activity slot(s) tied to a failing constraint; freezes everything else. | **Done, registered** |
| **R2** | Protected repair. Whole-plan rewrite, but **records** which previously-passing constraints it broke (regressions). *(Code does not hard-reject/rollback in current form — see §6.)* | **Done, registered** |
| **R3** | Adaptive-scope repair. "R1 that relaxes into R0": starts at slot scope, widens slot→day→plan on a fixed schedule (2 iters per rung). At tightest = R1, widest = R0. | **Done, registered** |
| **R3P** | Phased variant of R3: repairs *personal* constraints only for up to 5 iters, then a forced commonsense-repair iteration (protecting passing personal constraints), recovering if it breaks one. Same R3 class with `phased=True`. | **Done, registered** |
| **R4** | Constraint-interdependency-guided repair. Should consume the learned matrix `M` to choose repair order/scope that minimises cascades. | **NOT implemented, NOT registered** |

**Control:** all strategies share ONE verifier (`shared_verifier.py::verify_plan`) that
re-checks the **whole itinerary against all constraints after every attempt**. Strategies differ
only in *what may change*, never in *how the plan is checked*. This is what makes the comparison
apples-to-apples.

---

## 2. Current status — DONE vs TODO (based on code + git log, not docs)

**DONE (verified in code):**
- Shared framework: `shared_verifier.py`, `shared_repair_loop.py` (the scheduler lives
  *inside* `run_repair_loop`: personal-repair iterations first (≤5), then commonsense iterations
  while errors remain, back to personal if one breaks a personal constraint; total budget capped
  at 6 and always used unless the plan passes or nothing is left to fix), strategy factory registration.
- **R0, R1, R2, R3, R3P all implemented AND registered** in
  `repair_strategies/__init__.py` (`STRATEGY_FACTORIES = {R0, R1, R2, R3, R3P}`). All five are
  selectable and executable via `run_experiments.py --strategy ...`.
- Language-aware verifier fix (English itineraries checked against English sandbox — removed
  false "unavailable transport" errors). Windows long-path / nested-dir logging fixes.
- Evaluation + matrix pipeline: `repair_attempt.py`, `repair_metrics.py`, `regression_matrix.py`,
  `constraint_families.py`, `edit_footprint.py`, `repair_comparison.py`, `train_test_split.py`
  plus the four offline scripts. End-to-end flow works.
- Splits generated and committed: `pilot5`, `subset_train/test`, `combined_train/test`,
  `medium_train/test` + `*_origin.json` manifests.
- Committed pilot5 evidence for R0, R2, R3, R3P (see §5).
- Test suite green: **277 tests, 0 failures, 0 errors** (verified this session).

**TODO:**
- **R4 (matrix-guided)** — the core research contribution. Not written yet. Needs the learned
  matrix `M` as input.
- **Build the matrix `M`** from R0–R3 **train** trajectories (`subset_train`) via
  `build_regression_matrix.py`. Pipeline exists; the matrices for the real learning runs still
  need to be produced/collected.
- **Full experiment runs on `subset_test`** for R0–R3 (individual results) and R4 on
  `subset_test` only (held-out hypothesis test). The current committed results are the 5-query
  `pilot5` smoke runs, not the subset runs.
- **Individual per-strategy analyses / write-ups.**

> ✅ **Current facts (README/CONTRIBUTIONS/notebooks updated to match):** R0, R1, R2, R3, R3P
> are all implemented and registered (`STRATEGY_FACTORIES`); only **R4** remains. The test suite
> has **277 tests** (0 failures, 0 errors). Subset sizes are `subset_train`=60
> (20 easy / 20 medium / 20 human) and `subset_test`=30 (10 / 10 / 10), balanced equally by
> difficulty, with `pilot5` (5) a subset of `subset_train`; `combined_train`=422 /
> `combined_test`=182, `medium_train`=105 / `medium_test`=45. If any doc still cites "221 tests"
> or "R2/R4 not registered", trust the code and the split files over that prose.

---

## 3. Repo map (key files, one line each)

**Repair framework — `chinatravel/agent/nesy_verifier/`**
| File | Purpose |
|---|---|
| `shared_verifier.py` | `verify_plan()`: structure check + commonsense + personal DSL constraints. Returns tri-state `personal_constraints` (True/False/None), `error_info` (genuine violations only), and separate technical channels (`verifier_errors`, `translation_errors`, `schema_errors`). Any technical error forces `passed=False`. |
| `shared_repair_loop.py` | `run_repair_loop()`: the personal-first / repeating-commonsense scheduler. verify → `strategy.repair()` → verify candidate → `strategy.accept()` → record a `RepairAttemptRecord` per attempt. One strategy instance for the whole loop (strategies may hold state). `max_steps` capped at 6; rejected attempts still consume budget. Sets `context["repair_phase"]` = `"personal"` or `"commonsense"`. |
| `llm_modulo.py` | Main LLM-modulo agent; `solve()` builds initial plan + context, selects repair strategy, drives the loop. Contains the Windows path sanitisation fixes. |
| `initial_state.py` | Builds the initial repair state. |
| `repair_strategies/base.py` | `BaseRepairStrategy` (abstract `repair()`, default `accept()`=True) + `RepairResult(repaired_plan, metadata)` dataclass. **Read this first to implement R4.** |
| `repair_strategies/__init__.py` | `STRATEGY_FACTORIES` registry + `create_repair_strategy(name)`. Add R4 here. |
| `repair_strategies/r0.py` | R0 whole-plan regeneration. Simplest reference impl. |
| `repair_strategies/r1.py` | R1 slot-targeted repair (slot discovery, single-slot replacement, type preservation). |
| `repair_strategies/r2.py` | R2 protected whole-plan repair; tracks protected (passing) indices + regressions. |
| `repair_strategies/r3.py` | R3 + R3P (ladder slot→day→plan; `phased=True` = R3P). Richest example; emits the full canonical repair-intent metadata contract. |
| `prompts/llm_modulo.py` | `BACK_PROMPT` / `INITIAL_PROMPT` + prompt rules (inner-city transport nested in `transports`, allowed activity types, required `start_time`/`end_time`). |
| `verifier/commonsense_constraint_nl.py` | `collect_commonsense_constraints_error()`; **language-aware** (`_infer_lang`/`_set_lang`) — the fix that made English runs honest. |

**Evaluation + matrix — `chinatravel/evaluation/`**
| File | Purpose |
|---|---|
| `repair_attempt.py` | `RepairAttemptRecord` data model + `normalize_repair_intent_metadata` + `failed_constraint_indices`. The per-attempt log schema. |
| `repair_metrics.py` | Repair success / efficiency metrics. |
| `repair_comparison.py` | Paired before/after repair comparison. |
| `regression_matrix.py` | `build_regression_matrix()` — turns attempt records into the per-family regression matrix (the `M` builder). |
| `constraint_families.py` | `CONSTRAINT_FAMILIES` (the 9 families, below) + `classify_constraint()`. |
| `edit_footprint.py` | `compare_edit_footprint()` — how much a repair changed. |
| `train_test_split.py` | `load_manifest`/`filter_attempts` — split attempts by train/test partition (leakage control). |
| `export_final_plans.py` | Export final plans from a run. |
| `*.md` (REPAIR_*, REGRESSION_MATRIX, CONSTRAINT_FAMILIES) | Contracts/specs for each piece. `REPAIR_COMPARISON.md` is the evidence contract. |

The 9 constraint families: `trip_specification, party_resources, monetary_budget,
accommodation, dining, attraction, transport_mode, travel_extent, schedule_order`.

**Scripts — `scripts/`**
| File | Purpose |
|---|---|
| `setup_project.py` | Downloads both sandboxes from Hugging Face (`database/` zh, `database_en/` en). Run once after `pip install`. |
| `build_regression_matrix.py` | Build regression-matrix CSVs from `attempts.jsonl` (or a history JSON). Supports `--repair-strategy`, `--split-manifest`+`--partition` for leakage-free train/test slicing. |
| `build_repair_summary.py` | Per-run `summaries.csv`. |
| `evaluate_repair_run.py` | Offline benchmark eval of a run dir (schema/commonsense/logical CSVs). |
| `build_train_test_split.py` | Generate a train/test split config. |

**Runners (repo root)**
| File | Purpose |
|---|---|
| `run_experiments.py` | **Canonical** repair-strategy study runner (DeepSeek, registered strategies). Writes a run dir with `queries/`, `attempts.jsonl`, `run_manifest.json`. Supports `--resume`, `--retry-failed`. |
| `run_exp.py` | General ChinaTravel launcher (other agents/baselines; has `--repair_strategy R0..R4`). Not the study runner. |
| `run_tpc.py`, `eval_exp.py`, `eval_tpc.py`, `eval_with_oracle.py` | Original ChinaTravel run/eval entrypoints. |
| `run_experiment.py` | **Removed** (historical paired runner; replaced by `run_experiments.py`). |

**Notebooks / docs**
- `framework_r0.ipynb` — explains the R0 framework + tests, runnable proof cells.
- `train_test_split_r0.ipynb` — the deterministic split + how it wires into the runner.
- `docs/PRD_R3_adaptive_repair.md` — the R3 design spec (ladder, scope rungs, matrix-component logging). Good model for an R4 PRD.
- `experiments/Commands_to_test_queries.md` — the 4-step experiment workflow + which split each strategy runs on.
- `CLAUDE.md` — long-form internal project notes (big; lower priority to upload).

---

## 4. End-to-end flow: run a strategy → attempts.jsonl → metrics/matrix

```
run_experiments.py (one strategy, one split)
      │   per query: build initial plan → run_repair_loop → one RepairAttemptRecord per step
      ▼
experiments/<run-id>/
   ├── run_manifest.json   (model, split, max_steps, git commit, sampling args — the fairness record)
   ├── attempts.jsonl      (one JSON repair-attempt record per line)  ◄── matrix/metrics input
   └── queries/<uid-hash>/ (per-query final plan + initial_state.json + reference/query.json)
      │
      ├─► scripts/evaluate_repair_run.py  --run-dir <run>        → benchmark_eval/*.csv
      ├─► scripts/build_repair_summary.py --input <run>          → summaries.csv
      └─► scripts/build_regression_matrix.py
             --input <run>/attempts.jsonl
             --output-dir <run>/regression_matrix
             --repair-strategy <STRATEGY>                        → regression matrix CSVs
```

`attempts.jsonl` is the single source of truth for both metrics and the matrix `M`. Each record
carries `before_personal_constraints`, `after_personal_constraints`, and the transition sets
`{fixed, newly_violated, still_failed, still_passed, unknown}` — `newly_violated` is the
cascade signal `M` is built from.

---

## 5. Data / splits / experiments

**Splits** (`chinatravel/evaluation/default_splits/*.txt`, one UID per line):

| Split | Size | Role |
|---|---|---|
| `pilot5` | 5 (2 easy / 1 medium / 2 human) | Shared smoke/comparison set everyone runs first. **Subset of `subset_train`.** |
| `subset_train` | 60 (20 easy / 20 medium / 20 human) | Learn the matrix `M` (R0–R3 train trajectories). |
| `subset_test` | 30 (10 easy / 10 medium / 10 human) | **Main comparison** + held-out R4 test. No leakage from train. |
| `combined_train/test` | 422 / 182 | Full stratified 70/30 across easy+medium+human. |
| `medium_train/test` | 105 / 45 | Medium-only split. |
| base: `easy`/`medium`/`human` | 300 / 149 / 154 | Upstream difficulty tiers. |

`chinatravel/evaluation/splits/*_origin.json` map each UID in a stratified split back to its
base Hugging Face split (easy/medium/human) so the loader fetches each query from the right
place and results can be sliced by difficulty.

**Experiments folder** (`experiments/`, git-tracked):
- Newer runs (`run_experiments.py` output) = a `<run-id>/` dir with `attempts.jsonl` +
  `run_manifest.json` + `queries/`. Committed example: `experiments/pilot5-r2/`.
- Older flat style = `<strategy>_<model>_<split>/<uid>.json` final plans. Committed:
  `r0_deepseek-chat_pilot5/`, `r3_deepseek-chat_pilot5/`, `r3p_deepseek-chat_pilot5/`
  (5 queries each). `_archive_gpt4.1/` = superseded GPT-4.1 samples (predate the language fix).
- **What exists today = pilot5 smoke runs only** (R0, R2, R3, R3P). The `subset_train`/
  `subset_test` production runs that the comparison and matrix need are NOT yet committed.

`.gitignore`: `results/` and `cache/` are ignored; `experiments/` IS tracked. Final plans land
in `results/`, repair logs in `cache/`.

---

## 6. Conventions & gotchas (read before changing anything)

- **Fairness invariant:** keep **DeepSeek V3 (`deepseek/deepseek-chat`) + `--max-steps 6` (≤5 personal + commonsense rounds)
  + `--lang en`** identical across all strategies. Any difference in results must be attributable
  to the repair method, not the setup. The committed pilot5-r2 manifest also shows
  `temperature=0, top_p≈0` (greedy) — keep sampling settings fixed too. `run_manifest.json`
  records the git commit + sampling args per run so fairness is auditable.
- **Train vs test (leakage):** develop/tune on `subset_train`; build `M` from R0–R3 **train**
  trajectories; test R4 on held-out `subset_test` only. Use
  `--split-manifest ... --partition train|test` in `build_regression_matrix.py` to slice
  cleanly. "Main comparisons can only be made on `subset_test`."
- **R0 baseline vs legacy baseline:** `--strategy R0` (shared loop + shared verifier) is the
  ablation baseline. Legacy ChinaTravel (no repair strategy, original verifier) is NOT the
  comparison baseline.
- **`pilot5` is the shared 5-query set** — run every new strategy on it first for a quick
  apples-to-apples check before scaling.
- **Language-aware verifier:** English itineraries are now checked against `database_en`
  (`_infer_lang`/`_set_lang` in `commonsense_constraint_nl.py`). Before this fix, English runs
  produced false "unavailable transport" errors and inflated error counts (that's why the
  `_archive_gpt4.1` numbers are not comparable).
- **Windows fixes:** long-path `\\?\` prefix + model-name sanitisation in log dirs; `Logger`
  creates parent dirs. No-ops on macOS/Linux. On Windows set `$env:PYTHONUTF8="1"` or offline
  eval fails to read saved JSON.
- **"full pass rate 0" on R0 pilot5 is expected, not a bug:** a plan only "fully passes" when
  ALL personal + commonsense checks pass AND no technical error; the 5 pilot queries are hard
  (human/medium) and DeepSeek within a budget-5 repair loop often still has residual
  violations. The research signal is the *transitions* (fixed vs newly_violated), not the raw
  full-pass count. Judge strategies on cascade/repair metrics, not full-pass alone.
- **R2 caveat:** the PRD describes R2 as reject + rollback on regression, but the current `r2.py`
  **records** regressions on a whole-plan rewrite and the base `accept()` default is True. If R2
  is meant to hard-reject, verify/implement its `accept()` override before trusting R2 results.
- **Stray artifacts:** an empty file named `python` sits at repo root (harmless; likely a
  misdirected shell redirect). Safe to ignore/delete.
- **Dependencies:** Python 3.12 in `.venv`; `requirements.txt` pins `openai` upper bound
  (httpx compat), `pyarrow==19.0.1`, `python-dotenv`. `.env` holds the OpenRouter key
  (`CHINATRAVEL_OPENAI_API_KEY`, `CHINATRAVEL_OPENAI_BASE_URL=https://openrouter.ai/api/v1`);
  never commit it.

---

## 7. How to run things (real syntax)

**(a) Setup**
```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python scripts/setup_project.py    # downloads both sandboxes (database/, database_en/)
cp .env.example .env               # then paste the OpenRouter key into .env
set -a; source .env; set +a        # macOS/Linux: load env vars
```

**(b) Run a strategy on a split** (`--strategy` ∈ R0,R1,R2,R3,R3P)
```bash
python run_experiments.py \
  --strategy R3 --splits pilot5 \
  --llm deepseek/deepseek-chat --lang en \
  --max-steps 6 \
  --output-dir experiments --run-id pilot5-r3
# resume a partial run: add --resume (and --retry-failed to retry failures)
```
Other `run_experiments.py` flags: `--index UID [UID ...]`, `--temperature`, `--top-p`,
`--seed`, `--oracle-translation`, `--split-manifest`, `--partition {train,test}`,
`--skip-unavailable`.

**(c) Produce eval / summaries / matrix**
```bash
python scripts/evaluate_repair_run.py  --run-dir experiments/pilot5-r3
python scripts/build_repair_summary.py --input   experiments/pilot5-r3
python scripts/build_regression_matrix.py \
  --input experiments/pilot5-r3/attempts.jsonl \
  --output-dir experiments/pilot5-r3/regression_matrix \
  --repair-strategy R3
# leakage-free matrix from train partition only:
#   ... --split-manifest <manifest.json> --partition train
```

**(d) Tests**
```bash
python -m unittest discover -s tests -p "test_*.py"
# verified this session: Ran 277 tests — OK (0 failures, 0 errors)
```

---

## 8. What the next AI should probably help with

1. **Design + implement R4 (`repair_strategies/r4.py`)** following `base.py` and the R3 pattern;
   register it in `repair_strategies/__init__.py` (`STRATEGY_FACTORIES["R4"] = _r4`). R4 reads
   the learned matrix `M` to order/scope repairs so fixing constraint family *i* avoids
   cascading into family *j*. Mirror the R3 PRD to write an R4 PRD first.
2. **Produce the learned matrix `M`:** run R0–R3 on `subset_train`, then
   `build_regression_matrix.py --partition train` per strategy; decide the fusion scheme
   (per-strategy matrices vs one fused universal matrix — see `Commands_to_test_queries.md`
   "Scenario 1 / Scenario 2").
3. **Run the individual studies:** R0–R3 + R4 on `subset_test` (held-out), fixed DeepSeek/budget/en
   settings; collect metrics and the cascade (`newly_violated`) analysis.
4. **Write-up + individual strategy reports;** describe recorded cascading violations
   and matrix-guidance evidence within each run.
5. (Done) Doc drift in README/CONTRIBUTIONS/notebooks ("R2/R4 not registered", "221 tests",
   subset "69/31") has been corrected to R0–R3P registered / 277 tests / 60(20·20·20)·30(10·10·10).
   Re-check only if the code moves again.
6. **Confirm R2's intended accept/rollback semantics** before trusting R2 numbers (see §6).

---

## 9. Files the user should UPLOAD to the next AI (max context, small footprint)

The next AI can't read the repo, so prioritise these (each is self-describing):

1. **`HANDOVER.md`** (this file) — the map + status + commands.
2. **`chinatravel/agent/nesy_verifier/repair_strategies/base.py`** — the interface R4 must implement (tiny).
3. **`chinatravel/agent/nesy_verifier/repair_strategies/r3.py`** — the richest worked example (R3/R3P, ladder, metadata contract).
4. **`docs/PRD_R3_adaptive_repair.md`** — the design-spec template to copy for an R4 PRD.
5. **`experiments/Commands_to_test_queries.md`** — exact run/eval/matrix workflow + which split per strategy + the R4 matrix-fusion scenarios.
6. **`chinatravel/evaluation/REPAIR_COMPARISON.md`** (or `REGRESSION_MATRIX.md`) — the evidence/matrix contract.

If a 7th slot is allowed: `chinatravel/evaluation/repair_attempt.py` (the attempt-record schema
that feeds the matrix) or `CONTRIBUTIONS.md` (file ownership map — but note its stale rows).

---

*Honesty notes: Items marked "verified this session" were confirmed by reading code / running
the suite on `main` @ `3b47d9a`. R4 is unwritten. The only committed experiment evidence is the
5-query pilot runs; no `subset_train/test` production results exist in the repo yet. README and
CONTRIBUTIONS prose is partly stale (R2/R4 status, 221 vs 277 tests, subset sizes) — trust the
code and the split files over that prose.*
