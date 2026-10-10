# Google Local matching verification

Metadata filename: `meta-New_York.json.gz`. Size: 60,954,605 bytes. SHA-256: `b0d618a3e0d7286991f816a16079727e15ae20fdc2a6195d8d4ffae2cc28c534`. Raw rows: 272,189; geographic candidates: 118,653.

| Entity | Total | HIGH accepted | Coverage | MEDIUM summaries | Ambiguous | Unmatched | Rejected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Restaurant | 670 | 246 | 36.72% | 1 | 1 | 309 | 114 |
| Attraction | 3,066 | 641 | 20.91% | 259 | 80 | 1,269 | 1,076 |

Registry: 887 rows, all HIGH; canonical identities valid, entity/type unique, Google IDs non-null and unique.

Collision claims: 15 across 7 Google IDs. Classification counts by claim: {'duplicate_canonical_entity': 12, 'parent_child_attraction_issue': 3}. All excluded from registry.

Full method, category/subcategory/source coverage, schema inspection, and unmatched examples: [matching report](google_local_entity_matching_report.md).

## Validation

Docker build and compose configuration passed. Metadata download/cache, full streaming clean and matching succeeded in Docker. All 107 unittest tests passed. Repeated clean/matching produced byte-identical cleaned CSV, registry, restaurant audit, attraction audit, ambiguity audit, collision audit and Markdown report. `git diff --check` passed. Notebook was not changed.

All 116 pre-existing data/scripts/tests files were checked against the before-task snapshot and remain byte-identical. Canonical hashes:

- `data/processed/restaurants.csv`: `f4143bdcba0bbe9f2cb686c53c456a21da027512d3722b8e0f4651738760d1bc` (before = after)
- `data/processed/attractions.csv`: `594934dc2c5a64b65628bb27e458ce07e32f98ee667ffb560ea787ba89a0c6c4` (before = after)

No review file downloaded or extracted; no processed review table or reviewer profile created. Raw metadata is Git-ignored.

## Files created or modified in this task

- `README.md`
- `scripts/download_reviews.py`
- `scripts/google_local_matching.py`
- `tests/test_google_local_matching.py`
- `data/metadata/google_local_review_source.md`
- `data/interim/google_local_ny_metadata_clean.csv`
- `data/metadata/google_local_entity_registry.csv`
- `data/reports/google_local_ambiguous_matches.csv`
- `data/reports/google_local_attraction_matching.csv`
- `data/reports/google_local_entity_matching_report.md`
- `data/reports/google_local_gmap_id_collisions.csv`
- `data/reports/google_local_restaurant_matching.csv`
- `data/reports/google_local_matching_verification.md`

`requirements.txt` and the other existing untracked attraction artifacts predate this task and were preserved. No commit or push.

## Final git status --short

```
 M README.md
 M requirements.txt
?? data/interim/commonplace_attraction_candidates.csv
?? data/interim/commonplace_attraction_classified.csv
?? data/interim/commonplace_attraction_review.csv
?? data/interim/commonplace_attraction_unmapped.csv
?? data/interim/commonplace_attractions_clean.csv
?? data/interim/commonplace_kaggle_tourist_signal.csv
?? data/interim/google_local_ny_metadata_clean.csv
?? data/interim/individual_landmarks_clean.csv
?? data/interim/kaggle_tourist_locations_clean.csv
?? data/interim/scenic_landmarks_clean.csv
?? data/metadata/attraction_auto_curation_rules.csv
?? data/metadata/attraction_category_mapping.csv
?? data/metadata/attraction_id_registry.csv
?? data/metadata/attractions_sources.md
?? data/metadata/commonplace_attraction_filter.csv
?? data/metadata/commonplace_taxonomy.csv
?? data/metadata/google_local_entity_registry.csv
?? data/metadata/google_local_review_source.md
?? data/processed/attractions.csv
?? data/reports/attraction_auto_curation_report.csv
?? data/reports/attraction_auto_curation_report.md
?? data/reports/attraction_curation_verification.md
?? data/reports/attraction_duplicate_alias_audit.csv
?? data/reports/attraction_finalization_verification.md
?? data/reports/commonplace_attraction_filter_report.md
?? data/reports/commonplace_candidate_name_review.csv
?? data/reports/commonplace_domain_samples.csv
?? data/reports/commonplace_domain_type_counts.csv
?? data/reports/commonplace_domain_type_crosstab.csv
?? data/reports/commonplace_exclude_supported_by_landmarks.csv
?? data/reports/commonplace_excluded_subtypes.csv
?? data/reports/commonplace_exploration_report.md
?? data/reports/commonplace_facility_domain_counts.csv
?? data/reports/commonplace_facility_type_counts.csv
?? data/reports/commonplace_include_supported_by_kaggle.csv
?? data/reports/commonplace_include_supported_by_landmarks.csv
?? data/reports/commonplace_included_subtypes.csv
?? data/reports/commonplace_kaggle_review_subtype_support.csv
?? data/reports/commonplace_near_duplicate_names.csv
?? data/reports/commonplace_review_resolution.md
?? data/reports/commonplace_review_resolution_with_landmarks.md
?? data/reports/commonplace_review_subtypes.csv
?? data/reports/commonplace_review_supported_by_kaggle.csv
?? data/reports/commonplace_review_supported_by_landmarks.csv
?? data/reports/commonplace_same_name_different_location.csv
?? data/reports/commonplace_same_name_same_location.csv
?? data/reports/commonplace_schema.csv
?? data/reports/commonplace_type_samples.csv
?? data/reports/final_attraction_curation.csv
?? data/reports/final_attraction_curation_manual.csv
?? data/reports/final_attraction_curation_report.md
?? data/reports/google_local_ambiguous_matches.csv
?? data/reports/google_local_attraction_matching.csv
?? data/reports/google_local_entity_matching_report.md
?? data/reports/google_local_gmap_id_collisions.csv
?? data/reports/google_local_matching_verification.md
?? data/reports/google_local_restaurant_matching.csv
?? data/reports/kaggle_audit_verification.md
?? data/reports/kaggle_commonplace_ambiguous_matches.csv
?? data/reports/kaggle_commonplace_matching_report.csv
?? data/reports/kaggle_commonplace_matching_summary.csv
?? data/reports/kaggle_commonplace_name_only_candidates.csv
?? data/reports/kaggle_matches_commonplace_exclude.csv
?? data/reports/kaggle_tourist_locations_unmatched.csv
?? data/reports/kaggle_tourist_relevance_report.md
?? data/reports/landmark_audit.md
?? data/reports/landmark_commonplace_matching_report.csv
?? data/reports/landmark_commonplace_matching_summary.csv
?? data/reports/landmark_pipeline_verification.md
?? data/reports/landmarks_unmatched_commonplace.csv
?? notebooks/explore_attractions.ipynb
?? scripts/audit_landmarks.py
?? scripts/build_attraction_curation.py
?? scripts/download_attractions.py
?? scripts/download_reviews.py
?? scripts/explore_attractions.py
?? scripts/filter_attractions.py
?? scripts/finalize_attractions.py
?? scripts/google_local_matching.py
?? scripts/match_attractions_kaggle.py
?? scripts/resolve_attraction_review.py
?? tests/test_attraction_curation.py
?? tests/test_attraction_filter.py
?? tests/test_attraction_finalization.py
?? tests/test_attractions_exploration.py
?? tests/test_google_local_matching.py
?? tests/test_kaggle_attraction_matching.py
?? tests/test_landmark_audit.py
```
