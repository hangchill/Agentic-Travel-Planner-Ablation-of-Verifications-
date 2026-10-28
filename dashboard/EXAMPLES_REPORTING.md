# Canonical mechanism examples

The Examples dashboard page and route have been removed. The six-page navigation
is Overview, Query Explorer, TRAIN set, TEST set, Ablations & Comparisons, and
Strategy-Specific. This document describes retained analysis helpers, not an
available dashboard screen.

`dashboard/example_selection.py` retains mechanism qualification, ranking and
Markdown serialization. `dashboard/components/examples.py` retains only evidence
collection and frozen TRAIN-matrix validation. Their analysis regression tests
remain; page rendering, selectors and page-specific exports were removed.
No experiment or representative-example analysis artifacts were deleted.

The retained qualification rules are:

| Section | Source | Exact qualification |
| --- | --- | --- |
| Cascading violation / interdependency | TRAIN R0–R3 | Personal repair, target False→True, one known target family A, and a previously True PC in a different known family B becomes False in the candidate |
| R2 protection success | TEST R2 | Protected PC True→False in candidate, rejected, decision reason `previously_satisfied_constraint_regressed`, and logged `accepted_plan_after` equals the prior accepted raw plan |
| R3 widening success | TEST R3 | Earlier slot proposal with unresolved failing target, explicit no-progress marker, or rejection; later day/plan proposal accepted with target False→True or fewer CS loop error messages |
| R4 matrix-guided case | TEST R4 | Positive logged relationship support/rate matches the trial's frozen TRAIN matrix cell, and proposal is accepted with target False→True or fewer CS loop error messages |
| R4 contrast | TEST R4 | Unsupported/no logged relationship, structural guard, or supported guidance without accepted target improvement or a candidate not selected post hoc |

PC transitions require equal-length known before/candidate vectors; only explicit
Boolean False→True/True→False pairs count. Family classification reuses
`dashboard.metrics.family_map`, the project's existing constraint-family classifier.
CS improvements mean loop error-message count reductions, not benchmark check
pass rates. Changed/no-progress labels reuse the existing trajectory helper and
explicit log marker; missing translated plans leave Changed unavailable.

Default ordering prefers single-target, saved-matrix-contribution, higher-support
TRAIN cascades; target-fixing R2 rollbacks; PC-fixing, regression-free R3 widening
sequences; and post-hoc-selected, regression-free, target-fixing supported R4
repairs. Structural guard contrasts have priority. Ties use run/query/trial/round
identities, with no hard-coded examples.

## Evidence sources and distinctions

- `run_manifest.json` supplies discovered partition/strategy/run identity.
- `queries/*/R*-*.json` and R4 `queries/*/trials/*.json` supply independent
  checkpoint histories, repair attempts, candidate verifications, acceptance
  decisions, raw accepted plans, and final loop states.
- `test_result_analysis/<strategy>/per_query.csv` supplies difficulty labels only.
- Saved `matrix_summary.csv` (or original persisted matrix tables) supplies TRAIN
  family relationship support and observed regression rates. Original
  `regression_matrix/matrix_contributions.csv` confirms saved contribution
  membership where present; absence means no membership confirmation is claimed.
- R4's checkpoint `matrix.path` resolves inside its run directory, never an
  arbitrary path. Its frozen CSV must match recorded output/checkpoint hashes,
  and its manifest input directories must identify TRAIN R0–R3. Hash checks allow
  only LF/CRLF variants because Windows-generated inputs have LF checkouts on
  macOS; arbitrary byte/content changes fail closed. Logged support/rates must
  also match the specific saved cell. No matrix is reconstructed.
- R4 `final_state.json` supplies post-hoc selection source/step/outcome.
  A selected matrix identifier disambiguates matching trials where available;
  ambiguous trial identities remain unavailable. Post-hoc selection never
  rewrites loop acceptance, checkpoint final states or benchmark reporting.

Trials are never joined to invent a widening sequence or rollback. Missing accepted
raw plans invalidate subsequent preservation proof until a new accepted raw plan
is logged. All examples keep candidate, accepted-before, accepted-after, final
loop, and post-hoc states separate. R3 uses the fixed widening semantics documented
in `chinatravel/agent/nesy_verifier/repair_strategies/r3.py`; no causal reaction to
failure is claimed. R4 was **provided** guidance; following or causal impact is
not inferred.

The retained Markdown serializer can describe a selected trajectory and states
for programmatic use. It is no longer registered as a dashboard display or download.
Tables 1–4, numerical aggregate metrics, experiment artifacts and analysis outputs
are unchanged.
