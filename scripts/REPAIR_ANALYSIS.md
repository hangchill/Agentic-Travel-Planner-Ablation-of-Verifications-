# Offline repair-strategy analysis

`scripts/analyze_repair_strategies.py` analyzes any explicitly supplied subset of
R0/R1/R2/R3/R4 with a common loader, shared `compute_attempt_metrics()` definitions,
and separate mechanism hooks. It never runs experiments, calls providers,
executes a verifier, evaluates benchmarks, or rebuilds matrices. R3P is excluded.

From repository root, with Python 3.12 and the project's environment activated:

```sh
python -m pip install -r requirements-analysis.txt
python scripts/analyze_repair_strategies.py \
  --run R0=experiments/subset_train-r0 \
  --run R1=experiments/subset_train-r1 \
  --run R2=experiments/subset_train-r2 \
  --run R3=experiments/subset_train-r3-new \
  --run R4=experiments/subset_test-r4 \
  --output-dir results/analysis/repair_strategies
```

Each `--run` is optional individually, but at least one is required. For example:

```sh
python scripts/analyze_repair_strategies.py --run R0=experiments/subset_train-r0
python scripts/analyze_repair_strategies.py --run R1=experiments/subset_train-r1
python scripts/analyze_repair_strategies.py --run R2=experiments/subset_train-r2
python scripts/analyze_repair_strategies.py --run R3=experiments/subset_train-r3-new
python scripts/analyze_repair_strategies.py --run R4=experiments/subset_test-r4
```

Use `--no-figures` for tables/reports without matplotlib. No random selection is
used. Strategy arguments and proposals are sorted; duplicate strategy labels or
query/step identities are rejected. Supplied labels differing from persisted
identity produce explicit warnings, and mixed-strategy streams are rejected.
R4 independent matrix-trial labels retain separate accepted trajectories; they
are never concatenated as a single sequence of accepted states.
Output and input trees must be disjoint. Numerical CSVs are deterministic;
provenance and report timestamps intentionally change. All source files are
SHA-256 checked before and after. Analysis outputs are Git-ignored by `results/`.
Do not point different runs at an existing output directory unless replacing its
analysis is intended; use a separate output directory when comparing reruns.

## Inputs and evidence

The generic adapter reads optional `run_manifest.json`, `attempts.jsonl`,
`summaries.csv`, `queries/*/*.json`, `benchmark_eval/*/benchmark_summary.json`, and
`regression_matrix/`. If JSONL is absent, persisted checkpoint repair records can
supply proposals. No proposals are reconstructed from summary counts. Without a
manifest population, the sorted union of query evidence is explicitly labelled
as inferred. Evidence outside a declared population is warned about and excluded.

- Direct: candidate transitions, targets, phases/scopes, protection, decisions,
  usage/time and footprints, wherever persisted.
- Reconstructable: initial/last observed accepted personal vectors and phase/scope
  sequences. Rejecting a candidate keeps the previous accepted vector.
- Unavailable: missing terminal status, unlogged events, unknown-query outcomes,
  absent benchmark scores and initialization usage. A checkpoint without an
  explicit attempt count/history does not prove zero attempts.

Satisfaction is True/(True+False); UNKNOWN/None is excluded. All-UNKNOWN rate is
undefined. UNKNOWN prevents all-personal-pass and never creates a fix or a
regression. Candidate events remain visible even after R2 rollback; accepted
metrics exclude rejected candidate changes. Missing phases stay unknown.

Unchanged requires the recorded no-progress marker; footprint zero is not enough.
A final proposal is only the end of the available stream unless a persisted stop
exists. Known token sums with incomplete coverage are partial sums, not complete
run totals; `total_tokens_delta_complete_total` is blank when any delta is missing.
All common efficiency metrics cover repair only, excluding initialization.
Per-query footprint rates require complete proposal coverage; a separately named
measured-subset rate retains partial evidence. Every summary statistic has valid N.

Saved matrix rate/support/count triplets (including scopes and perspectives) are
read without changing eligibility. Zero support must have missing rate; positive
support with no regressions has rate 0.0. Triplets reconcile with saved contribution
records and long tables if present. Missing triplets stay unavailable; legacy
rate-only files are not turned into invented supports. The v2.1
`commonsense_repair` source is separate from personal-target rows. Cell supports
are opportunities, not independent queries; support ≥5 is only a display filter.

## Outputs

```text
<output>/<strategy>/
  attempt_level.csv
  query_level.csv
  overall_summary.csv
  phase_summary.csv
  failure_modes.csv
  failure_summary.csv
  matrix_summary.csv
  evidence_availability.csv
  footprint_bins.csv
  footprint_associations.csv
  mechanism_summary.csv
  <strategy-hook tables>.csv
  existing_benchmark_summaries.json
  provenance.json
  case_studies.json
  case_studies.md
  ANALYSIS.md
  figures/*.png, *.svg
<output>/cross_strategy/       # created only for multi-strategy invocations
  comparability_audit.csv
  overall_summary.csv
  ANALYSIS.md
```

R0 hook: global scope, broad footprints, collateral regressions, target counts.
R1 hook: explicit localization reasons, no-ops, successful one-slot fixes.
R2 hook: protection/rollback, rejected target fixes, blocked harmful candidates,
plan hashes/equality, subsequent continuation, and candidate/accepted matrices.
R3 hook: persisted scope transitions/outcomes and escalation reasons. Current R3
uses fixed attempt-based widening, including commonsense calls; it must not be
called failure-triggered escalation. Hooks do not change shared metrics.

Failure flags overlap. Metadata reason rates use all proposals as denominator;
unavailable schema/protection evidence remains missing. Case studies use fixed
criteria, then UID and step, without random sampling. Correlations are descriptive
Spearman rank associations without significance tests or independence claims.
Cross-strategy synthesis audits populations/query hashes, model/settings, budget,
implementation hashes and initial plans where observable. Verifier/scheduler
are not independently hashed; no equality is inferred from missing evidence.

## Run selection and existing baseline

The requested `scripts/analyze_r0_r1_individual.py` and its individual outputs do
not exist in this checkout. There were no references to migrate or wrapper to
retain. The available reproducible baseline is the ignored
`results/analysis/r0_r1_final/analyze.py` and its tables. The generic implementation
preserves those R0/R1 numerical definitions; it does not alter that baseline.

Candidate audit (local manifests/artifacts inspected 2026-10-26):

| Run | Split / declared queries | Proposals / represented queries | Evidence | Selection |
| --- | --- | --- | --- | --- |
| experiments/subset_train-r2 | subset_train / 60 | 332 / 57 | 60 strategy + 60 initial checkpoints, summaries, benchmark, matrices | strongest full TRAIN R2 candidate; analyzed |
| experiments/smoke-r2-train2 | subset_train / 2 | 12 / 2 | checkpoints, no summary/benchmark/matrix | smoke only |
| experiments/pilot5-r2-v1 | pilot5 / 5 | 11 / 5 | checkpoints, summary/benchmark/matrix; budget 5 | pilot, not full TRAIN |
| experiments/subset_train-r3 | subset_train / 60 | 199 / 60 | checkpoints, summary/benchmark/matrix, older hash | older plausible TRAIN run; not selected |
| experiments/subset_train-r3-new | subset_train / 60 | 325 / 57 | 60 strategy + 60 initial checkpoints, summaries, benchmark, matrices | user explicitly confirmed authoritative; analyzed |
| experiments/subset_test-r3 | subset_test / 30 | 111 / 29 | checkpoints, summary/benchmark/matrix | TEST, excluded |

All listed manifests use English and deepseek/deepseek-chat. Full R2 uses budget
6 and the same aggregate implementation hash as authoritative R0/R1. New R3 uses
budget 6 and a different hash; older R3 uses another hash. Repository run-command
documentation describes naming conventions, not authoritative final selection.
No manifest was found in the R3 pilot directory. No R3P data are analyzed.

The R1 declared UID `h20241029143754236194` has no attempt or terminal evidence;
its row remains unknown. At least 23 reconstructable R0/R1 initial plans differ.
These data use repeated commonsense repair, not a presumed strict one-C policy.
All cross-strategy comparisons remain observational.

## Tests

```sh
python -m unittest discover -s tests -p 'test_analyze_repair_strategies.py'
```

Fixtures cover loading, optional artifacts, UNKNOWN, ordering, identity warnings,
accepted reconstruction and R2 rollback, scope parsing, matrix triplets, missing
outcomes, CLI subsets/order, source safety, and byte-identical repeated CSVs.


## R4 TEST evidence and analysis

The explicit source is `experiments/subset_test-r4/`: 30 declared TEST queries,
175 proposals, 30 independent trial checkpoints, combined mode (one pooled-matrix
trial per query). No R4 runtime, selector, evaluator, safety routine or matrix
builder is executed by the analyzer. The read-only R4 adapter/hook is
`scripts/repair_analysis_r4.py`.

The active implementation is
`chinatravel.agent.nesy_verifier.repair_strategies.r4.MatrixGuidedRepair`;
`r4/strategy.py` is a compatibility import. It reuses R3 helpers with whole-plan
scope, not R3's widening schedule. Personal rankings sum probabilities toward
currently passing families, break ties by higher support then lower index, and
are advisory: all failed personal targets remain in feedback. Unsupported prior
cells use the logged neutral value 0.5. That value is a fallback configuration,
not a safety threshold or a logged event proving the model followed it.
Commonsense-source risk relationships are logged separately. No unlogged target
order, target choice, protection enforcement or cell influence is inferred.

Two outcomes must remain distinct:

- `final_observed_*` describes each trial's last accepted personal state, using
  the same shared calculations as R0–R3.
- `selected_final_*` describes the persisted post-hoc exported selection. The
  selector considers initial plus eligible verified candidate outcomes, minimizing
  unresolved checks/unknowns/personal/commonsense/schema, then step and source.
  The analyzer validates membership without invoking or changing selection.

For multiple independent matrix trials, the adapter reconstructs each trial with
shared helpers and sums proposal/efficiency events, while keeping per-trial states
in `trial_trajectories`. A unique last-accepted query endpoint is left undefined;
`selected_final_*` is the independently persisted selected endpoint. Local trial
steps reset, so proposal identity also includes the persisted trial strategy.

The current selection pool contains 205 outcomes (30 initial plus 175 proposals):
30 selected and 175 non-selected. Seventeen winners are initial plans; 13 are
proposal outcomes. This does not mean 175 proposals were rejected: all 175 were
accepted by the shared loop. The generation/search costs include all trials even
when an initial or early proposal wins. Per-outcome currency costs and selection
CPU overhead are not persisted and are not fabricated.

### Guidance provenance and leakage

The run snapshot `inputs/pooled/main_matrix.csv` is a 100-cell, 10×10 prior with a
separate manifest. The manifest names R0/R1/R2/R3 TRAIN sources. The auditor reads
those exact recorded paths, rebasing Windows checkout prefixes to the same
repository artifacts; it never searches for substitute runs or rebuilds evidence.
It checks the stored hashes, contribution/history UIDs against subset_train,
source labels, and exclusion of R4 TEST UIDs. R1's unavailable commonsense-destination
history is explicitly retained as incomplete evidence.

The allowlist hash is defined by the runtime as SHA-256 of the LF-joined, sorted
UID set without a trailing newline, rather than the raw split-file bytes.
Several Windows-era artifact hashes match only the CRLF representation of the
checkout contents. This is reported as `CRLF_equivalent`, distinct from raw-byte
`exact`. TRAIN-only guidance content can be verified while strict byte-exact
provenance remains false. No source bytes, matrix contents or manifests are changed.
`r4_matrix_provenance.json`, `r4_provenance_files.csv`, `r4_matrix_sources.csv`, and
`r4_run_metadata_snapshot.json` preserve the audit and recorded implementation hashes.

### R4-specific outputs

Where corresponding evidence exists:

```text
R4/r4_trials.csv
R4/r4_selections.csv
R4/r4_matrix_guidance.csv
R4/r4_recommendations.csv
R4/r4_support_summary.csv
R4/r4_fallbacks.csv
R4/r4_costs.csv
R4/r4_scope_summary.csv
R4/r4_safety_summary.csv
R4/r4_targeting.csv
R4/r4_matrix_cells.csv
R4/r4_matrix_sources.csv
R4/r4_provenance_files.csv
R4/r4_benchmark_plan_audit.csv
```

These supplement, rather than redefine, the shared outputs. The prior is not a
realized R4 regression matrix: absent outcome matrices remain unavailable in
`matrix_summary.csv`. Prior heatmaps are explicitly titled TRAIN-derived guidance.
No artificial empty R4-specific tables are emitted solely to satisfy filenames.

Unsupported probabilities are counted from logged risk relationships (29/175
proposals in the current run), separately from 39 proposals with no logged
relationship. Repeated logged cells are retained as relationships, not independent
empirical observations. Ninety proposals log a structural rejection and return an
unchanged candidate; these are not shared-loop rejection decisions. Passing
personal constraints are prompt protection, not enforced R2-style rollback.

**Benchmark policy caveat:** all 30 saved benchmark plans match the trial's last
accepted plan; 12 differ from post-hoc selection. The analyzer reports the saved
benchmark population/policy and verifies both identities without rerunning or
changing evaluation. Existing scores must not be described as selected-outcome
scores for those differing plans.

### Cross-strategy separation

Synthesis groups by explicit partition and query population. Only the largest
aligned group enters the direct aggregate table; excluded sources are listed in
`cross_strategy/excluded_runs.csv` and its report. Thus an invocation supplying
R0–R3 TRAIN and R4 TEST keeps the existing TRAIN numerical tables unchanged and
adds a separate R4 TEST note. Different model/settings/initial plans still limit
any aligned comparison to descriptive evidence. No alternative TEST run is
silently substituted. `experiments/subset_test-r3/` is a possible matching TEST
population, but has not been selected as authoritative for this analysis.
