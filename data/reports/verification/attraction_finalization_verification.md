# Attraction finalization verification

Original CommonPlace INCLUDE base: 2901. Preserved shortlist: 257. Auto decisions: ADD 165, DO_NOT_ADD 91, ALIAS_OF_EXISTING 1. Final attraction rows: 3066.

Additions by origin: supported REVIEW 33; supported EXCLUDE 5; unmatched Individual 124; unmatched Scenic 3. Fort Tryon Park resolves to existing ATTR_0898 (CommonPlace source ID 15705); its alias provenance is retained. No further duplicate additions were removed. All 2901 base source identities remain present, including existing base duplicates, as required.

Added final categories: historic_site 41, theater 35, park 28, religious_site 24, landmark 18, transport_landmark 9, museum 5, garden 3, sports 1, market 1.

Final schema: attraction_id, name, category, subcategory, borough, latitude, longitude, source, source_id, is_landmark, landmark_source, landmark_source_id, tourist_relevance_source, facility_type, facility_domain_code, facility_domain_label, commonplace_filter_decision, curation_candidate_id, kaggle_name_support, landmark_evidence. No invented rating, price or opening_hours.

Docker build/configuration, integrated auto curation/finalization, notebook execution (25 code cells), all 92 tests (16 new finalization tests), repeat-run determinism, ID/base/schema validation and git diff --check passed. Five generated finalization artifacts (final CSV, registry, CSV/Markdown curation audit, duplicate/alias audit) were byte-identical on rerun. Persistent registry assignments are unchanged; append/retired-key behavior is tested.

All 106 pre-existing protected files remain byte-identical, including the original shortlist/manual view, CommonPlace source/classification/filter metadata/base, prior Kaggle/landmark audits and restaurant pipeline. CommonPlace counts stay INCLUDE 2901, REVIEW 5790, EXCLUDE 11760, UNMAPPED 0, total 20451. Restaurant CSV SHA256: f4143bdcba0bbe9f2cb686c53c456a21da027512d3722b8e0f4651738760d1bc. No commit or push.

Created/modified for this task:

- scripts/finalize_attractions.py; tests/test_attraction_finalization.py.
- data/metadata/attraction_auto_curation_rules.csv; attraction_category_mapping.csv; attraction_id_registry.csv.
- data/processed/attractions.csv.
- data/reports/attraction_auto_curation_report.csv and .md; attraction_duplicate_alias_audit.csv; this verification report.
- README.md; notebooks/explore_attractions.ipynb (manual requirement superseded, historic evidence retained).

Existing untracked files from earlier pipeline stages remain present. Final git status --short:

```text
 M README.md
 M requirements.txt
?? data/interim/commonplace_attraction_candidates.csv
?? data/interim/commonplace_attraction_classified.csv
?? data/interim/commonplace_attraction_review.csv
?? data/interim/commonplace_attraction_unmapped.csv
?? data/interim/commonplace_attractions_clean.csv
?? data/interim/commonplace_kaggle_tourist_signal.csv
?? data/interim/individual_landmarks_clean.csv
?? data/interim/kaggle_tourist_locations_clean.csv
?? data/interim/scenic_landmarks_clean.csv
?? data/metadata/attraction_auto_curation_rules.csv
?? data/metadata/attraction_category_mapping.csv
?? data/metadata/attraction_id_registry.csv
?? data/metadata/attractions_sources.md
?? data/metadata/commonplace_attraction_filter.csv
?? data/metadata/commonplace_taxonomy.csv
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
?? scripts/explore_attractions.py
?? scripts/filter_attractions.py
?? scripts/finalize_attractions.py
?? scripts/match_attractions_kaggle.py
?? scripts/resolve_attraction_review.py
?? tests/test_attraction_curation.py
?? tests/test_attraction_filter.py
?? tests/test_attraction_finalization.py
?? tests/test_attractions_exploration.py
?? tests/test_kaggle_attraction_matching.py
?? tests/test_landmark_audit.py
```
