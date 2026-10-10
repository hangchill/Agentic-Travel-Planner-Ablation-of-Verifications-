# Landmark pipeline verification

CommonPlace before/after: INCLUDE 2901, REVIEW 5790, EXCLUDE 11760, UNMAPPED 0, TOTAL 20451. All 29 configured REVIEW subtypes remain REVIEW; no blanket change was justified. Metadata remains unchanged.

Individual raw rows 1532; designated eligibility 1514, with currency unverified because the current flag is absent. Other states 18 (Amended 8, Proposed 6, Moved 3, Heard 1). Scenic raw rows 8; current and designated 8, other current states 0, inactive/non-current 0.

| Source | MATCHED_INCLUDE | MATCHED_REVIEW | MATCHED_EXCLUDE | UNMATCHED | AMBIGUOUS | REJECTED |
|---|---:|---:|---:|---:|---:|---:|
| Individual | 33 | 32 | 20 | 1415 | 0 | 14 |
| Scenic | 3 | 1 | 0 | 4 | 0 | 0 |
| Total | 36 | 33 | 20 | 1419 | 0 | 14 |

There are 1433 eligible records with no accepted match, including 14 rejected name candidates. Matching confirms 89 distinct CommonPlace rows. REVIEW support is strongest for Church (18 unique rows), Cemetery/Morgue (4), cultural Other (2), and nine other subtypes with one each; no individual or subtype is promoted. Notable REVIEW matches include Whitehall Ferry Terminal, Pier A, McCarren Play Center and Verdi Square. EXCLUDE matches include Gracie Mansion, Seagram Building, Waldorf-Astoria Hotel and Pratt Institute Library. Scenic gaps include Grand Army Plaza, Prospect Park, Fort Tryon Park and Coney Island (Riegelmann) Boardwalk. Name/geometry differences may explain apparent gaps; they are not confirmed source absences.

Docker build, Compose configuration, landmark download/cache, cleaning/matching, review proposal/filter regeneration, notebook execution (21 code cells), full tests (61 passed, including 14 new landmark tests), repeat-output checks and git diff --check passed. Repeated classified/candidate/review/unmapped outputs, landmark cleaned tables and reports are byte-identical across identical snapshots. Protected restaurant scripts/tests/metadata/CSV, CommonPlace raw data and Kaggle audit files remained byte-identical. Raw landmark files remain Git-ignored.

Restaurant CSV SHA256: `f4143bdcba0bbe9f2cb686c53c456a21da027512d3722b8e0f4651738760d1bc`. No final attraction IDs, processed attractions.csv, selective promotions, source union, commit or push.

Files created/extended this task:

- README.md; requirements.txt (Shapely, pyproj, pyshp compatible with existing Python 3.11 image).
- scripts/download_attractions.py; new scripts/resolve_attraction_review.py and scripts/audit_landmarks.py.
- tests/test_landmark_audit.py; notebooks/explore_attractions.ipynb.
- data/interim/individual_landmarks_clean.csv and scenic_landmarks_clean.csv.
- data/reports/commonplace_review_resolution.md and commonplace_review_resolution_with_landmarks.md.
- data/reports/landmark_audit.md, landmark_commonplace_matching_report.csv, landmark_commonplace_matching_summary.csv.
- data/reports/commonplace_include_supported_by_landmarks.csv, commonplace_review_supported_by_landmarks.csv, commonplace_exclude_supported_by_landmarks.csv.
- data/reports/landmarks_unmatched_commonplace.csv and this verification report.
- Existing CommonPlace outputs regenerated without byte changes; existing untracked files remain in final status.

Final git status --short:

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
?? scripts/download_attractions.py
?? scripts/explore_attractions.py
?? scripts/filter_attractions.py
?? scripts/match_attractions_kaggle.py
?? scripts/resolve_attraction_review.py
?? tests/test_attraction_filter.py
?? tests/test_attractions_exploration.py
?? tests/test_kaggle_attraction_matching.py
?? tests/test_landmark_audit.py
```
