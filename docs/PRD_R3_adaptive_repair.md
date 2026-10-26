# PRD — R3 Adaptive-Scope Repair Strategy (+ per-prompt matrix-component logging)

## Context

The group project (see `CLAUDE.md`) extends ChinaTravel's `LLM-modulo` planner with repair
strategies R0–R4 to study whether modelling constraint interdependencies improves
verification-guided repair. A teammate has delivered the shared framework + R0; this PRD
adds **R3 (adaptive-scope repair)** as a plug-and-play strategy selectable via
`--repair_strategy R3`, and specifies the per-prompt logging of the raw components from which
the constraint-interdependency matrix `M` is built later.

> Shared **evaluation metrics and difficulty-tier logging** are a *separate* PRD
> (`docs/PRD_eval_metrics.md`, forthcoming), since they apply to R0–R4, not just R3.

### Teammate progress — verification result (verified by code inspection)

| Claim | Status | Evidence |
|---|---|---|
| Shared verifier | Present & coherent | `shared_verifier.py::verify_plan` returns tri-state `personal_constraints` (T/F/None), separates genuine violations (`error_info`) from technical channels (`verifier_errors`, `translation_errors`, `schema_errors`); forces `passed=False` on any technical error. |
| Repair loop | Present | `shared_repair_loop.py::run_repair_loop` verifies → `strategy.repair()` → verifies candidate → `strategy.accept()` → records every attempt; keeps accepted plan separate from candidate; honours `max_steps` (rejected attempts still consume budget). |
| Constraint-transition logging | Present, **personal-only** | `compare_constraint_results` emits `{fixed, newly_violated, still_failed, still_passed, unknown}` — but only diffs `personal_constraints`, not commonsense. Full candidate `verification` (incl. commonsense/schema) *is* stored per history entry, so commonsense transitions are recoverable offline. |
| R0 tested end-to-end | Supported | `tests/test_shared_verifier_reliability.py`; `framework_r0.ipynb` documents an end-to-end GPT-4.1 run on medium case `e20241028160845920703` (errors 38→3→2, and an accommodation constraint that passed then regressed — exactly the interdependency signal we want). |

### Key facts the design relies on (from the code)

- `run_repair_loop(problem, raw_plan, strategy, context, llm, translate_fn, max_steps)` keeps
  **one strategy instance** for the whole loop → R3 can hold state (`self._scope`,
  `self._stuck`) across steps. The loop does **not** pass a step index or history into
  `repair()`; R3 tracks its own.
- `repair(problem, raw_plan, verification_results, context, llm)` receives the **itinerary
  list** (list of day dicts) as `raw_plan` and must **return an itinerary list** in
  `RepairResult.repaired_plan` (the loop wraps it as `{"itinerary": ...}`). R0 confirms this.
- The loop **already re-verifies all constraints every step** (R3's "reverify after each
  attempt" requirement is met for free).
- `context` = the 8 shortlist fields (`go_train_info`, …, `innercity_transport_info`), built
  once in `llm_modulo.py` (~line 319) — same dict R0 formats into `BACK_PROMPT`.
- `verification_results` keys available to R3: `commonsense_errors`, `personal_constraints`,
  `personal_errors`, `schema_errors`, `error_info`, `passed`, plus technical channels.

## Goal

Implement `repair_strategies/r3.py` so that `--repair_strategy R3` runs adaptive-scope repair
with the **same plumbing** R0 uses, and **logs, per prompt, the raw components** from which the
matrix can be built in a **later, separate task**. Building `M` is out of scope here.
"Plug and play" = add `r3.py` and register it in `llm_modulo.py`'s `if/elif`; **do not delete
`r0.py`** (R0 remains the baseline for comparison).

## Design

### R3 in one line

**R3 is R1 that gradually relaxes into R0.** It always edits the *current accepted plan*, but
starts with the least freedom (only the failed slots, exactly like R1) and **earns more
freedom only when it gets stuck** — first the failing day, then the whole plan. At its tightest
rung it *is* R1; at its widest it *is* R0. Contrast with siblings (axis = how much may change):

| Strategy | What it may change each round | Guard |
|---|---|---|
| R0 | the whole plan, always | none |
| R1 | only the failed-constraint slots, always | hard freeze everywhere else |
| R2 | the whole plan, always | reject + roll back if a previously-passing constraint breaks |
| **R3** | **starts = R1's slots; widens slot → day → plan as it stalls** | hard freeze outside the *current* scope |

### Does R3 start from the draft? Yes — scope ≠ what it sees

Step 0 is the initial draft (`INITIAL_PROMPT`). Every round the loop hands R3 the **current
accepted plan** + its fresh verification. Scope only controls *which part R3 may rewrite*, not
which plan it sees. Each round: (1) read current plan + which constraints fail, (2) compute the
editable region at the current rung, (3) ask the LLM to rewrite only that region, (4) merge
(freeze everything outside), (5) loop re-verifies the whole plan.

### The freedom ladder (3 rungs)

| Rung | Editable region | Frozen | ≈ |
|---|---|---|---|
| L1 `slot` (start) | only activities tied to currently-failing constraints | everything else | R1 |
| L2 `day` | all activities in **any day that contains a failure** | clean days | — |
| L3 `plan` | the whole itinerary | nothing | R0 |

> The `day` rung only adds value for **multi-day** plans. For a 1-day trip L2 == L3, so R3
> effectively has two rungs (slot → whole plan).

**Scope-membership rules (settled):**

- **Hotel + inter-city transport are trip-level anchors — never "day" slots**; they stay frozen
  until L3. They are trip-wide and high-ripple, and L2 already covers every day's activities.
- **Global constraints (budget, day_count) can't localize**, so at L2 they unlock **all** days
  (effectively plan scope). Every step logs an **effective-scope fraction** = editable slots /
  total slots, so a "budget L2" step reads ~1.0 and isn't mistaken for a small edit. At L1 a
  pure-global constraint uses a heuristic slot set (e.g. highest-cost activities for budget).
- **Short trips:** a 2-day plan failing on both days at L2 is effectively L3 — accepted; the
  effective-scope fraction (~1.0) makes it visible.

Accept proposals (R0-style — rollback is R2's job, kept out of R3 so the ablation stays clean).
Re-verify all constraints each attempt (the loop already does this).

### Verification is the control (held constant across R0–R4)

The re-verification in step (5) is **not** part of R3 — it is the shared verifier
(`shared_verifier.py::verify_plan`) that **every** strategy uses identically. R0–R4 ablate
**only the repair step** (which slots may change); the verification never changes, so any
measured difference is attributable to the repair method, not the verifier. Two baselines
exist and must not be confused: **project R0** (`--repair_strategy R0`) runs on the *same*
shared loop + verifier as R3 and is the comparison baseline; the **legacy ChinaTravel** path
(no `--repair_strategy`) uses the original, separate verification and is *not* the baseline.

### Constraint → slot localization (which activities are "implicated")

Produce a set of `(day_idx, activity_idx)` targets from `verification_results`:

- **Commonsense / schema errors:** parse the error string for `day {d}` / `activity {a}` /
  a `position` name and map to that activity (the verifier's messages already carry these).
- **Personal (`hard_logic_py`) constraints:** many are *global* (budget, counts), so exact
  localization is often impossible. Heuristic: scan the DSL text for POI names / activity
  `type` keywords / day references and match activities; **if nothing matches (global
  constraint), mark the target set as "whole plan"** for that constraint. Global constraints
  therefore naturally push R3 toward widening — which is the point of the adaptive design.

This mapping is deliberately approximate; the **adaptive widening is the safety net** when
targeting is too narrow to fix a constraint.

### Enforcement — regenerate-then-merge (this is the "code blocks edits" mechanism)

1. Prompt the LLM with the current plan, the failures, and an explicit list of **editable
   slots** (ask it to change only those and keep everything else identical).
2. Parse the proposal (reuse R0's `repair_json` + the `[{"day": 1,` prefix trick).
3. **Merge in code:** build the returned itinerary by copying **frozen** activities verbatim
   from the current plan and taking **only editable** activities from the proposal, aligned
   by `(day_idx, activity_idx)`. If a frozen day's shape differs in the proposal, the current
   version wins. This guarantees the lock regardless of LLM compliance. (L3 skips the merge
   and takes the proposal wholesale.)

### Climbing a rung — widen only when stuck (the "adaptive" part)

R3 stays on a rung while it keeps improving, and **climbs one rung only after 2 rounds with no
improvement over the best result seen at that rung**. Using *best-so-far at the rung* (not "did
this round beat the last round") correctly treats oscillation (2→1→2… with no new best) as
stuck, instead of mistaking the dip for progress. Scope is a **ratchet — it never drops back**
after progress (dropping back causes L1↔L2 looping and unpredictable step counts). Done in
`accept()` (the only place R3 sees *both* before and after; always returns `True`):

- `violations(v)` = count(`personal_constraints` == False) + len(`commonsense_errors`) +
  len(`schema_errors`).
- Track `best_at_rung` = min violations seen since entering the current rung. If
  `violations(candidate) < best_at_rung` → update best, `self._stuck = 0`; else `self._stuck += 1`.
- When `self._stuck >= 2`: climb one rung (L1→L2→L3), reset `self._stuck = 0` and `best_at_rung`.
- `repair()` reads `self._scope` for the next attempt. (At L3 and still stuck → stay at L3 until
  the repair budget runs out.)

### Prompt

Add an `R3_TARGETED_PROMPT` (new constant in `prompts/llm_modulo.py` or inline in `r3.py`)
derived from `BACK_PROMPT` but with an explicit "You may ONLY modify these slots: …; copy
every other activity unchanged" instruction and the failing-constraint feedback
(`error_info`). L3 reuses the existing `BACK_PROMPT` (whole-plan).

### How new constraint violations appear (freeze is on slots, not constraints)

This is the key mechanism — stated plainly:

1. **R3 freezes itinerary *slots*, never constraints.** "Targeted" / "editable scope" only
   decides **which activities/fields of the plan may change**. It does **not** restrict which
   constraints get checked.
2. **Every attempt re-verifies the *whole* itinerary against *all* constraints** (the loop
   already does this via `verify_plan`). So after any edit, *any* constraint can change
   status — including ones the repair was not trying to fix.
3. **Therefore one targeted edit can break a different constraint.** Changing the single slot
   that a failing constraint points at can have side effects elsewhere in the plan.

   > Example: constraint *diet* fails, so R3 edits one restaurant slot to a dietary-compliant
   > option. That restaurant is more expensive → the plan's **total cost** rises → the
   > **budget** constraint, which was passing, now fails. The dietary edit *caused* a budget
   > regression.

4. **Full re-verification catches it, and that is what we log.** The budget constraint flips
   `pass → fail` in the next `verify_plan`, the loop/R3 records it, and the matrix (built later)
   books it as `diet → budget`. The matrix is literally a tally of these "fixed one, broke
   another" side effects discovered by whole-itinerary re-verification.

So **"single-target" means the repair was *aimed* at one constraint type — not that only one
constraint can change.** The whole value of the matrix depends on the opposite: one aimed
edit, then re-check everything, and see what else moved.

## Logging the matrix components (this task — NOT building the matrix)

**Scope boundary.** This implementation **logs the raw per-step components** from which the
matrix can be built later. **Building `M` — typing constraints, filtering single-target steps,
replay, the num/denom computation, stratification — is a separate downstream task and is NOT in
this implementation.** The definition and rules below are kept only as the *target* the logging
must be sufficient for; none of it is computed by R3.

### Target matrix-entry definition (reference only — built later)

Each entry is the **observed regression rate**: the probability that repairing constraint
type *i* causes a **previously satisfied** constraint type *j* to become violated.

```
                #(repairs targeting i that newly violate j)
M[i->j]  =  -----------------------------------------------------
           #(eligible repairs targeting i where j initially passed)
```

- **Numerator** — over repair steps that targeted *i*: count the steps where *j* was passing
  **before** the step and violated **after**.
- **Denominator** — over the same steps: count the steps where *j* was passing **before**
  (whether or not it later broke). A step where *j* was already failing beforehand is **not
  eligible** for the `(i, j)` cell and contributes to neither.
- Diagonal `M[i->i]` is undefined/skipped (the targeted constraint isn't a "previously
  satisfied" bystander).
- *Worked example:* 20 repairs target dietary; budget passed beforehand in 15 of them
  (denominator = 15); budget newly breaks in 6 (numerator = 6) → `M[diet,budget] = 6/15 = 0.40`.

### Two counting rules

1. **Single-target repairs build the directional matrix.** "Single-target" filters on how many
   constraint types the repair **aimed at** (exactly one *i*), **not** on how many constraints
   change — a single aimed edit is re-verified against the whole plan and may break several
   *j*'s at once; **every** such regression is attributed to that one *i*. Only these
   single-aim steps increment `M` (a hard selection filter, not a weighting). Consequence for
   R3: at L1 it may aim at several failing constraints at once → those steps are *multi-target*
   and excluded from `M`; single-target observations occur when exactly one constraint type is
   failing. This is why R1 is the cleaner matrix source — R3 contributes its single-target
   steps only.
2. **Multi-target repairs are logged but not attributed.** Record them for overall evaluation
   / efficiency metrics; never credit a new violation to one particular target without more
   evidence.

### Aggregation across prompts

Combine by **summing numerators and denominators** across all eligible single-target repairs
(from every prompt), **then divide** — do **not** average per-prompt percentages, because
prompts contribute different numbers of eligible attempts. So the cell is
`M[i->j] = Σ_prompts num_{ij} / Σ_prompts denom_{ij}`.

### What R3 logs per step (this is the actual deliverable)

The loop **already** stores each step's full `verification` — every constraint's pass/fail/None
(personal) plus commonsense/schema errors — for the accepted plan (before) and the candidate
(after). So the **per-constraint status transitions are already captured by the loop.** R3 only
**adds the repair context** needed to attribute them later, via `RepairResult.metadata`:

```python
metadata = {
    "strategy": "R3",
    "step": self._step,                      # R3's internal counter
    "scope_level": self._scope,              # "slot" | "day" | "plan"
    "scope_fraction": 0.18,                  # editable slots / total slots (edit size)
    "changed_slots": 1,                      # slots whose value actually changed after merge
    "editable_slots": [                      # which activities were unlocked (the action)
        {"day": d, "activity_index": a, "type": t, "position": p}, ...
    ],
    "targeted_constraints": [                # the failing constraints this step aimed at (RAW)
        {"kind": "personal", "index": i, "dsl": "..."},
        {"kind": "commonsense", "message": "..."}, ...
    ],
    "per_target_edits": {                    # new slot values per target -> enables later replay
        "<constraint-ref>": [{"day": 1, "activity_index": 2, "new_value": {...}}], ...
    },
    # R0-parity fields:
    "prompt": query_message, "raw_response": response,
    "llm_inference_time": inference_time,
}
```

**What R3 deliberately does NOT do** (these belong to the later matrix-build task):

- It logs **raw** targeted-constraint identities (personal index + DSL text, commonsense
  message). It does **not** compute constraint *types*, a `single_target` flag, or typed status
  — that keeps R3 lean and avoids hard-coding the typing scheme (still an open research point).
- It does **not** compute the matrix, do replay, or stratify. It only logs enough that a later
  tool can.

Why these specific fields: `targeted_constraints` = the *i* side; the loop's before/after
`verification` = every *j*'s pass→fail transition; `per_target_edits` = lets the later builder
replay each target's edit in isolation; `scope_fraction` / `changed_slots` = let it stratify by
edit size. Nothing here needs changes to `shared_repair_loop.py` or `shared_verifier.py`.

### Logging is per-prompt (one self-contained record per query)

Components are logged **per prompt** — which is natural, since each query is one `solve()` call
with a **fresh R3 instance** (state resets) and its **own** file
`cache/<method>_R3/problem_<id>_repair_history.json`. We make each per-prompt file
**self-contained** for standalone, in-depth analysis by including a small header alongside the
per-step entries:

```python
{
  "uid": "<query id>",
  "constraints": {                       # the query's full constraint set, by stable index
     "personal": {0: "<dsl>", 1: "<dsl>", ...},   # == problem["hard_logic_py"]
     # commonsense categories are query-independent (the fixed taxonomy)
  },
  "ladder_config": {"rungs": ["slot", "day", "plan"], "patience": 2},
  "steps": [ { "...per-step metadata above...": None }, ... ]
}
```

Why this matters: **within one prompt the personal-constraint index space is fixed**, so a
per-prompt, **index-level** interdependency view (which specific constraint broke which) can be
read straight from the logs **without any typing** — that is the clean, in-depth per-prompt
analysis. Cross-prompt pooling is the only thing that needs typing, and that is the later task.
Keep `uid` on every record so per-prompt logs are joinable to `results/<method>_R3/<uid>.json`.

### Later (separate task — NOT in this implementation): building `M` from the logs

Recorded here only so we know the logging above is sufficient. A future tool will: (1) **type**
constraints (commonsense→taxonomy category; personal→concept-function type via `func_dict` keys
in `concept_func.py`); (2) keep **single-target** steps, and additionally **replay** disjoint
multi-target sub-edits; (3) compute `M[i->j] = Σ num / Σ denom` pooled across prompts; (4)
**stratify by scope** (never pool L1 with L3; L3 carries hardest-query selection bias). None of
this is built now.

## Files

- **Add** `chinatravel/agent/nesy_verifier/repair_strategies/r3.py` — `R3AdaptiveScopeRepair(BaseRepairStrategy)`
  with `repair()` + `accept()` + helpers (localization, merge, prompt build), mirroring
  `r0.py`'s structure.
- **Edit** `chinatravel/agent/nesy_verifier/llm_modulo.py` (~line 371) — add
  `elif self.repair_strategy_name == "R3": strategy = R3AdaptiveScopeRepair()` and import it.
- **Add (optional, new constant)** `prompts/llm_modulo.py` — `R3_TARGETED_PROMPT`.
- **Ensure per-prompt self-contained logging** — R3 metadata rides in the existing per-query
  `cache/<method>_R3/problem_<id>_repair_history.json`; add the `uid` + `constraints` header so
  each file stands alone. (Written where `llm_modulo.py` already writes that history.)
- **Add** `tests/test_r3_adaptive_repair.py` — mock-LLM unit tests (no shared code touched).

**Explicitly NOT in this task (the separate matrix-build task):**
`chinatravel/agent/nesy_verifier/constraint_types.py` (constraint typing) and
`scripts/build_constraint_matrix.py` (typing + single-target filter + replay + num/denom +
stratification). This implementation only produces the per-prompt component logs they consume.

## Verification

1. **Unit (offline, mock LLM):**
   - Freeze enforcement: a mock LLM that rewrites a *frozen* activity → merged result keeps
     the current (locked) activity; only editable slots change.
   - Scope widening: feed a candidate that never reduces violations → assert `self._scope`
     advances L1→L2→L3 after 2 stuck rounds each.
   - Localization: failing timing constraint on day 2 activity 1 → target set is exactly that
     activity at L1; a global budget constraint → target set escalates to whole plan.
   - Log completeness (per step): metadata carries `scope_level`, `scope_fraction`,
     `changed_slots`, `editable_slots`, `targeted_constraints` (raw), `per_target_edits`.
   - Per-prompt self-containment: the written per-query record carries `uid` + `constraints`
     (the `hard_logic_py` index→dsl map) and a `steps` list, and resets between queries.
   - Run with `python -m unittest tests.test_r3_adaptive_repair -v` (unittest, not pytest).
2. **End-to-end (needs restored env + sandbox + API key):**

   ```bash
   python run_exp.py --agent LLM-modulo --repair_strategy R3 \
     --llm openai/gpt-4.1 --splits medium --index e20241028160845920703 \
     --refine_steps 4 --oracle_translation --lang zh
   ```

   Confirm `results/LLM-modulo_R3/<id>.json` is produced and the per-prompt
   `cache/LLM-modulo_R3/problem_<id>_repair_history.json` is self-contained (header + per-step
   `scope_level` / `targeted_constraints` / `per_target_edits`). Building `M` is a later task.
3. **No regression:** re-run the existing suite to confirm R3 didn't disturb shared code.

## Settled design decisions

**Verdict on the design walkthrough:** internally consistent — it correctly shows L1's limit
(a frozen attraction blocks the lunch fix), oscillation (fix budget ↔ break diet, flat count)
counting as stuck, the L2 ripple (a day rewrite drops a correct attraction), and replay-based
attribution. Decisions adopted:

| # | Decision | Choice | Why |
|---|---|---|---|
| D1 | Scope control | **Shared ladder** (one scope for the whole repair), **not** per-constraint rungs | Keeps "adaptive scope" a single, well-defined ablated variable; simpler to build/explain; preserves the R3↔R4 distinction (per-constraint minimal edits are R4's job); the matrix-cleanliness gain of per-constraint is recovered via replay (D6). **The one point of divergence from a per-constraint proposal — flagged for revisit.** |
| D2 | Day-slot membership | Hotel + inter-city transport are **trip-level**, frozen until L3 | Trip-wide, high-ripple; L2 already covers every day's activities. |
| D3 | Global constraints at L2 | Unlock **all days**; log **effective-scope fraction** | They can't localize; the fraction makes "budget L2 ≈ plan scope" visible. |
| D4 | Drop back after progress? | **No — ratchet** (scope only widens) | Avoids L1↔L2 looping and unpredictable step counts. |
| D5 | Stuck metric | **No improvement over best-so-far at the rung for 2 rounds** | Robust to oscillation (beat-last-round isn't). |
| D6 | Matrix attribution | **R3 only logs** raw `targeted_constraints` + `per_target_edits`; single-target filtering and disjoint-region replay happen in the **later** build task | The marginal per-target effect is what `M` wants; logging `per_target_edits` now is all R3 needs to enable it later. |
| D7 | Edit size | **R3 logs** `changed_slots` + `scope_fraction`; stratification / `EditCost` use is **later** | Bigger edits break more; logging the covariates now lets the later builder stratify L1/L2/L3. |
| D8 | L3 data | Analysis note for the **later** task: don't compare L3 vs L1 rates naively | L3 fires only on the hardest queries → selection bias. |
| D9 | Accept policy | **Always-accept** (unchanged) | Keeps R3 distinct from R2's rollback. |
| D10 | Logging granularity | **Per prompt**, self-contained (`uid` + constraint set + steps), fresh R3 state per query | Enables clean index-level per-prompt analysis with no typing; cross-prompt pooling is the later task. |

## Open decisions / risks

- **Widening trigger:** chosen *stuck-based* (climb a rung after 2 no-progress rounds) — the
  faithful reading of "adaptive". Alternative *fixed schedule* (rounds 1–2 at L1, 3–4 at L2,
  5+ at L3, regardless of progress) is simpler but widens blindly; one-line switch.
- **D1 divergence (flagged):** a **shared** scope ladder is chosen over per-constraint rungs.
  If the team wants cleaner per-constraint matrix rows at the cost of a more complex policy and
  a fuzzier "scope" variable, this is the decision to revisit first.
- **Accept policy:** chosen *always-accept* (keeps R3 distinct from R2's rollback). Alternative
  "accept only if not worse" is a one-line change if the team prefers.
- **Matrix sparsity (expected):** the single-target filter + R3's tendency to target several
  failing constraints at once means few `M`-eligible steps per R3 run. Mitigation: emit raw
  `num` / `denom` so low-support cells are visible, and pool R1's single-target steps (cleaner
  source) into the same builder when R1 lands.
- **Constraint typing is lossy** (a later-task concern): concept-function typing collapses e.g.
  all budget thresholds to one `budget` type; multi-function DSL snippets are ambiguous.
- **Localization is heuristic** — mitigated by adaptive widening; log when a constraint can't
  be localized so we can audit how often R3 falls back to whole-plan.
- **Index alignment** in merge breaks if the LLM reorders days/activities — the lock defends
  by keeping current on any shape mismatch; log such mismatches.
