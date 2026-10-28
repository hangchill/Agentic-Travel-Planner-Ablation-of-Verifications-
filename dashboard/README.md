# Repair-analysis dashboard

A local, read-only Streamlit frontend. No models, APIs, benchmark evaluators,
experiment writers or matrix builders are called. No source artifacts are modified.
See [DATA_AUDIT.md](DATA_AUDIT.md) for the audited inventory, precise definitions,
TEST/analyzer disagreements and metric availability.

## Install and launch

From the repository root, use the project Python environment (Python 3.12+):

```sh
python -m pip install -r requirements-dashboard.txt
streamlit run dashboard/app.py
```

The local Streamlit configuration binds to 127.0.0.1, disables usage telemetry and
file watchers; use Refresh local data after updating source files.

Use `python -m streamlit run dashboard/app.py` if the Streamlit command is not on
PATH. Install requirements in the same environment that launches Streamlit.

## Data discovery and final-run workflow

The dashboard discovers immediate `experiments/*/run_manifest.json` files, regardless
of the directory name. `final_test-r0`, `subset_test-r0`, and arbitrary descriptive
names work when manifests declare TRAIN/TEST, exact strategies R0–R4, a nonempty
unique query population and persisted attempts/query/summary artifacts. Invalid
or incomplete manifests are excluded; nested archive directories are not scanned.
Multiple valid runs remain individually selectable. No latest run is silently chosen.

Preferred generated diagnostics layout:

```text
results/analysis/repair_strategies/
  train/R0/ ... train/R3/
  test/R0/  ... test/R4/
test_result_analysis/
  README.md
  R0/ ... R4/
```

The loader prefers `<partition>/<strategy>` and falls back to legacy
`<strategy>` only when source path, run ID and recorded attempt checksum match.
There is no migration/copy requirement: existing legacy outputs continue to work.
Generating final TEST diagnostics in `test/` leaves TRAIN outputs intact.
Common TEST reporting always comes from the existing team's table builder;
the dashboard never runs evaluators, scoring or subprocesses.

After experiments finish, run the following from the repository root. These
commands assume final TEST directories are named `experiments/final_test-r0`
through `final_test-r4`; substitute actual run paths when different. This is
upstream run selection, not frontend configuration or registration.

1. Generate final-accepted benchmark exports (unless already completed upstream):

```sh
for strategy in r0 r1 r2 r3 r4
do
  python scripts/result_analysis/evaluate_repair_run.py \
    --run-dir "experiments/final_test-$strategy"
done
```

2. Regenerate all available common TEST tables **together**, using exact labels:

```sh
python scripts/result_analysis/build_test_result_tables.py \
  --run R0=experiments/final_test-r0 \
  --run R1=experiments/final_test-r1 \
  --run R2=experiments/final_test-r2 \
  --run R3=experiments/final_test-r3 \
  --run R4=experiments/final_test-r4 \
  --output-dir test_result_analysis
```

The builder's default `--origin` must cover every final UID; supply the appropriate
origin JSON if the population changes. Missing strategies should be omitted from
the command until their runs exist. Include every available reporting strategy in
each invocation: a partial invocation replaces the combined README with notes for
only its supplied runs. Existing CSVs for omitted runs then fail binding and show
Unavailable. The dashboard explicitly explains this and does not bypass the check.

3. Preserve/regenerate TRAIN diagnostics separately, when needed:

```sh
python scripts/analyze_repair_strategies.py \
  --run R0=experiments/subset_train-r0 \
  --run R1=experiments/subset_train-r1 \
  --run R2=experiments/subset_train-r2 \
  --run R3=experiments/subset_train-r3-new \
  --output-dir results/analysis/repair_strategies/train
```

4. Write final TEST diagnostics into their separate partition:

```sh
python scripts/analyze_repair_strategies.py \
  --run R0=experiments/final_test-r0 \
  --run R1=experiments/final_test-r1 \
  --run R2=experiments/final_test-r2 \
  --run R3=experiments/final_test-r3 \
  --run R4=experiments/final_test-r4 \
  --output-dir results/analysis/repair_strategies/test
```

5. Click **Refresh local data** or restart `streamlit run dashboard/app.py`. Clear
old filters and select the intended final run if multiple runs exist. Availability,
query populations, observed rounds, support bounds and numerical displays reload
from files. No dashboard edits, manual strategy registration or copying CSV/JSON
into dashboard/ are required. Refresh remains available even for a missing selected
run or an empty inventory. The commands above are instructions; implementation and
validation do not regenerate existing experiment or reporting artifacts.

## Provenance and freshness

Overview displays dynamic TRAIN/TEST availability, reporting/diagnostic availability
and query counts for each R0–R4 strategy, plus individual source runs. Generated
diagnostics availability is distinct from raw proposal diagnostics that can be
computed through the existing shared metric helper.

Overview and TEST set show the selected source path/run ID, generated output
paths, manifest query population/count and generation timestamps when recorded.
Timestamps are Unavailable for the TEST builder, which does not emit generation
metadata; filesystem modification time is not presented as a generation timestamp.
Recorded analysis source checksums are verified for the files listed. Without
checksum evidence the UI explicitly says:

> Source freshness cannot be cryptographically verified.

A matching run ID/population establishes binding, not freshness. The TEST builder
has no checksum manifest, so regenerate its tables after source changes even when
identities remain the same. Artifact publication should finish before refreshing.

## Pages and filters

The top navigation uses this exact order:

1. **Overview**: TRAIN/TEST inventory, run coverage and provenance.
2. **Query Explorer**: local partition (TEST default), strategy, query and trajectory filters;
   candidate/accepted states, final itinerary and separate post-hoc selection.
3. **TRAIN set**: TRAIN R0–R3 development matrices, support, relationship filters and downloads.
4. **TEST set**: TEST-only Tables 1–4, with existing local comparison and round filters.
5. **Ablations & Comparisons**: generated TEST pairwise results, validity checks, mechanism evidence,
   difficulty filters and reproducibility. See [ABLATION_COMPARISONS.md](ABLATION_COMPARISONS.md).
6. **Strategy-Specific**: TEST strategy diagnostics, including localisation, protection,
   widening, matrix guidance, guards and trial selection.
7. **Examples**: four canonical mechanism sections with automatic source binding,
   alternative qualifying selections and Markdown exports. These illustrate mechanisms,
   not aggregate evidence. See [EXAMPLES_REPORTING.md](EXAMPLES_REPORTING.md).

All analytical filters are local to their page. TEST set binds TEST reporting
regardless of selections elsewhere; TRAIN set binds TRAIN R0–R3 evidence.
Query Explorer retains initial/final endpoints while filtering expanded rounds.
Examples searches complete independent trajectories using its canonical criteria.
Saved aggregate matrices use local strategy/perspective/family/support controls;
proposal filters never rebuild them. PC family and TEST failure kind remain
different taxonomies.

## Derivation and missing-data contract

All new metric derivations live in `metrics.py`:

- Filtered TEST tables call the original table functions over saved per-query
  values; complete unfiltered tables are read verbatim. No scoring is run.
- Additional percentages divide saved query counts by cohort N. CS shares divide
  saved passed counts by saved total checks. >85% is strict.
- Extra process summaries use nonmissing mean/median with valid N. Calls sum only
  complete persisted counters. Logged exhaustion uses the stop reason, even for
  early stops. No-progress requires an explicit marker.
- Proposal diagnostics reuse generated metrics if provenance matches; otherwise
  call shared `compute_attempt_metrics`, not an independent implementation.
- Round changed classification calls the team's `round_data` on history prefixes.
  Accepted states advance only for accepted rounds. Mean accepted PC rates use
  True/(True+False), labelled as loop diagnostics. CS rounds show message counts
  and message-set differences, not benchmark check fixes. There is no forward fill.
- R1 localisation success requires logged editable slots; explicit `localiz`
  failure reasons are counted. Missing successes stay unavailable.
- Accepted PC event totals aggregate the existing shared accepted metrics across displayed proposals, with means and valid N. They count repeated events and are not benchmark endpoint fixes. Zero is assigned only to proven zero-round queries.
- R2 harmful means a candidate regressed an explicitly protected PC. The funnel
  distinguishes rejected and accepted candidates; PC preservation is separate from raw plan preservation. The additional verified rollback table compares each rejected round's persisted accepted_plan_after with the preceding accepted raw plan. Missing plan evidence stays unavailable.
- R3 reaches/maximum/adjacent scope transitions use logged scope order; successes
  mean targeted PC fixes. No failure-triggered widening is inferred.
- R4 proposal guidance: supported if any logged cell has support >0; unsupported
  if relationships exist but none has positive support; otherwise no logged
  relationship. Mixed proposals remain inspectable in the cell table. Structural
  guard failures use `proposal_rejected_reason`, distinct from accepted=False.
- Pooled matrices add already saved counts/support, then divide only positive
  support; no event classification or matrix construction. Coverage counts unique
  off-diagonal PC-family cells, excluding commonsense source rows.
- Candidate cascades require a targeted fix plus a new PC violation. R2 candidates
  require harmful rejection and verified prior-plan equality. R3 candidates require an earlier slot target miss or explicit no-progress before a
  later day/plan target fix. R4 guidance candidates require supported advice and
  a repaired post-hoc selection; limitations include missing advice/guards/no-op/
  retained initial plan. These are descriptive search criteria.

Missing values display Unavailable (including styled table cells), never zero. CSV exports retain empty fields for missing numeric values. Generated
analysis binds by provenance path/run ID and attempt checksum. TEST tables bind
by generated README source path/run ID, all required reporting files and exact
UID/strategy population. The team TEST
builder currently emits no checksum manifest, so same-identity in-place artifact
changes cannot be fully detected; regenerate tables after changing source runs.
CSV/JSON/JSONL and normalized attempts/checkpoint bundles are cached with file
mtime/size signatures. “Refresh local data” clears caches.

TRAIN means development/matrix construction; TEST means held-out evaluation.
Mixed partitions produce the requested warning. Comparison requires equal TEST
partition/population/model/settings/budget/language/initial-plan hashes and known
metadata; seed/implementation differences are flagged. Existing runs do not meet
all checks, so the controlled comparison stays disabled. Merged team CSVs do not
bypass the safeguards. Post-hoc R4 selections never replace last-accepted TEST
outcomes.

## Validation

```sh
python -m unittest discover -s dashboard/tests -p 'test_*.py'
python -m unittest discover -s tests -p 'test_analyze_repair_strategies.py'
git diff --check
```

The dashboard suite checks discovery, partition identity, provenance, parity of
all four team summary functions with fixtures generated by the original team helpers, missing costs,
thresholds, zero-support distinction, localisation, protection, scopes, guidance,
trajectory acceptance, candidate filters, comparison gating, and Streamlit
AppTest rendering using isolated synthetic persisted artifacts. No network is needed.

Remaining constraints: R0–R4 are the supported strategy schema; one common reporting
set per strategy and one diagnostic set per partition/strategy can be bound at a
time. Keep separate source runs and select the one whose generated provenance
matches. Upstream schemas and the team's existing evaluator/metric definitions
still apply (including its current budget-related reporting conventions); dynamic
round controls do not redefine those metrics. DATA_AUDIT.md records the original
audit snapshot, not a permanent claim about current availability.

## Table-first TEST PC reporting

The PC tab compares available strategies side by side with difficulty columns,
failure-kind filters, accepted-loop round tables and a supplementary comparison
chart. See [PC_REPORTING.md](PC_REPORTING.md) for every source-row mapping,
Initial/Final semantics, denominators and unavailable metrics. The PC tab discovers available TEST reporting strategies independently of other pages.

## Table-first TEST CS reporting

The CS tab now mirrors the PC structure using shared cohort, control, pivot and
chart helpers. It has its own difficulty/strategy filters and downloads, literal
failure-label attribution, accepted-loop message diagnostics and round comparison.
See [CS_REPORTING.md](CS_REPORTING.md) for every source mapping, exception and
denominator policy, unsupported check-level round metrics and comparison guards.

## Table-first TEST process reporting

Repair Process / Efficiency now shares the PC/CS cross-strategy structure, with
exact Table 3 cells, token-coverage warnings, outcome breakdown, separate token/
time charts, round diagnostics and secondary counters. See
[PROCESS_REPORTING.md](PROCESS_REPORTING.md) for exact row mappings, denominators,
missing-token semantics, changed-round signs, cache limitations and failure flags.

## Table-first ChinaTravel Evaluation

The fourth TEST tab provides final benchmark Difficulty × Strategy reporting,
metric bars, strategy/difficulty profiles and saved query-level results, without
round analysis. See [EVALUATION_REPORTING.md](EVALUATION_REPORTING.md) for exact
evaluator definitions, raw exception-column footnote, percentage scaling, missing
results and the distinction between Commonsense macro and three-way All-pass.

### Page navigation and partition policy

The persistent top navigation contains only the seven pages. There is no global
run, partition or analytical filter state; the sidebar retains only Refresh local data.

| Page | Partition | Local controls |
| --- | --- | --- |
| Overview | TRAIN and TEST inventory | Run provenance |
| Query Explorer | TEST default; local TRAIN option | Partition, strategy/run, difficulty, query UID, phase/round/family/outcome |
| TRAIN set | TRAIN R0–R3 | Source strategies, matrix perspective, repaired/regressed family, minimum support, relationship sort/top N |
| TEST set | TEST reporting only | Existing independent Table 1–4 difficulty, strategies, metric/failure-family and round comparison controls |
| Ablations & Comparisons | TEST only | Comparison, difficulty, supplementary metric; generated validity and cohort safeguards |
| Strategy-Specific | TEST only | Strategy/run, difficulty where reporting exists, proposal phase/round/family/outcome/UID |
| Examples | TRAIN cascade; TEST R2/R3/R4 | Qualifying example selector per canonical section; Markdown exports |

Missing TEST runs remain unavailable; TRAIN is never substituted. Changing pages
cannot carry a partition or proposal filter into benchmark reporting. The reporting
pages use the same saved tables and metric helpers as before; removing proposal
filters restores the full benchmark cohort by default. Restart Streamlit after
updating source (file watching is disabled in the repository configuration).

## Query Explorer walkthrough

Query Explorer retains its local TEST-default partition, strategy/run, difficulty,
query UID, phase/round/family/outcome and independent-trial controls. The summary
shows the original saved request where available, initial/final accepted PC and
loop-CS results, and run/trial identity. Benchmark reporting remains separate.

The compact Initial/Attempt navigation wraps after seven buttons and includes
Previous/Next. Attempt labels use persisted step IDs; navigation uses independent
record identities, so nonconsecutive or missing step IDs are not renumbered as
recorded rounds. Filters restrict selectable attempts, while initial/final states
and the full constraint history remain available. Selecting another query or trial
uses independent navigation state.

Before, Candidate and Accepted after each have verification details and activity
cards. Rejected candidates remain visible; accepted state advances only according
to the recorded loop decision. Missing raw plans remain unavailable rather than
being replaced with translated plans, last candidates or selected exports. The
final accepted loop plan and R4 post-hoc selected outcome have separate sections.

`components/itinerary_cards.py` imports only the pure `activity_title`,
`format_money` and `transport_description` functions from `frontend.presentation`.
No replay data, narration, curated issue IDs, live planner, history discovery or
storage helpers are imported. Cards support multiple days, dict/list transfers,
recorded details and escaped text. Longer itineraries use collapsed day sections.

The supplementary raw-plan diff matches unique recorded activity/slot IDs first,
then unique unchanged place/route identities within explicitly identified days
(or a single unambiguous day). It never pairs activities by list position.
Insertions/deletions with stable IDs are labelled explicitly; changed identities,
duplicates and other ambiguous activities remain unmatched. Reordering is shown
as an order change. Partial alignment has no invented changed-activity count.
This display does not redefine the team's translated-plan changed metric.

Explicit zero-based `editable_slots` records can focus the Before itinerary.
These are editable-location mappings, not inferred violation locations; highlights
are never transferred to a possibly reordered candidate.

PC history shows saved True/False/Unknown candidate vectors and the final accepted
state. CS history shows saved messages/counts, without invented persistent check
identities. Message-set introductions/removals are loop diagnostics, not benchmark
check fixes. R2 shows protected PCs, candidate regressions, rejection and recorded
raw-plan retention evidence. R3 shows actual scope, scheduled widening and logged
escalation. R4 separates relationship evidence/support, guard status, candidate
outcome, loop acceptance and post-hoc selection; logged guidance does not prove
that the model followed it.

Process details expose only saved counters. Raw evidence is collapsed and
credential/environment fields are redacted. Downloads include the current
attempt, state comparison, field diff, checkpoint and final itinerary; existing
itinerary and benchmark CSV downloads remain available. Provenance uses the
existing binding/freshness infrastructure and adds the selected checkpoint path.
Generation timestamps and freshness limitations are labelled when unavailable.

See `QUERY_EXPLORER_MERGE.md` for implementation and validation details.
