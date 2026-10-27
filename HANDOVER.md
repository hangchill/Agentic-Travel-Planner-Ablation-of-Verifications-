# HANDOVER — DSA4213 Verification-Guided Travel-Planner Repair

> **Read this file alone and you can understand the whole project and continue it.**
> You do not need to open any Python file to follow what we did, why, and what is left.
> Code-level pointers are given only so you know *where* to look if you choose to.
>
> Last updated against `main` @ `2ae0ed1` (after the ablation-comparisons + dashboard work and
> the R0/R4 comparison were merged). Working tree clean. Where a number or claim could be stale,
> it is flagged.

---

## 1. What this project is (one paragraph)

We forked the **ChinaTravel** benchmark. ChinaTravel asks an LLM to build a multi-day travel
itinerary (flights/trains, hotels, attractions, restaurants, inner-city transport) that satisfies
a natural-language request **plus** a set of machine-checkable constraints, and it ships a
**verifier** that checks any itinerary against those constraints. When the itinerary fails a
constraint, the planner tries to **repair** it and re-checks. Our project does **not** change how
planning or checking works. We **hold the verifier fixed** and change only the **repair step**,
then compare repair strategies head-to-head. This is an *ablation of the repair method*.

**Research question.** When you repair the one constraint that is failing, do you accidentally
break constraints that were already passing (a "cascade")? And can we reduce those cascades by
**modelling which constraint types tend to break which other types**? The headline artifact is a
**regression / interaction matrix** `M[i][j] = probability that constraint family j newly breaks
when we repair family i`. Our final strategy (R4) reads this matrix to repair in an order/scope
that avoids cascades.

---

## 2. The five repair strategies (what differs is ONLY the repair)

Every strategy generates an initial plan the same way and is checked by the **same shared
verifier after every repair attempt**. They differ only in *what part of the plan is allowed to
change* during a repair.

| Strategy | Idea | One-line behaviour | Status |
|---|---|---|---|
| **R0** | Baseline | Regenerate the **whole** itinerary from scratch given the verifier's error list. | Implemented, registered |
| **R1** | Targeted | Edit only the **slot(s)** tied to the failing constraint; freeze everything else. | Implemented, registered |
| **R2** | Protected | Whole-plan rewrite, but **track** which previously-passing constraints it broke; can reject/roll back a regressing candidate. | Implemented, registered |
| **R3** | Adaptive scope | Start narrow (slot), widen **slot → day → plan** on a schedule. At its narrowest it behaves like R1, at its widest like R0. | Implemented, registered |
| **R4** | Matrix-guided | Reads the learned matrix `M` and chooses repair order/scope to **minimise cascades**. The core research contribution. | Implemented, registered |

> **R3P is gone.** An earlier "phased" variant (R3P) was folded into R3 and removed. If any doc
> still mentions R3P as a separate strategy, that doc is stale — there are exactly five: R0–R4.

**Why this is a fair comparison (the control).** All five call one verifier,
`chinatravel/agent/nesy_verifier/shared_verifier.py::verify_plan`, which re-checks the **entire
itinerary against all constraints** after each attempt. Any difference in results is therefore due
to the repair method, not the checker.

**Two different "baselines" — don't confuse them:**
- **Project R0** (`--strategy R0`) runs through *our* shared repair loop and shared verifier. This
  is the baseline we ablate R1–R4 against.
- **Legacy ChinaTravel** (running the original agent with no repair strategy) uses the original,
  separate verification path. It is **not** our comparison baseline.

---

## 3. Current status — DONE vs TODO

**DONE**
- Shared framework: one verifier + one repair loop + a strategy registry. All five strategies
  (R0, R1, R2, R3, R4) are implemented and selectable.
- The matrix pipeline: run a strategy → per-attempt log → regression matrix CSVs.
- The **learned matrix `M`** has been built by pooling R0–R3 **training** trajectories
  (`r4/main_matrix_from_subset_train_r0_r3_10x10.csv` and its `_probabilities.csv`).
- **Training runs** on `subset_train` (60 queries) committed for **R0, R1, R2, R3**.
- **Test runs** on `subset_test` (30 queries) committed for **all five: R0, R1, R2, R3, R4**.
- Per-method **result tables** (personal-constraint, commonsense, repair-process, benchmark
  metrics) under `test_result_analysis/` for R0–R4, plus a merged side-by-side comparison.
- **Ablation / comparison layer** (`scripts/result_analysis/ablation_comparisons/`): offline,
  read-only pairwise comparisons over the test reporting — R0↔R2 (rollback protection), R1↔R3
  (editing-scope flexibility), R3↔R4 (advanced strategies), and R0↔R4 (matrix-guidance; delta =
  R4 − R0). It reads the generated CSVs; it never runs experiments or scores plans.
- **Results dashboard** (`dashboard/`): a local, read-only Streamlit app that visualises the test
  reporting and ablation comparisons. No models/evaluators/writers are invoked.
- Language-aware verifier (English itineraries checked against the English sandbox) and
  **named-place translation** for scoring (Chinese place names in the DSL are matched to the
  English plan at eval time). Cross-platform (Windows) logging fixes.
- Test suite green (41 test files under `tests/`; run it to get the exact assertion count).

**TODO / gaps to be aware of**
- The `subset_test-r1` run has `attempts.jsonl` + `benchmark_eval` (and is in the analysis
  tables) but is **missing its `summaries.csv`, `pass_rates.csv`, and `regression_matrix/`** —
  the summary and matrix steps weren't run for it. Run those two offline steps (see §7) to make
  R1 consistent with the other test runs.
- **No `subset_train-r4`** run. R4 is evaluated on `subset_test` only (correct, since R4 must be
  tested on held-out data), and there is a small training-only R4 pilot path if needed.
- **Write-up / interpretation.** The tables exist; the narrative comparing strategies (does
  matrix guidance actually reduce cascades vs R0?) still needs to be written from them.
- **Known data-quality caveats affect the numbers** — see §6. They are documented, not bugs to
  rediscover.

---

## 4. How a single run works (the pipeline, no code needed)

```
run_experiments.py  (pick ONE strategy, ONE split)
      │   for each query: build an initial plan, then repair-and-recheck up to 6 times
      ▼
experiments/<run-id>/
   ├── run_manifest.json   model, split, max-steps, git commit, sampling args  (the fairness record)
   ├── attempts.jsonl      one line per repair attempt  ◄── the single source of truth
   └── queries/<uid>/      per-query initial state + final plan (+ reference query)
      │
      ├─► scripts/result_analysis/evaluate_repair_run.py   → benchmark_eval/  (schema/commonsense/logical scores)
      ├─► scripts/result_analysis/build_repair_summary.py  → summaries.csv, pass_rates.csv, phase_outcomes.csv, llm_cache_hits.csv
      └─► scripts/matrix_building/build_regression_matrix.py → regression_matrix/  (the M builder)
```

Each line in `attempts.jsonl` records the constraints **before** and **after** the attempt and
the transition sets `{fixed, newly_violated, still_failed, still_passed, unknown}`. The
`newly_violated` set is the **cascade signal** the matrix `M` is built from.

**Building the matrix M for R4.** Run R0–R3 on `subset_train`, build each one's regression matrix,
then **pool** them into one matrix (sum the regression counts and the attempt supports across
R0–R3, then divide). That pooled matrix is what R4 consumes. The committed pooled matrix lives at
`r4/main_matrix_from_subset_train_r0_r3_10x10.csv`; R4 is pointed at a matrix via the
`--r4-matrix PATH` flag (or the `CHINATRAVEL_R4_MATRIX` env var).

---

## 5. Data splits and the committed experiment runs

**Splits** (`chinatravel/evaluation/default_splits/<name>.txt`, one query id per line):

| Split | Size | Role |
|---|---|---|
| `pilot5` | 5 | Shared smoke set — run a new strategy here first for a quick sanity check. Subset of `subset_train`. |
| `subset_train` | 60 (20 easy / 20 medium / 20 human) | **Learn** the matrix `M` from R0–R3 here. |
| `subset_test` | 30 (10 easy / 10 medium / 10 human) | **Main comparison** and held-out R4 test. No overlap with train. |
| `combined_train` / `combined_test` | 422 / 182 | Full stratified 70/30 split. |
| `medium_train` / `medium_test` | 105 / 45 | Medium-difficulty only. |

Difficulty of each query comes from `chinatravel/evaluation/splits/subset_origin.json`, not from
the id prefix — the analysis tables group Easy/Medium/Human using that map.

**Committed runs** under `experiments/` (git-tracked):

| Run folder | Strategy | Split | Notes |
|---|---|---|---|
| `subset_train-r0` | R0 | train | |
| `subset_train-r1` | R1 | train | |
| `subset_train-r2` | R2 | train | |
| `subset_train-r3-new` | R3 | train | current R3 training run |
| `subset_test-r0` | R0 | test | 5 queries were reran after provider failures — see §6 and their `rerun_provenance.json` |
| `subset_test-r1` | R1 | test | has `attempts.jsonl` + `benchmark_eval` only; `summaries.csv`/`pass_rates.csv`/`regression_matrix/` not yet built (see §3) |
| `subset_test-r2` | R2 | test | |
| `subset_test-r3` | R3 | test | 1 query reran after provider failures (`rerun_provenance.json`) |
| `subset_test-r4` | R4 | test | matrix-guided; its matrix inputs are under `inputs/pooled/` |

`r4_signal_exploration/` and `archives_runs/` hold exploratory / superseded material.
`.gitignore` ignores `results/` and `cache/`; `experiments/` **is** tracked. Per team convention
we commit each run folder **except its `logs/` subfolder**.

**Headline test-set results** (final full-pass rate = whole plan passes every check). R0/R2/R3/R4
are from each run's `pass_rates.csv`; R1 is from its benchmark summary + analysis table (it has no
`pass_rates.csv` yet). Treat small differences as noise — only 10 queries per difficulty group.

| Strategy (subset_test) | Final full-pass rate | Final "all personal constraints pass" rate |
|---|---|---|
| R0 | 2/30 (6.7%) | 43% |
| R1 | 1/30 (3.3%) | ~47% (14/30 final plans with 0 failed personal constraints) |
| R2 | 1/30 (3.3%) | 53% |
| R3 | 3/30 (10%) | 50% |
| R4 | 1/30 (3.3%) | 43% |

> **Do not read these full-pass rates as "the strategy failed."** Full pass requires *every*
> personal + commonsense check to pass with no technical error, and these queries are hard. The
> research signal is the **transitions** — how many failing constraints got fixed vs how many
> passing ones got broken (cascades) — captured per attempt in `attempts.jsonl` and summarised in
> the `test_result_analysis/` tables. Judge strategies on fix-vs-cascade behaviour, not raw full-pass.

---

## 6. Conventions and gotchas (read before changing or trusting numbers)

- **Fairness invariant.** Keep the model and settings identical across all strategies:
  **DeepSeek V3 (`deepseek/deepseek-chat`) via OpenRouter, `--lang en`, `--max-steps 6`,
  `temperature=0`, `top_p≈0` (greedy).** `run_manifest.json` records these per run so fairness is
  auditable. Any result difference must come from the repair method, not the setup.
- **Train vs test (no leakage).** Develop and learn `M` on `subset_train`; evaluate the
  held-out comparison (especially R4) on `subset_test`. Main comparisons are made on
  `subset_test`.
- **Named-place constraints are translated at scoring time.** The query DSL keeps Chinese place
  names (e.g. `{'寒山寺'}<=attraction_name_set`) but English plans use English names. The
  evaluator swaps in the English name of the same database row before scoring (logged in each
  run's `benchmark_eval/*/named_place_translations.json`). **During repair** the loop still
  checked the Chinese name, so it reported those constraints as failed even when the plan had the
  right place — the tables include "excluding named-place constraints" rows to show results
  without that artifact.
- **Failed model calls can poison a result (important).** When a provider request fails,
  the model wrapper returns the text `{"error": "Request failed, please try again."}` instead of
  raising. That round then has **no token count**, the repeat-request cache can serve that error
  text to later identical requests, and a strategy that always accepts (R0) can take the error
  text as its "new plan" — replacing a working plan with an error stub. **This is exactly what
  happened to 5 queries in the original `subset_test-r0` run; we reran those 5, replaced their
  checkpoints, and rebuilt the eval outputs** (each carries a `rerun_provenance.json`; the R3 test
  run had 1 such rerun). If you see a query with `model_call_data_complete = False` or an
  error-stub final plan, that query needs a rerun before its tokens/metrics are trustworthy.
- **Other documented data caveats** (see `test_result_analysis/README.md` for the full list):
  walking legs can miss a `price` field (fails a schema/commonsense check); a timing-check bug can
  raise on transport that departs before arrival (hides timing errors / stops a query early); a
  plan the commonsense evaluator crashes on is counted as failing all checks in Tables 1–3.
- **Small groups.** 10 queries per difficulty group — a one- or two-query swing is noise.
- **Stray/again:** `.env` holds the OpenRouter key (`CHINATRAVEL_OPENAI_API_KEY`,
  `CHINATRAVEL_OPENAI_BASE_URL=https://openrouter.ai/api/v1`). **Never commit `.env`.** Python 3.12
  in `.venv`.

---

## 7. How to run everything (copy-paste)

**Setup (once)**
```bash
python3.12 -m venv .venv
source .venv/bin/activate                      # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python scripts/experiment_setup/setup_project.py   # downloads both sandboxes (database/, database_en/)
cp .env.example .env                           # then paste the OpenRouter key into .env
```

**Run one strategy on one split** (`--strategy` ∈ R0, R1, R2, R3, R4)
```bash
python run_experiments.py \
  --strategy R3 --splits subset_test \
  --llm deepseek/deepseek-chat --lang en \
  --max-steps 6 \
  --output-dir experiments --run-id subset_test-r3
# resume a partial run: add --resume ; retry failed queries: add --resume --retry-failed
# run only specific queries: --index <uid> <uid> ...
```

**R4 needs the learned matrix:**
```bash
python run_experiments.py \
  --strategy R4 --splits subset_test \
  --llm deepseek/deepseek-chat --lang en --max-steps 6 \
  --r4-matrix r4/main_matrix_from_subset_train_r0_r3_10x10.csv \
  --output-dir experiments --run-id subset_test-r4
```

**Evaluate + summarise + build the matrix for a run** (no API calls; safe to re-run)
```bash
python scripts/result_analysis/evaluate_repair_run.py  --run-dir experiments/subset_test-r3
python scripts/result_analysis/build_repair_summary.py --input   experiments/subset_test-r3
python scripts/matrix_building/build_regression_matrix.py \
  --input experiments/subset_test-r3/attempts.jsonl \
  --output-dir experiments/subset_test-r3/regression_matrix \
  --repair-strategy R3
```

**Build the per-method analysis tables** (what's under `test_result_analysis/`)
```bash
python scripts/result_analysis/build_test_result_tables.py \
  --run experiments/subset_test-r0 --run experiments/subset_test-r2 \
  --run experiments/subset_test-r3 --run experiments/subset_test-r4
```

**Build the ablation comparisons** (offline, reads the tables above)
```bash
python -m scripts.result_analysis.ablation_comparisons.build_ablation_comparisons \
  --r0 experiments/subset_test-r0 --r1 experiments/subset_test-r1 \
  --r2 experiments/subset_test-r2 --r3 experiments/subset_test-r3 \
  --r4 experiments/subset_test-r4 \
  --test-reporting-dir test_result_analysis \
  --output-dir results/analysis/ablation_comparisons
```

**Launch the results dashboard** (local, read-only; separate requirements file)
```bash
python -m pip install -r requirements-dashboard.txt
streamlit run dashboard/app.py          # binds to 127.0.0.1; "Refresh local data" after edits
```

**Tests**
```bash
python -m unittest discover -s tests -p "test_*.py"
```

**Check remaining OpenRouter credit before a run** (runs cost real money)
```bash
curl -s -H "Authorization: Bearer $(grep -m1 '^CHINATRAVEL_OPENAI_API_KEY=' .env | sed 's/^[^=]*=//' | tr -d '\"')" \
  https://openrouter.ai/api/v1/key
```

---

## 8. Where things live (only if you want to read code)

**Repair framework — `chinatravel/agent/nesy_verifier/`**
- `shared_verifier.py` — `verify_plan()`: structure + commonsense + personal-constraint checks;
  returns a tri-state per constraint (pass / fail / couldn't-evaluate) and keeps technical errors
  on separate channels.
- `shared_repair_loop.py` — `run_repair_loop()`: the loop that verifies, calls the strategy's
  `repair()`, re-verifies, applies the strategy's `accept()`, and logs one attempt record per step
  (budget capped at 6).
- `repair_strategies/` — `base.py` (the interface every strategy implements), then `r0.py`…`r4.py`;
  `__init__.py` is the registry (`STRATEGY_FACTORIES = {R0, R1, R2, R3, R4}`).

**Evaluation + matrix — `chinatravel/evaluation/`**
- `regression_matrix.py` — builds the matrix `M` from attempt records.
- `constraint_families.py` — the 9 families: `trip_specification, party_resources,
  monetary_budget, accommodation, dining, attraction, transport_mode, travel_extent,
  schedule_order` (plus a `commonsense_repair` source row in the matrix).
- `repair_attempt.py` — the per-attempt record schema; `*.md` files are the specs/contracts.

**R4 helpers — `r4/`**
- `main_matrix_from_subset_train_r0_r3_10x10.csv` (+ `_probabilities.csv`) — the committed learned
  matrix; `main_matrix_manifest.json` records how it was pooled and from which runs.
- `README.md` — the full R4 training/matrix workflow; `run_r4.py` / `run_r4_pipeline.py` are
  optional helpers (the normal path is `run_experiments.py --strategy R4 --r4-matrix ...`).

**Analysis output — `test_result_analysis/`**
- One folder per method (`R0`, `R1`, `R2`, `R3`, `R4`) with `table1_pc.csv` (personal constraints),
  `table2_cs.csv` (commonsense), `table3_repair_process.csv` (tokens/time/rounds),
  `table4_eval_exp.csv` (benchmark metrics), and `per_query.csv`.
- `merged/` + `MERGED_TABLES.md` — all methods side by side. `README.md` there defines every
  metric and lists all data caveats. **Read that README to interpret any number correctly.**

**Ablation comparisons + dashboard**
- `scripts/result_analysis/ablation_comparisons/` — the offline pairwise-comparison builder
  (`build_ablation_comparisons.py`) and its README (defines the four canonical pairs and the
  delta = Right − Left convention). Output lands under `results/analysis/ablation_comparisons/`.
- `dashboard/` — the Streamlit app (`app.py`, `pages/`, `components/`) plus `*_REPORTING.md` and
  `DATA_AUDIT.md`. Read `dashboard/DATA_AUDIT.md` for which metrics are available and where
  TEST-reporting and the analyzer disagree.

**Runners / docs**
- `run_experiments.py` — the canonical study runner. `run_exp.py` — the general ChinaTravel
  launcher (not the study runner).
- `experiments/Commands_to_test_queries.md` — the 4-step run→eval→summary→matrix workflow and the
  matrix-fusion scenarios for R4.
- `docs/PRD_R3_adaptive_repair.md` — the R3 design spec (a good template if you write an R4 spec).

---

## 9. What the next person should probably do

1. **Finish the `subset_test-r1` eval** — build its `summaries.csv`/`pass_rates.csv` and its
   `regression_matrix/` (run the two offline steps in §7 on `experiments/subset_test-r1`) so R1
   is consistent with the other four test runs. The run and benchmark eval already exist.
2. **Write the results narrative** from `test_result_analysis/` + the regression matrices: does
   matrix-guided R4 actually reduce cascades (`newly_violated`) relative to R0, and how do R1/R2/R3
   sit in between? Use the cascade/fix transitions, not raw full-pass rates.
3. **Watch for poisoned runs.** Before trusting any run's tokens/metrics, confirm no query has an
   error-stub final plan or `model_call_data_complete = False`; rerun offending queries and replace
   their checkpoints (mirror the existing `rerun_provenance.json` pattern), then rebuild the eval
   outputs.
4. **Keep the fairness invariant** (model, budget, language, greedy sampling) identical across any
   new runs, and keep train/test separation (learn `M` on train, compare on test).

---

*Honesty notes: result numbers in §5 are read from the committed `pass_rates.csv` of each
`subset_test` run. The exact unit-test assertion count isn't pinned here — run the suite for it.
Known data-quality caveats (named-place translation, failed-model-call stubs, walking-leg price,
timing-check crash) are real and documented in `test_result_analysis/README.md`; they shape the
numbers and are not new bugs. All five strategies now have a `subset_test` run, but
`subset_test-r1` still lacks its summary/matrix outputs (only `attempts.jsonl` + `benchmark_eval`
exist).*
