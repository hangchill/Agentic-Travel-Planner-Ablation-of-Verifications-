# R3 (adaptive scope) on `subset_train` — results report

Run: `experiments/subset_train-r3` · 60 queries (20 easy / 20 medium / 20 human) · deepseek-chat, temperature 0, English sandbox · 6-step budget · git `e1d97b7`

## TL;DR

- **R3 almost never produces a fully valid plan.** 2/60 plans (3.3%) pass the repair loop's own verifier, and 0/60 pass the benchmark evaluator.
- **Personal constraints improve a little.** Queries with every personal constraint satisfied go from 29 to 35 (48% → 58%). Widening the edit scope does not help: the fix rate for targeted constraints falls from 19% at slot scope to 8% at day scope and 4% at plan scope.
- **Commonsense errors show no net change.** There are 300 commonsense errors before repair and 299 after. Repair fixes attraction, hotel and restaurant errors but adds inner-city transport errors, which go from 75 to 182.
- **About half the LLM calls change nothing.** 102 of 199 repair attempts returned a plan with zero changed slots, and those calls used about 51% of repair tokens.
- **The official regression matrix is almost empty.** It holds 1 regression across 255 eligible cells. The dependencies that do occur run commonsense → personal (room type, budget) and personal → commonsense (inner-city transport), and the current matrix definition does not count either direction.

No other strategy has been run on `subset_train` yet (there is only a 2-query R2 smoke test). This report is therefore a baseline sheet for R3. Section 7 lists what to compare once the R0, R1 and R2 runs exist.

---

## 1. Setup and query profile

The loop gives each query up to **5 personal-constraint attempts**, then **exactly one commonsense attempt**. If that attempt breaks a personal constraint, a personal recovery attempt can follow while budget remains (`shared_repair_loop.py:139-156`). A query whose personal constraints all pass at the start goes straight to the commonsense step and then stops. R3 widens the editable scope on a fixed schedule: slot for attempts 1–2, day for 3–4, whole plan from 5.

Origins come from `chinatravel/evaluation/splits/subset_origin.json`, not from the uid prefix: `e…` ids include both easy and medium queries, and `m…` and `t…` ids are easy.

| Query profile | Easy | Medium | Human | All |
|---|---|---|---|---|
| Mean trip days | 2.05 | 2.35 | 3.45 | 2.62 |
| Mean personal constraints / query | 5.2 | **8.15** | 4.35 | 5.9 |
| Personal all-pass at start | 8/20 | 8/20 | **13/20** | 29/60 |
| Commonsense errors / query at start | 4.35 | 3.95 | **6.70** | 5.00 |
| Main initial personal failures | day count (4), ticket count (4), hotel (4), budget (3), cuisine (3) | **budget (11 of 15)** | budget (3), must-visit attraction (2) | |

Each origin has a different profile. Medium queries have the most constraints, with hotel/room and transport-mode rules on top of budget. Human queries have few constraints but the most commonsense errors, most of them about accommodation. Easy queries fail on structural requirements: the number of days, including a particular hotel or cuisine, and ticket counts.

## 2. Headline metrics by origin

| Metric | Easy | Medium | Human | All |
|---|---|---|---|---|
| **Final pass (loop verifier)** | 0/20 | 1/20 | 1/20 | **2/60 (3.3%)** |
| Step-5 pass (before the last step) | 0/20 | 1/20 | 1/20 | 2/60 |
| Benchmark all-pass | 0 | 0 | 0 | **0** |
| Personal all-pass: start → step 5 → final | 8 → 10 → 10 | 8 → 12 → 11 | 13 → 14 → 14 | 29 → 36 → 35 |
| Personal constraint satisfaction (micro), start → final | 80.8% → 80.8% | 90.8% → 89.0%* | 79.3% → 85.1%* | 85.0% → 85.6% |
| Commonsense errors / query, start → final | 4.35 → **5.65** ▲ | 3.95 → 4.35 ▲ | 6.70 → **4.95** ▼ | 5.00 → 4.98 |
| Benchmark logical micro / macro | 86.5% / 50% | 92.6% / 55% | 92.0% / 75% | 90.7% / 60% |
| Benchmark schema pass | 75% | 30% | 15% | 40% |
| Mean attempts / query | 3.8 | 3.6 | 2.55 | 3.3 |
| Tokens / query, mean (median) | 142k (163k) | 140k (133k) | 99k (**43k**) | 127k (95k) |
| Wall time / query | 118 s | 121 s | 120 s | 120 s |

\* The micro rate counts "unknown" results as not satisfied. Medium drops because one plan became untranslatable during repair (7 constraints went to unknown). Human rises partly because one plan that started untranslatable became evaluable.

**By origin:**

- **Easy did worst after repair.** Only 2 of the 12 queries with a personal failure reached all-pass. Day-count (4) and "must include X" failures were never fixed. Personal-phase edits introduced 95 new commonsense errors, 65 of them inner-city transport errors, so commonsense errors per query *rose* by 30%. The "easy" label describes the query, not how easy it is to repair.
- **Medium has the best personal-phase success and the worst side effects.** 5 of 12 queries reached personal all-pass, the best rate of any origin. But the commonsense step then broke a personal constraint in 6 of 20 medium queries, and 2 of the 5 queries that had reached all-pass lost it again by the end. Medium queries carry 38 of the 47 hotel/room constraints in the sample, and those constraints are what the commonsense step breaks.
- **Human was cheapest, and the commonsense step helped most there.** 13 of 20 queries skip the personal phase and get only the single commonsense attempt (median 43k tokens). That step works best on human queries: 134 → 99 errors, with the hotel errors largely fixed. The personal phase was close to useless: 1 fix in 31 attempts. Two human plans had *every* personal constraint "unknown" and spent 10 attempts with nothing to target.

## 3. Effectiveness in detail

### 3.1 Personal phase: widening the scope did not help

139 personal attempts targeted 165 failing-constraint instances. They produced 20 fixes and 1 personal regression.

| Scope rung | Attempts | Targeted fix rate | Attempts with zero changed slots | New commonsense errors introduced |
|---|---|---|---|---|
| slot (attempts 1–2) | 59 | **14/74 = 19%** | 29 (49%) | 113 |
| day (3–4) | 54 | 5/63 = 8% | 35 (65%) | 37 |
| plan (5+) | 26 | 1/28 = 4% | **21 (81%)** | 10 |

At temperature 0, giving the model more freedom mostly made it return the same plan. Almost all fixes come in the first two attempts: queries that reached all-pass did so after 1.75 attempts on average. Even so, 25 of 60 queries used all 5 personal attempts.

**Which constraint families get fixed.** The table counts constraints failing at the start and how many pass at the end.

| Family | Failed at start | Fixed by end |
|---|---|---|
| party_resources (ticket counts) | 5 | **5** |
| monetary_budget | 17 | 5 |
| transport_mode | 2 | 1 |
| trip_specification (day count) | 5 | **0** |
| attraction (must visit X) | 5 | 0 |
| accommodation (must stay at X / room type) | 5 | 0 |
| dining (must eat cuisine X) | 3 | 0 |

R3 fixes constraints that only need a value changed inside existing slots, such as ticket counts and sometimes cost. It never fixed a constraint that needs a day added or removed or a new entity inserted. Those need plan-level edits, and at plan scope the model barely edits (81% of plan-scope attempts change nothing).

### 3.2 Commonsense step: errors are swapped rather than removed

Each query gets one commonsense attempt (60 in total). From the official `pass_rates.csv`: 333 errors targeted, **164 fixed (49%), 122 new**, and 2 queries ended with zero commonsense errors. When this step runs at attempt 1–2 (slot scope) it clears everything in 2 of 34 queries. When it runs at attempt 5–6 (plan scope) it clears everything in 0 of 24.

Commonsense errors by category, start → end of repair (all 60 queries):

| Category | Start | End | |
|---|---|---|---|
| Accommodation (room type, hotel cost, missing hotel) | 79 | 34 | fixed well |
| Attraction (closed hours, repeats, invalid) | 43 | 11 | fixed well |
| Restaurant (meal times, cost, repeats) | 68 | 41 | partly |
| Cross-city transport | 32 | 26 | rarely fixed |
| **Inner-city transport (cost, route origin, availability)** | **75** | **182** | **made worse** |

By error type, timing errors (opening hours, meal windows) are fixed most often: 73 fixed, 9 new. Cost/price errors are the ones the step creates: 86 new, 47 fixed. Most new inner-city errors are `cost = price × people` mismatches or a leg whose origin no longer matches the previous activity. That pattern points to the cause: changing a POI or a ticket count invalidates the transport legs on either side of it, and the LLM does not recompute them.

The commonsense step also **broke a personal constraint in 8 queries** (2 easy, 6 medium, 0 human), and 5 of those recovered in a later attempt.

### 3.3 Technical failures

- Plans with verifier or translation errors went from 7 at the start to **12 at the end** (3 easy, 6 medium, 3 human). The two recurring crashes are `collect_transport_error: string indices must be integers` and `collect_time_error: 'position'`.
- Two plans became untranslatable *during* repair, which turned all of their personal results into "unknown".
- An "unknown" result traps the loop. The scheduler keeps choosing the personal phase because the constraint is not `True`, but there is nothing `False` to target. This produced 17 attempts with no target across 3 queries.

## 4. Efficiency

- **Tokens are almost all prompt.** Per query, prompt tokens average 121.5k against 5.5k completion tokens. Each attempt costs about 38k tokens whatever the origin, because the plan and tool context are re-sent every time.
- **Attempts that change nothing:** 102 of 199 (easy 42/76, medium 33/72, human 27/51). They used about **51% of all repair tokens**.
- **Rounds are bimodal.** 27 queries stop after 1 attempt and 25 hit the 6-step cap, so a mean of 3.3 hides two different groups. Report the distribution or the median when comparing strategies.
- The human set is cheapest only because the schedule sends most human queries straight to the single commonsense step. R3 is not more efficient on human queries in any other sense.

## 5. The repair verifier and the benchmark evaluator check different things

- **Chronological order:** 55 of 60 final plans fail the benchmark's "Does not follow Chronological Order" check. Both plans that pass the loop verifier also fail it. The benchmark checks that activities do not overlap and that transport departs after the previous activity ends (`symbol_verification/commonsense_constraint.py:1097-1117`). The repair loop's verifier (`collect_time_error` in `verifier/commonsense_constraint_nl.py`) only checks that an activity starts after its own transport arrives, so the loop is never asked to fix overlaps.
- **Schema (40% pass):** 32 of the 36 failures are inner-city transport legs missing a `price` field, which the loop verifier also does not check. The schema pass rate did rise during repair, from 28% at the start.
- The gap is the same for every strategy, so **comparisons between strategies stay fair**. Absolute benchmark pass rates will stay near 0 for every method until the gap is closed. Report loop-verifier and benchmark numbers separately.

## 6. The constraint regression matrix

### 6.1 The official matrix (`regression_matrix/`) is almost empty

Rows are the family of the single failing constraint an attempt targeted. Columns are the family that regressed (passed before, failed after). Families with no support are omitted.

| Source ↓ / dest → | trip_spec | party_res | budget | accommodation | dining | transport_mode | attempts |
|---|---|---|---|---|---|---|---|
| monetary_budget | 0/43 | 0/43 | — | **1/29 (3.4%)** | 0/19 | 0/15 | 43 |
| attraction | 0/14 | 0/14 | 0/9 | 0/9 | — | 0/9 | 14 |
| dining | 0/9 | 0/9 | — | — | — | — | 9 |
| accommodation | 0/8 | 0/8 | 0/2 | — | 0/1 | 0/1 | 8 |
| trip_specification | — | 0/5 | — | — | 0/5 | — | 5 |
| party_resources | 0/1 | — | — | — | — | — | 1 |
| transport_mode | 0/1 | 0/1 | — | — | — | — | 1 |

There is **1 regression in 255 eligible cells.** The `travel_extent` and `schedule_order` rows and columns are empty because no query in the sample has a constraint of either type.

Five things make the matrix this sparse. None of them shows that the constraints are independent:

1. **Most targeted attempts don't edit the plan.** 61% of personal attempts change zero slots, and an unchanged plan cannot regress anything.
2. **Most eligible cells point at constraints that never move.** 156 of 255 eligible cells (61%) have trip_specification (day/people count) or party_resources (ticket count) as the destination. Repairs essentially never change these.
3. **The eligibility rules drop most attempts.** Of 199 attempts, 82 have exactly one target and count as a source. The other 117 are excluded: 40 had several targets, and 77 had none (all 60 commonsense steps plus 17 attempts trapped by "unknown" results).
4. **The budget row dominates.** It holds 149 of the 255 eligible cells (58%).
5. **The step that causes regressions is excluded by definition.** 8 of the 9 personal regressions in this run happen at the commonsense step, which has no personal target (next section).

### 6.2 A fuller view: every attempt, including the commonsense step

I counted every personal regression (True → False) across all 199 attempts. The source is the targeted family, or "commonsense step" for that attempt; a destination counts only if some constraint in that family passed before the attempt.

| Source | Regressions in accommodation | Regressions in budget | All other families |
|---|---|---|---|
| Commonsense step | **5/22 (23%)** | **3/20 (15%)** | 0 |
| Personal phase (any target) | 1 (budget → accommodation) | 0 | 0 |

The mechanisms are easy to read off the cases:

- To fix "room_type must be an integer", the model rewrote the room type and broke the user's `room_type == 2` constraint.
- To fix "attraction closed at visit time", the model swapped in a different attraction and pushed the trip over the 1600 RMB budget.

Both are commonsense → personal dependencies. All 8 occur in easy or medium queries, and 6 of them in medium, where the hotel/room constraints are.

### 6.3 Personal → commonsense: the largest dependency, and the matrix doesn't count it

The personal phase introduced **160 new commonsense errors** while fixing 117. Grouped by the family the attempt targeted:

| Targeted family | Attempts | New commonsense errors per attempt | Of which inner-city |
|---|---|---|---|
| dining | 15 | **4.3** | 44 |
| party_resources | 5 | **4.0** | 20 |
| trip_specification | 25 | 1.0 | 19 |
| monetary_budget | 67 | 1.0 | 31 |
| accommodation | 22 | 1.0 | 11 (+10 accommodation) |
| transport_mode | 6 | 0.2 | 1 |
| attraction | 25 | 0.2 | 4 |

(An attempt with several targets is counted under each of its families, so the rows overlap.)

The ordering makes sense. Changing ticket counts (party_resources) changes every transport cost through `cost = price × people`. Swapping restaurants (dining) moves positions and breaks the transport legs around them. This interaction is the main reason R3 ends with as many commonsense errors as it started with, and none of it appears in `M`.

### 6.4 What this means for M and R4

As currently defined (personal × personal, single explicit target), the R3 matrix is close to all zeros and would give R4 almost no guidance. Some changes worth discussing as a team; they would change `matrix_definition_version`:

1. **Add commonsense categories as destinations**, at minimum inner-city transport, accommodation and restaurant. CLAUDE.md already names the commonsense taxonomy as an intended axis.
2. **Count the commonsense step as a source** (for example `commonsense:<category>`) instead of dropping attempts with no personal target. This is where the commonsense → personal regressions are.
3. **Use attempts that changed at least one slot as the denominator**, so "never tried" is not counted as "tried and broke nothing".
4. **Always show support next to each rate, with a minimum support** (for example 10 or more) before a cell is used. With 60 queries, most cells fall below that.

## 7. Comparing strategies once the R0, R1 and R2 runs exist

These are the R3 reference values to put each other strategy against:

| Metric | R3 value | Why it matters for the comparison |
|---|---|---|
| Final pass, loop verifier / benchmark | 3.3% / 0% | Headline result, though near the floor for every method (§5) |
| Personal all-pass, final (change from start) | 58.3% (+10 pts) | Main effectiveness signal |
| Commonsense errors / query, final (change) | 4.98 (−0.02) | Shows whether a method removes errors or only moves them |
| Inner-city transport errors, final | 182 (start: 75) | The largest regression channel |
| Commonsense step: fixed / new | 164 / 122 | Quality of the commonsense step |
| Queries where the commonsense step broke a personal constraint | 8 | R2's rollback should push this to 0 |
| Attempts with zero changed slots | 51% | R1 stops on an unchanged plan; R0 rewrites everything |
| Tokens / query, mean and median | 127k / 95k | Efficiency (H2) |
| Plans with technical errors at the end | 12 | Robustness |

What this R3 run suggests to look for in the others:

- **R0** may fix structural failures (day count, must-include) that R3 never fixes, but should show more regressions.
- **R2** should remove the 8 commonsense-step personal regressions. The open question is whether rollback then stalls on commonsense errors.
- **R1** should save most of the tokens spent on unchanged plans.

**Comparison rules:**

- **Check initial plans first.** Confirm `initial_plan_hash` matches across runs so every strategy starts from the same plans.
- **Compare the same query under each strategy (paired), not overall rates.** Use McNemar or a sign test on pass/fail per query. With 20 queries per origin, one query is 5 percentage points, so a difference of 1–2 queries within an origin is noise.

## 8. Caveats

- **Small sample:** n = 20 per origin, temperature 0, one seed.
- **Approximate category breakdowns:** commonsense categories come from my grouping of verifier message text, and "fixed"/"new" from exact message comparison. That gives 154 fixed / 116 new against the official 164 / 122 in `pass_rates.csv`. Use the official totals and treat category splits as approximate.
- **Unclassified constraints:** 5 constraints could not be mapped to a family (unmapped or ambiguous) and are left out of the family tables.
- **Local edits to the split file:** `subset_origin.json` has uncommitted local changes. The train split's 20/20/20 composition matches it.
