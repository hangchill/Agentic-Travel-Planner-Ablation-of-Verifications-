# Offline review corpus verification

Review file: `review-New_York.json.gz`; compressed size 2,649,939,478 bytes.
SHA-256: `847fff4eb277aa9c0a257c7b3008bef641ef4bc6f65067cbe4edae2eccfb0687`.
Retrieval: 2026-10-10T12:50:19.956649+00:00. Official full split URL recorded in extraction provenance.

Full source scan: 33,459,761 reviews. Accepted-mapping observations: 596,154; text-bearing: 305,170; ratings-only: 290,984. Exact duplicates found and removed: 7,748. All 887 accepted entities occur in coverage, including the 3 attraction entities with zero text reviews.

| Entity | Canonical | Accepted mapping | With text | Text coverage | Cap required / at 100 | Below cap | Processed rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Restaurant | 670 | 246 | 246 | 36.72% | 158 | 88 | 20,349 |
| Attraction | 3,066 | 641 | 638 | 20.81% | 254 | 387 | 36,203 |

Mapping coverage is 36.72% / 20.91%; actual text coverage is 36.72% / 20.81%. Availability absent means UNKNOWN, never negative subjective evidence.

## Processed rating distributions and dates

```json
[
  {
    "entity_type": "restaurant",
    "rows": 20349,
    "entities_with_text": 246,
    "rating_distribution": {
      "1.0": 2516,
      "2.0": 1409,
      "3.0": 2043,
      "4.0": 3585,
      "5.0": 10796
    },
    "date_range": [
      "1990-12-31",
      "2021-08-20"
    ]
  },
  {
    "entity_type": "attraction",
    "rows": 36203,
    "entities_with_text": 638,
    "rating_distribution": {
      "1.0": 2532,
      "2.0": 2023,
      "3.0": 4309,
      "4.0": 7946,
      "5.0": 19393
    },
    "date_range": [
      "2008-02-04",
      "2021-08-30"
    ]
  }
]
```

Count quantiles and text-count bins before cap are in [restaurant report](restaurant_review_report.md) and [attraction report](attraction_review_report.md), alongside date/rating distributions and attraction category coverage. Earliest restaurant source timestamp converts to 1990-12-31; this unusually early source value is preserved, not corrected or asserted reliable.

## Verification

Docker build/config passed; full source downloaded and scanned once in Docker. Completed extraction cache reused for repeated builds. Full unittest suite: 117 tests passed. Streaming selection, text cleaning, empty text exclusion, exact deduplication, cap, diversity/recency, input-order determinism, persistent RR_/AR_ IDs, referential integrity and identity-free schemas verified.

All 9 corpus/registry/report files byte-identical across repeated builds. Persistent IDs match their keys. Every processed entity/Google ID pair exists in the frozen accepted registry. No orphan rows, no blank text, no entity exceeds 100. Processed schemas contain no reviewer identity fields. Interim schemas omit user ID, name, photos and business response. No subjective labels or reviewer profiles created.

All 108 prior data/scripts/tests files remain byte-identical. Frozen before = after SHA-256:

- `data/processed/restaurants.csv`: `f4143bdcba0bbe9f2cb686c53c456a21da027512d3722b8e0f4651738760d1bc`
- `data/processed/attractions.csv`: `594934dc2c5a64b65628bb27e458ce07e32f98ee667ffb560ea787ba89a0c6c4`
- `data/metadata/google_local_entity_registry.csv`: `353476becaf464b0610eadacc411601cfdf7738efe7f8430dabd0e010b8369e5`

The 355 MB rebuildable SQLite interim is ignored by Git and Docker build contexts; it remains accessible in the existing Docker bind mount. The raw 2.65 GB review split is Git-ignored. Notebook not updated. `git diff --check` passed. No commit or push.

## Files created or modified this task

- `.gitignore`
- `.dockerignore`
- `README.md`
- `scripts/download_review_corpus.py`
- `scripts/build_review_corpora.py`
- `tests/test_review_corpora.py`
- `data/metadata/review_corpus_schema.md`
- `data/interim/google_local_matched_reviews.sqlite`
- `data/processed/restaurant_reviews.csv`
- `data/processed/attraction_reviews.csv`
- `data/metadata/restaurant_review_id_registry.csv`
- `data/metadata/attraction_review_id_registry.csv`
- `data/reports/google_local_review_coverage.csv`
- `data/reports/google_local_review_extraction.json`
- `data/reports/restaurant_review_report.md`
- `data/reports/attraction_review_report.md`
- `data/reports/review_dataset_summary.md`
- `data/reports/review_corpus_verification.md`

Pre-existing requirements and other untracked attraction/matching artifacts were preserved.

## Final git status --short

```
 M .dockerignore
 M .gitignore
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
?? data/metadata/attraction_review_id_registry.csv
?? data/metadata/attractions_sources.md
?? data/metadata/commonplace_attraction_filter.csv
?? data/metadata/commonplace_taxonomy.csv
?? data/metadata/google_local_entity_registry.csv
?? data/metadata/google_local_review_source.md
?? data/metadata/restaurant_review_id_registry.csv
?? data/metadata/review_corpus_schema.md
?? data/processed/attraction_reviews.csv
?? data/processed/attractions.csv
?? data/processed/restaurant_reviews.csv
?? data/reports/attraction_auto_curation_report.csv
?? data/reports/attraction_auto_curation_report.md
?? data/reports/attraction_curation_verification.md
?? data/reports/attraction_duplicate_alias_audit.csv
?? data/reports/attraction_finalization_verification.md
?? data/reports/attraction_review_report.md
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
?? data/reports/google_local_review_coverage.csv
?? data/reports/google_local_review_extraction.json
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
?? data/reports/restaurant_review_report.md
?? data/reports/review_corpus_verification.md
?? data/reports/review_dataset_summary.md
?? notebooks/explore_attractions.ipynb
?? scripts/audit_landmarks.py
?? scripts/build_attraction_curation.py
?? scripts/build_review_corpora.py
?? scripts/download_attractions.py
?? scripts/download_review_corpus.py
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
?? tests/test_review_corpora.py
```
