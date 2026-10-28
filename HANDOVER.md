# Project Overview — DSA4213 Verification-Guided Travel-Planner Repair

## 1. What this project is (one paragraph)

We forked the **ChinaTravel** benchmark. ChinaTravel asks an LLM to build a multi-day travel
itinerary (flights/trains, hotels, attractions, restaurants, inner-city transport) that satisfies
a natural-language request **plus** a set of machine-checkable constraints, and it ships a
**verifier** that checks any itinerary against those constraints. When the itinerary fails a
constraint, the planner tries to **repair** it and re-checks. Our project does **not** change how
planning or checking works. We **hold the verifier fixed** and change only the **repair step**,
then compare repair strategies head-to-head. This is an *ablation of the repair method*.

**Research question.** *Can modelling constraint interdependencies improve the effectiveness and
efficiency of verification-guided repair?* When you repair the one constraint that is failing, do
you accidentally break constraints that were already passing (a "cascade")? And can we reduce
those cascades by **modelling which constraint types tend to break which other types**? The
headline artifact is a **regression / interaction matrix** `M[i][j] = probability that constraint
family j newly breaks when we repair family i`. Our final strategy (R4) reads this matrix and adds
advisory risk text to the repair prompt. Importantly, R4 only *warns* the LLM about likely
cascades — it does not enforce anything (see §9).

---

## 2. The five repair strategies (what differs is ONLY the repair)

Every strategy generates an initial plan the same way and is checked by the **same shared
verifier after every repair attempt**. They differ only in *what part of the plan is allowed to
change* during a repair.

| Strategy | Idea | One-line behaviour | Guard against regressions? |
|---|---|---|---|
| **R0** | Baseline | Regenerate the **whole** itinerary from scratch given the verifier's error list. | No — always accepts |
| **R1** | Targeted | Edit only the **one slot** tied to the failing constraint (one activity or nested transport); freeze everything else. | No |
| **R2** | Protected | Whole-plan rewrite, but its `accept()` **rejects any candidate that breaks a previously-passing personal constraint** (a hard rollback). | **Yes** — the only strategy with a real guard |
| **R3** | Adaptive scope | Start narrow (slot), widen **slot → day → plan** driven by the iteration counter (1–2 slot, 3–4 day, 5+ plan). At its narrowest it behaves like R1, at its widest like R0. | No |
| **R4** | Matrix-guided | R3-at-plan-scope **plus advisory regression-matrix text in the prompt**. Each round it reads the learned matrix `M`, ranks the failing constraints by estimated cascade risk, and appends that advice to the prompt. | **No — advisory only** (it warns the LLM; it does not override `accept()`) |

> **R3P is gone.** An earlier "phased" variant (R3P) was folded into R3 and removed. If any doc
> still mentions R3P as a separate strategy, that doc is stale — there are exactly five: R0–R4.

> **Be honest about R4.** R4 is mechanically "R3 edited at whole-plan scope, with advisory matrix
> text added to the prompt." It does **not** override the accept/reject step, so it inherits the
> base `accept()` that always returns `True`. The matrix changes **prompt content only** — never
> the editing scope, the candidate selection, or the loop's repair order. **R4 does not prevent
> regressions; only R2 does.** The case study in §9 even shows R4 accepting a regressing candidate.
> This is the single most important thing to state plainly when presenting the project.

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

## 3. What was built and run

- Shared framework: one verifier + one repair loop + a strategy registry. All five strategies
  (R0, R1, R2, R3, R4) are implemented and selectable.
- The matrix pipeline: run a strategy → per-attempt log → regression matrix CSVs.
- The **learned matrix `M`** was built by pooling R0–R3 **training** trajectories
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
- Automated tests: **41 test files under `tests/`**; the suite passes offline (run it to get the
  exact assertion count — the number of files is stable, the assertion count is not pinned here).

**A few practical notes on the committed runs (not open work, just things a reader should know):**
- The `subset_test-r1` run has `attempts.jsonl` + `benchmark_eval` and appears in the analysis
  tables, but its `summaries.csv`, `pass_rates.csv`, and `regression_matrix/` were not built, so
  some R1 cells are read from the benchmark eval rather than a `pass_rates.csv`.
- There is **no `subset_train-r4`** run by design: R4 must be evaluated on held-out data, so it was
  only run on `subset_test`. The matrix it consumes is learned from R0–R3 training runs.
- The **data-quality caveats in §6 shape the numbers**. They are documented and understood, not
  undiscovered bugs.

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

**Headline test-set results** (All = 30 queries; sources: `test_result_analysis/merged/*.csv`,
each run's `benchmark_eval/*/benchmark_summary.json`). Treat small differences as noise — only
~10 queries per difficulty group, so a swing of one or two queries is not meaningful.

| Metric (All, n=30) | R0 | R1 | R2 | R3 | R4 |
|---|---|---|---|---|---|
| Avg personal-constraint failures — final | 0.73 | 0.57 | 0.57 | 0.53 | 0.57 |
| Avg commonsense checks failed — final | 3.67 | 5.80 | 3.90 | 3.63 | **2.73** |
| Logical micro % | 88.30 | 90.96 | 90.96 | **91.49** | 90.96 |
| Logical macro % | 50.0 | 53.3 | 56.7 | **60.0** | 56.7 |
| Commonsense micro % | 86.90 | 79.29 | 86.07 | 87.02 | **90.24** |
| Full-pass rate (schema + CS + PC) | 0/30 | 1/30 | 0/30 | 2/30 | 2/30 |
| Harmful repairs rejected | — | — | **11** | — | — |
| Avg repair time / query (s) | 102.3 | **18.0** | 92.1 | **167.8** | 100.2 |
| Avg tokens / query | 92,483 | 104,614 | 92,640 | **183,897** | 109,103 |

**How to read it.** R4 is the best on **commonsense** (fewest final commonsense failures, highest
commonsense micro 90.2% vs R0 86.9%) — a small but consistent edge. R3 edges the **logical**
metrics (micro 91.49%, macro 60%) and full-pass, but is the **most expensive** on time and tokens.
R1 is the **cheapest and fastest** (~18 s/query) but **worst on commonsense**. R2's rollback guard
**rejected 11 harmful repairs** and never let a passing personal constraint regress.

> **Do not read full-pass rates as "the strategy failed."** Full pass requires *every* personal +
> commonsense check to pass with no technical error, and these queries are hard. The research
> signal is the **transitions** — how many failing constraints got fixed vs how many passing ones
> got broken (cascades) — captured per attempt in `attempts.jsonl` and summarised in the
> `test_result_analysis/` tables. Judge strategies on fix-vs-cascade behaviour, not raw full-pass.

> **Fairness caveat (read before quoting any cross-strategy number).** The five strategies did
> **not** start from the same initial itinerary for a given query — each regenerated its own first
> draft (confirmed by differing `initial_plan_hash` across R0–R4 for the same UID). So a lower
> final failure count could reflect an easier first draft rather than better repair. The honest,
> defensible comparison is **within-strategy initial→final improvement**, not absolute final
> levels. The `test_result_analysis/` tables report both initial and final, so the delta view is
> available.

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

## 9. Project status & honest limitations

The project is complete for the DSA4213 deliverable: all five strategies are implemented, were run
on the held-out test set, and the results and matrix are committed. What the experiments can and
cannot say is below — stated plainly so an outside reader can judge the work fairly.

**What we can legitimately claim.** With the same model, verifier, and budget across all five
strategies, R4's prompt-level matrix advice did not hurt and gave a small commonsense-satisfaction
edge (commonsense micro 90.2% vs R0 86.9%; fewest final commonsense failures; ~+0.93 commonsense
and ~+0.17 personal constraints satisfied per query vs R0). R2's hard rollback guard provably
worked — it rejected 11 regressing rewrites and never let a passing personal constraint break. R3
traded the best logical-macro score for the highest cost. So the effectiveness-vs-efficiency
trade-off is real and measurable, and R4 is **promising on commonsense** — not proven.

**What would be too strong to claim.** "R4 works" or "modelling constraint interdependencies
improves repair" as a causal result. The evidence does not support that, for the reasons below.

**Honest limitations.**

1. **R4 is advisory only — no regression guard.** R4 does not override `accept()`; it only adds
   risk text to the prompt and trusts the LLM to act on it. It does not block regressions. A
   concrete trace: on query `h20241029143652031792`, one of R4's commonsense-phase repairs broke a
   previously-passing personal constraint and R4 accepted it anyway (a later round happened to
   re-fix it). Only R2 enforces. Mechanically, R4 = R3-at-plan-scope + prompt text.

2. **The strategies did not start from identical initial plans.** For the same query, R0–R4 each
   regenerated their own first itinerary (different `initial_plan_hash`). Cross-strategy
   *final-level* comparisons are therefore confounded; only *within-strategy initial→final* deltas
   are a fair signal. Any claim that R4 "started from the same plan as R0" is incorrect.

3. **The regression matrix is sparse and low-support.** Most of the 100 cells are unobserved
   (support 0) and fall back to a neutral 0.5. Only two relationships have real support —
   `commonsense_repair → accommodation` (34/99 ≈ 0.34) and `commonsense_repair → monetary_budget`
   (15/91 ≈ 0.17). Low-N cells (e.g. 2/2 = 1.0) are not reliable estimates. A clean pipeline does
   not establish that the matrix has useful statistical support.

4. **Small sample.** n = 30 on test (≈10 per difficulty group), so a one- or two-query swing is
   noise. Differences between strategies are small relative to that.

5. **Data-quality caveats (see §6)** — named-place constraints checked in Chinese during repair,
   missing walking-leg prices, a timing-check crash, and failed-model-call stubs — affect all
   methods and are documented in `test_result_analysis/README.md`.

**If someone extends this work**, the two most valuable improvements would be (a) start every
strategy from the *same* initial plan per query so final-level comparisons become fair, and (b)
give R4 (or a new strategy) a *hard* guard so the matrix actually filters candidates rather than
only advising. Keep the fairness invariant (same model, budget, language, greedy sampling) and the
train/test separation (learn `M` on train, compare on test).

---

*Honesty notes: result numbers in §5 are read from the committed `test_result_analysis/merged/`
tables and each run's `benchmark_eval` summaries. The exact unit-test assertion count isn't pinned
here — there are 41 test files under `tests/`; run the suite for the assertion count. Known
data-quality caveats (named-place translation, failed-model-call stubs, walking-leg price,
timing-check crash) are real and documented in `test_result_analysis/README.md`; they shape the
numbers and are not new bugs. All five strategies have a `subset_test` run; `subset_test-r1` has
only `attempts.jsonl` + `benchmark_eval` (no summary/matrix outputs).*
