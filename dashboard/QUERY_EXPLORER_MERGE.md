# Query Explorer presentation merge

This change adapts the teammate replay's presentation into the existing dashboard;
it does not embed a second app or replace any analysis pipeline.

## Files

- `components/query_explorer.py`: summary, attempt navigation, state tabs, strategy
  evidence, history, process details, downloads, final/selected outcomes, provenance.
- `components/itinerary_cards.py`: reusable cards, recorded editable-location focus,
  conservative activity alignment and supplementary field-diff display.
- `query_presentation.py`: read-only raw-plan attachments to the existing numerical
  trajectory, filters, labels, history display and redacted evidence serialization.
- `data_loader.py`: returns aligned checkpoint source paths and the saved reference
  query alongside the existing checkpoint bundle. Discovery/binding is unchanged.
- `tests/test_query_presentation.py`: synthetic artifact and Streamlit interaction
  coverage for state separation, alignment, navigation and strategy presentation.
- `README.md`: controls, semantics, formatting reuse and missing-evidence behavior.

## Data and semantics

`metrics.trajectory`, shared attempt metrics and the TEST table builder remain
unchanged. All sources remain the existing experiments, bound generated diagnostics,
and TEST reporting tables. No analysis artifacts need regeneration for this change.

Raw Before starts with `initial_raw_plan`. Candidate comes from the selected
history entry or its repair attempt. Accepted after prefers recorded
`accepted_plan_after`; otherwise an accepted candidate advances the raw trajectory,
while an explicitly rejected candidate preserves the prior raw plan. Unknown
acceptance does not fabricate a raw state. Recorded retention confirmation is
available only when an explicit accepted-after plan exists. Missing final accepted
plans stay unavailable. Post-hoc selected plans never replace this trajectory.

Diffs use unique stable activity/slot IDs, then unique same-place/route identities.
No list-index matching is used. Ambiguous days and duplicate/changed identities
produce unavailable/partial alignment, without an invented changed-activity count.
Recorded IDs permit added/removed/reordered activity displays. Raw field changes
remain supplementary to the existing team-defined changed classification.

Only generic pure formatting functions are reused from `frontend.presentation`.
Frozen demo data, curated narration/mappings, live generation/verification,
`frontend.history`, `frontend.planner` and `frontend.storage` are excluded.

## Validation

Validation commands and final results are reported in the implementation response.
The protected-file baseline is `/tmp/query-merge-protected.json`; it covers experiment
artifacts, frontend sources/fixture, analysis sources, verifier/planner sources,
canonical TEST reporting and generated analysis. Temporary test fixtures are outside
the repository. No providers or evaluators are called by the walkthrough.

Browser inspection remains unavailable in this session because no browser connection
is registered. AppTest verifies generated controls and interactions, rather than
claiming screenshot-based visual validation.

Final results:

- Dashboard: 163 tests, 161 passed, two pre-existing PC reporting errors. Both
  reference `Final plans with 2+ failed PC`, which the upstream builder replaced
  with separate 2 and 3+ bins. Neither definitions nor unrelated tests were changed.
- New Query Explorer coverage: all 19 tests passed, including actual download
  payload capture after switching independent trials and missing-plan rendering.
- Existing strategy analysis: 48 passed; ablation comparisons: 18 passed.
- Existing repair metrics: 13 passed; commonsense round metrics: 4 passed.
- Teammate replay: all 6 passed.
- Real-data AppTest: TEST R2 rejection, R3 scope, R4 selection, field comparison and
  downloads; teammate TRAIN R2 query; round filtering; dashboard startup passed.
- Presentation/history binding checks passed for all 90 TEST R2/R3/R4 trials.
- Import/compilation and tracked/untracked whitespace checks passed.
- All 3,405 protected file hashes matched the starting baseline after validation.
- No model/provider calls, experiment writes, commits or pushes occurred.

Restart the existing Streamlit dashboard to load source changes (repository file
watching is disabled). Analysis regeneration is not required.
