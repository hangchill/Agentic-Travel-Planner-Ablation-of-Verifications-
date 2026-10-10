# Repository cleanup verification

Structural cleanup only: thresholds, curation, matching, sampling, identifiers, schemas and row ordering unchanged. No production pipeline was rerun against canonical outputs. Scope: restaurants, attractions and their reviews only.

## Inventory and organization

Inventoried 121 existing files before moves: [inventory](../repository_cleanup_inventory.csv). Moved 86 files. No data, audit, test or intermediate artifact deleted. Scripts/tests are domain packages; shared normalization helpers live in scripts/shared. All prior tests retained. Metadata remains flat to preserve stable configuration and provenance paths.

Detailed reports moved under audit/restaurants, audit/attractions and audit/reviews; historical verification moved under verification. Prior report contents were preserved byte-for-byte, including historical paths/commands; inventory provides old → current paths. Final summaries remain top-level, with a new attraction overview. Root README rewritten for navigation and package commands; data/README supplies lineage/evidence boundaries. Metadata documentation received path-only corrections.

Both exploratory notebooks reduced to short read-only inspections, stale outputs cleared. They now inspect processed data/audits and do not call transformation main() functions.

## Protection checks

All 9 processed tables and persistent/accepted registries byte-identical:

- `data/processed/attraction_reviews.csv`: `dbf731ed0c8efe25e33618eeb43c54742f3e929fa637f9186016d02d94c8fdb8` (before = after)
- `data/processed/restaurant_reviews.csv`: `e8934a61aafc0cafaa7281389e49fbe10f1e217648611260e7db26eb5703bedd` (before = after)
- `data/processed/attractions.csv`: `594934dc2c5a64b65628bb27e458ce07e32f98ee667ffb560ea787ba89a0c6c4` (before = after)
- `data/processed/restaurants.csv`: `f4143bdcba0bbe9f2cb686c53c456a21da027512d3722b8e0f4651738760d1bc` (before = after)
- `data/metadata/google_local_entity_registry.csv`: `353476becaf464b0610eadacc411601cfdf7738efe7f8430dabd0e010b8369e5` (before = after)
- `data/metadata/restaurant_id_registry.csv`: `696574d28676fe89d8d76ac14af7a876abdc5c526aa942945394bceb2a8d28cb` (before = after)
- `data/metadata/attraction_id_registry.csv`: `3a5ed6c7a8543df7571e9c05e4e133ce7e12b07b1122afdbbd29ca55b3bebb08` (before = after)
- `data/metadata/restaurant_review_id_registry.csv`: `984da922e6f52f871f1cf3987c8d764cbb56a096fc9a5d8096b6b6ae770ee898` (before = after)
- `data/metadata/attraction_review_id_registry.csv`: `492d783a15b0a69cd274afc9cbaa1856f35232f31996278885b0724579df60d8` (before = after)

All 61 previous report files remain byte-identical at their retained/moved locations. All 13 intermediates remain byte-identical. Reference searches found pipeline consumers, audit purposes or expensive-cache justification for each retained intermediate.

## Execution verification

- Docker build passed; docker compose config passed.
- Full unittest discovery with package-safe imports: 117 tests passed.
- All 18 production modules imported in Docker; root/configuration/raw/cache and relocated Google audit path checks passed.
- Both read-only notebooks executed successfully in Docker, with executed copies written to /tmp.
- No sys.path insertion remains in scripts/tests/notebooks.
- git diff --check passed.
- No commit or push.

## Changed files

Every move is recorded in the inventory. Additional created/updated files: root README; data/README; attraction_data_report; this verification; package __init__.py files; scripts/test imports and path constants; the two notebooks; path references in metadata documentation. Frozen data, registry and detailed audit bytes unchanged.

## Final git status --short

```
 M README.md
 M data/metadata/data_sources.md
 D data/reports/attraction_auto_curation_report.csv
 D data/reports/attraction_auto_curation_report.md
 D data/reports/attraction_curation_verification.md
 D data/reports/attraction_duplicate_alias_audit.csv
 D data/reports/attraction_finalization_verification.md
 D data/reports/commonplace_attraction_filter_report.md
 D data/reports/commonplace_candidate_name_review.csv
 D data/reports/commonplace_domain_samples.csv
 D data/reports/commonplace_domain_type_counts.csv
 D data/reports/commonplace_domain_type_crosstab.csv
 D data/reports/commonplace_exclude_supported_by_landmarks.csv
 D data/reports/commonplace_excluded_subtypes.csv
 D data/reports/commonplace_exploration_report.md
 D data/reports/commonplace_facility_domain_counts.csv
 D data/reports/commonplace_facility_type_counts.csv
 D data/reports/commonplace_include_supported_by_kaggle.csv
 D data/reports/commonplace_include_supported_by_landmarks.csv
 D data/reports/commonplace_included_subtypes.csv
 D data/reports/commonplace_kaggle_review_subtype_support.csv
 D data/reports/commonplace_near_duplicate_names.csv
 D data/reports/commonplace_review_resolution.md
 D data/reports/commonplace_review_resolution_with_landmarks.md
 D data/reports/commonplace_review_subtypes.csv
 D data/reports/commonplace_review_supported_by_kaggle.csv
 D data/reports/commonplace_review_supported_by_landmarks.csv
 D data/reports/commonplace_same_name_different_location.csv
 D data/reports/commonplace_same_name_same_location.csv
 D data/reports/commonplace_schema.csv
 D data/reports/commonplace_type_samples.csv
 D data/reports/final_attraction_curation.csv
 D data/reports/final_attraction_curation_manual.csv
 D data/reports/final_attraction_curation_report.md
 D data/reports/google_local_ambiguous_matches.csv
 D data/reports/google_local_attraction_matching.csv
 D data/reports/google_local_entity_matching_report.md
 D data/reports/google_local_gmap_id_collisions.csv
 D data/reports/google_local_matching_verification.md
 D data/reports/google_local_restaurant_matching.csv
 D data/reports/google_local_review_coverage.csv
 D data/reports/google_local_review_extraction.json
 D data/reports/kaggle_audit_verification.md
 D data/reports/kaggle_commonplace_ambiguous_matches.csv
 D data/reports/kaggle_commonplace_matching_report.csv
 D data/reports/kaggle_commonplace_matching_summary.csv
 D data/reports/kaggle_commonplace_name_only_candidates.csv
 D data/reports/kaggle_matches_commonplace_exclude.csv
 D data/reports/kaggle_tourist_locations_unmatched.csv
 D data/reports/kaggle_tourist_relevance_report.md
 D data/reports/landmark_audit.md
 D data/reports/landmark_commonplace_matching_report.csv
 D data/reports/landmark_commonplace_matching_summary.csv
 D data/reports/landmark_pipeline_verification.md
 D data/reports/landmarks_unmatched_commonplace.csv
 D data/reports/manual_price_category_check.csv
 D data/reports/osm_ambiguous_matches.csv
 D data/reports/osm_matching_report.csv
 D data/reports/review_corpus_verification.md
 M notebooks/explore_attractions.ipynb
 M notebooks/explore_restaurants.ipynb
 D scripts/audit_landmarks.py
 D scripts/build_attraction_curation.py
 D scripts/build_review_corpora.py
 D scripts/download_attractions.py
 D scripts/download_restaurants.py
 D scripts/download_restaurants_osm.py
 D scripts/download_review_corpus.py
 D scripts/download_reviews.py
 D scripts/explore_attractions.py
 D scripts/filter_attractions.py
 D scripts/finalize_attractions.py
 D scripts/google_local_matching.py
 D scripts/match_attractions_kaggle.py
 D scripts/osm_enrichment.py
 D scripts/preprocess_restaurants.py
 D scripts/resolve_attraction_review.py
 D scripts/restaurant_hours.py
 D scripts/restaurant_matching.py
 D tests/test_attraction_curation.py
 D tests/test_attraction_filter.py
 D tests/test_attraction_finalization.py
 D tests/test_attractions_exploration.py
 D tests/test_google_local_matching.py
 D tests/test_kaggle_attraction_matching.py
 D tests/test_landmark_audit.py
 D tests/test_osm_enrichment.py
 D tests/test_restaurant_hours.py
 D tests/test_restaurant_pipeline.py
 D tests/test_review_corpora.py
?? data/README.md
?? data/reports/attraction_data_report.md
?? data/reports/audit/
?? data/reports/repository_cleanup_inventory.csv
?? data/reports/verification/
?? scripts/__init__.py
?? scripts/attractions/
?? scripts/restaurants/
?? scripts/reviews/
?? scripts/shared/
?? tests/__init__.py
?? tests/attractions/
?? tests/restaurants/
?? tests/reviews/
?? tests/shared/
```
