# Attraction curation verification

257 candidates: 33 COMMONPLACE_REVIEW_LANDMARK_SUPPORTED; 20 COMMONPLACE_EXCLUDE_LANDMARK_SUPPORTED; 4 UNMATCHED_SCENIC_LANDMARK; 200 UNMATCHED_INDIVIDUAL_LANDMARK. Priority: HIGH 190, MEDIUM 67, LOW 0. Possible INCLUDE alias/constituent evidence: 23. Weak Kaggle name support: 6.

Individual screening: 1429 unmatched/rejected records; 772 keyword-bearing rows. Explicit infrastructure signals exclude 66 and private-residence wording without institutional signals excludes 213. Remaining signals produce 493 rows; conservative deduplication leaves 491 optional candidates. The deterministic ranking retains 200 and truncates 291. No decisions are inferred. All mandatory source identities are retained.

Manual-decision, reason and notes fields in both CSV outputs are blank. Temporary IDs use only CUR_; no final attraction IDs, processed attractions.csv, additions, promotions or union. CommonPlace remains INCLUDE 2901, REVIEW 5790, EXCLUDE 11760, UNMAPPED 0, total 20451.

Docker build/configuration and curation script passed. Notebook executed all 23 code cells without errors. Full unittest suite passed 76 tests (15 new curation tests). All three curation outputs are byte-identical on repeated generation. git diff --check passed. All 100 pre-existing protected files remained byte-identical, including the automatic candidate base, filter metadata, restaurant CSV/scripts/tests/metadata, Kaggle audit and landmark matching outputs. No commit or push.

Restaurant CSV SHA256: `f4143bdcba0bbe9f2cb686c53c456a21da027512d3722b8e0f4651738760d1bc`.

Files created/modified for this task:

- scripts/build_attraction_curation.py (new).
- tests/test_attraction_curation.py (new).
- data/reports/final_attraction_curation.csv (new full evidence table).
- data/reports/final_attraction_curation_manual.csv (new primary manual-review view).
- data/reports/final_attraction_curation_report.md (new selection/evidence summary).
- data/reports/attraction_curation_verification.md (this verification and final Git status).
- notebooks/explore_attractions.ipynb (new curation section and executed outputs).
- README.md (manual-review workflow).

Existing untracked files from earlier pipeline work remain present. Final git status --short:

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
?? data/metadata/attractions_sources.md
?? data/metadata/commonplace_attraction_filter.csv
?? data/metadata/commonplace_taxonomy.csv
?? data/reports/attraction_curation_verification.md
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
?? scripts/match_attractions_kaggle.py
?? scripts/resolve_attraction_review.py
?? tests/test_attraction_curation.py
?? tests/test_attraction_filter.py
?? tests/test_attractions_exploration.py
?? tests/test_kaggle_attraction_matching.py
?? tests/test_landmark_audit.py
```
