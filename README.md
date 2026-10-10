# Agentic Travel Planner — Verification Ablations

The finalized restaurant table is `data/processed/restaurants.csv`: **670 canonical
restaurants**, with frozen IDs, row order and 15 core fields. Google Maps Kaggle
supplies identity, location, ratings and price categories. Optional OSM/Overpass
supplies opening/kitchen hours, cuisine and explicit dietary tags.

## Application-facing restaurant data

**`data/processed/restaurants.csv` is the sole application-facing restaurant
CSV and the single source of truth for downstream restaurant code.** Future
`search_restaurants`, `filter_restaurants`, `check_restaurant_budget` and
`check_restaurant_hours` functions must load this processed file.

Downstream application code must not depend directly on `data/raw/` or
`data/interim/`. Those files are preprocessing inputs and audit artifacts only;
metadata configures regeneration and the calendar evidence helper.

## Run the restaurant pipeline

```bash
docker compose build
docker compose config
docker compose run --rm data-pipeline python scripts/download_restaurants.py
docker compose run --rm data-pipeline python scripts/download_restaurants_osm.py
docker compose run --rm data-pipeline python scripts/preprocess_restaurants.py --enrich-osm
docker compose run --rm data-pipeline python -m unittest discover -s tests -v
```

Downloaders reuse existing raw inputs. Supply `--refresh` explicitly to download
again; the OSM downloader also accepts `--endpoint URL`. Kaggle credentials stay
outside the repository; Compose mounts `~/.kaggle` read-only. Raw data and caches
remain ignored by Git and Docker. Cached OSM preprocessing works offline, and
failed retrieval preserves previous data and reports.

The finalized CSV is included for frozen enrichment. If bootstrapping an empty
processed directory, run `python scripts/preprocess_restaurants.py` in Docker
before downloading OSM. This cleans Kaggle data and reuses the retained ID
registry. The base-only command refuses to overwrite an enriched table.
Retain `data/metadata/restaurant_id_registry.csv` to reproduce existing IDs.

Native use: install `requirements.txt`, then run the same Python commands.
The single requirements file pins active direct dependencies; tests use unittest
and Overpass uses the Python standard library.

## Data policy

Manual inspection of representative Google Maps URLs established an approximate,
**experimental per-person price mapping**: 1 → $10–20, 2 → $20–40,
3 → $40–100, 4 → $100+. The metadata CSV is the single source of truth.
Missing categories stay null, category 4 has no upper bound, and no meal-cost
estimate is defined. These ranges are not exact real-world price guarantees.

OSM matches require conservative name/location evidence; competing plausible
matches stay ambiguous. Raw tags remain verbatim, kitchen hours stay separate,
and dietary values are never inferred from cuisine. OSM is community-maintained
and may be incomplete or stale.

Missing general hours receive **11:00–22:00 daily** as a controlled experimental
assumption, clearly marked `experimental_default` and `opening_hours_is_assumed`.
Observed OSM schedules are never replaced. Effective hours are typed JSON:
weekly intervals for defaults, verbatim OSM syntax for observations. A complete
OSM schedule parser is not supplied.

The static **2026** federal holiday calendar includes actual and separately
labelled observed dates. A holiday flag does not imply restaurant closure.
Only explicit OSM PH rules supply holiday behaviour; unsupported expressions
remain UNKNOWN, and defaults remain ASSUMED. `restaurant_hours.resolve_hours`
returns evidence for a restaurant/date, without verifier result labels.
Dates outside the configured year fail explicitly.

## Review and extend

- [Main data report](data/reports/restaurant_data_report.md): counts, coverage and integrity checks.
- [Sources](data/metadata/data_sources.md): provenance and calendar scope.
- [Schema](data/metadata/restaurant_schema.md): fields, matching and hours semantics.
- `data/interim/osm_restaurants_clean.csv` and `osm_restaurant_enrichment.csv`: OSM audit tables.
- `data/reports/osm_matching_report.csv` and `osm_ambiguous_matches.csv`: candidate review.
- `data/reports/manual_price_category_check.csv`: retained manual price observations; never overwritten automatically.
- `notebooks/explore_restaurants.ipynb`: overview, missingness, price samples and enrichment coverage.

Only Google Maps and OSM raw restaurant folders are retained. No attractions
pipeline is implemented yet.

## CommonPlace attractions exploration

This stage explores only [NYC Open Data CommonPlace](https://data.cityofnewyork.us/City-Government/CommonPlace/t95h-5fsr).
It creates no final attraction IDs, categories or processed attractions table,
and does not merge other sources or change restaurant data.

```bash
docker compose build
docker compose config
docker compose run --rm data-pipeline python scripts/download_attractions.py
docker compose run --rm data-pipeline python scripts/explore_attractions.py
docker compose run --rm data-pipeline python -m unittest discover -s tests -v
```

Open `notebooks/explore_attractions.ipynb` in Jupyter, or execute it in Docker:

```bash
docker compose run --rm data-pipeline jupyter nbconvert --to notebook --execute \
  --inplace notebooks/explore_attractions.ipynb
```

The downloader caches the official CSV/API schema, source dictionary and retrieval
metadata in ignored `data/raw/attractions/commonplace/`; `--refresh` explicitly
downloads again. Offline exploration writes `data/interim/commonplace_attractions_clean.csv`,
source taxonomy metadata and frequency/sample/duplicate reports. The notebook
adds bar charts and a coordinate scatter using matplotlib in the existing environment.

Read `data/reports/commonplace_exploration_report.md` and
`data/metadata/attractions_sources.md`. Facility-domain codes depend on facility
type; source-documented labels are decoded without inventing missing meanings.
Tourism keyword subsets are labelled exploration candidates, not final selection
rules. Raw/interim CommonPlace files are exploration artifacts, not an additional
application-facing restaurant dataset.

### First taxonomy-based attraction candidate universe

```bash
docker compose run --rm data-pipeline python scripts/filter_attractions.py
```

`data/metadata/commonplace_attraction_filter.csv` is the single rule source,
joined by facility type and type-dependent domain code. Its provisional decisions
are INCLUDE, EXCLUDE and REVIEW. Absent pairs become UNMAPPED; REVIEW is never
silently promoted. The undocumented type 13/domain 5 remains
UNKNOWN_UNDOCUMENTED and REVIEW. Names do not determine inclusion.

The filter writes classified, candidate, review and unmapped interim CSVs.
`data/reports/commonplace_attraction_filter_report.md` and the included/excluded/
review subtype audit CSVs show counts, reasons and seeded examples. Candidate
name flags are exploratory and do not remove rows. The notebook visualizes the
policy's consequences. No final attraction IDs, deduplication, source merges or
`data/processed/attractions.csv` are created yet.

### Kaggle tourist-relevance audit

The curated [348 New York Tourist Locations](https://www.kaggle.com/datasets/anirudhmunnangi/348-new-york-tourist-locations) list is an audit signal, not a canonical source. The actual workbook `New_York_Tourist_Locations.xlsx` contains 347 rows with `Tourist_Spot`, `Address`, and `Zipcode`. Raw files and retrieval metadata stay in the ignored `data/raw/attractions/kaggle_tourist_locations/` directory. The existing Kaggle credential mount is reused.

```sh
docker compose run --rm data-pipeline python scripts/download_attractions.py --source kaggle
docker compose run --rm data-pipeline python scripts/match_attractions_kaggle.py
```

The downloader validates and reuses cached files; `--refresh` requests another download. Cleaning preserves original values and source row references. Matching reuses shared name/address normalization and requires matching ZIP, exact normalized address, or very close coordinates alongside name evidence. Fuzzy matching defaults to 0.94 (`--fuzzy-threshold`). EXCLUDE is searched only as a separate diagnostic for primary UNMATCHED rows; `--no-exclude-diagnostic` disables it. Ambiguous candidates and competing aliases require manual review.

CommonPlace currently has coordinates but no addresses/ZIPs, while Kaggle has addresses/ZIPs but no coordinates. Therefore the current snapshot yields zero geographically confirmed matches, with name-only candidates saved separately. This does **not** establish zero source overlap or deficient CommonPlace coverage. The audit cannot identify supported REVIEW subtypes until comparable location evidence is available.

See `data/reports/kaggle_tourist_relevance_report.md` for schema, duplicates, missingness, status counts, subtype support and examples; `kaggle_commonplace_matching_summary.csv` counts each Kaggle row once, while the full matching report contains candidate pairs and diagnostic passes. The unmatched file includes all rows without an accepted INCLUDE/REVIEW match, including ambiguous and rejected rows. Audit signals live in a separate interim copy, `commonplace_kaggle_tourist_signal.csv`; a false signal means no accepted match. The notebook includes the audit and its limitations. Existing decisions and canonical restaurant data remain unchanged; this workflow creates no final attraction IDs or `data/processed/attractions.csv`.

### LPC landmark audit and REVIEW resolution

```sh
docker compose build
docker compose config
docker compose run --rm data-pipeline python scripts/download_attractions.py --source landmarks
docker compose run --rm data-pipeline python scripts/resolve_attraction_review.py
docker compose run --rm data-pipeline python scripts/filter_attractions.py
docker compose run --rm data-pipeline python scripts/audit_landmarks.py
docker compose run --rm data-pipeline jupyter nbconvert --to notebook --execute --inplace notebooks/explore_attractions.ipynb
docker compose run --rm data-pipeline python -m unittest discover -s tests
```

`--source individual` and `--source scenic` also download each source separately; caches are checksum-validated, with `--refresh` for new snapshots. Only NYC Open Data Individual Landmark Sites (`buis-pvji`) and Scenic Landmarks (`qexa-qpj6`) are added. Raw exports/schema/retrieval metadata stay ignored under `data/raw/attractions/landmarks/{individual,scenic}/`. The larger historic-district building database is not used.

The subtype proposal report covers all configured REVIEW pairs before application. All remain REVIEW because inspected subtypes mix visitor destinations with ordinary, inaccessible or constituent facilities; no whole-subtype change met the confidence requirement. The existing rule CSV remains the only classification authority. Landmark-supported individual records receive a selective-review recommendation, without automatic promotion.

Individual status comes from `lpc_sitest`; current and last-action flags are absent, so designated eligibility is reported with currency unverified. Scenic eligibility requires `current_=true`, `status=DESIGNATED` and no conflicting inactive/calendared/rescinded action. Clean tables preserve all records and status groups.

Both Socrata exports retain EPSG:2263 projected geometry, while the Shapefile `.prj` incorrectly labels it WGS84. Cached LPC spatial-reference metadata resolves this conflict; scenic polygon extents are checked against LPC geometry explicitly requested in EPSG:2263, and transformed individual polygons are checked against source geographic coordinates. Representative points lie in/on the geometry, with repairs recorded. Matching requires name and location evidence: within 50 m, exact names within 150 m, or polygon containment for large sites. Multiple plausible records remain ambiguous.

See `commonplace_review_resolution.md`, `landmark_audit.md`, and `commonplace_review_resolution_with_landmarks.md` in `data/reports/`. Matching summary counts source rows once; matching report exposes candidate pairs. Dedicated INCLUDE/REVIEW/EXCLUDE support files and unmatched-landmark inspection records support later decisions. Keywords do not imply attraction suitability. The notebook shows status, subtype support and borough charts. Restaurant files and the existing weak/manual Kaggle audit remain preserved. No final IDs, processed attractions CSV or source union are created.

### Preserved attraction shortlist (historical evidence)

```sh
docker compose run --rm data-pipeline python scripts/build_attraction_curation.py
```

This historical shortlist is preserved; the deterministic finalization workflow below supersedes its blank manual fields and requires no manual review. The full evidence table is `final_attraction_curation.csv`, with selection rules/counts and limitations in `final_attraction_curation_report.md`. The shortlist includes all landmark-supported CommonPlace REVIEW/EXCLUDE rows, all unmatched scenic landmarks, and at most 200 deterministically ranked unmatched/rejected individual landmark candidates. Keyword, institutional-name and address signals aid review; they do not establish public access or tourist suitability. Explicit service-infrastructure signals and private-residence wording without institutional signals are screened out of the optional individual subset. The ranking/cap follows conservative source/name/location deduplication.

Temporary `CUR_` IDs are review references, not final attraction IDs. Possible INCLUDE aliases include nearby similar names or named constituent features inside landmark polygons; they require manual identity review. Kaggle name support remains weak/unconfirmed and never creates candidates on its own.

All generated `manual_decision`, `manual_reason`, and `manual_notes` fields start blank. Intended decision vocabulary: `ADD`, `DO_NOT_ADD`, `ALIAS_OF_EXISTING`, `NEEDS_REVIEW`. Edit the compact manual file; join back to the full evidence file by `curation_candidate_id`. The builder refuses to overwrite populated manual fields in either output. Rebuilding from changed source snapshots may shift temporary IDs, so retain the matching full evidence file when reviewing. No automatic additions or final union are performed. Existing CommonPlace decisions, 2,901 automatic candidates, restaurant files and previous audits stay unchanged.

### Final deterministic attraction pipeline

```sh
docker compose build
docker compose config
docker compose run --rm data-pipeline python scripts/finalize_attractions.py
docker compose run --rm data-pipeline jupyter nbconvert --to notebook --execute --inplace notebooks/explore_attractions.ipynb
docker compose run --rm data-pipeline python -m unittest discover -s tests
```

The application-facing output is **`data/processed/attractions.csv`**. All 2,901 CommonPlace INCLUDE source rows are retained, alongside shortlist candidates assigned `ADD`. `DO_NOT_ADD` and `ALIAS_OF_EXISTING` never create additional rows. Manual decisions and `NEEDS_REVIEW` are not required. The old shortlist remains read-only evidence.

`data/metadata/attraction_auto_curation_rules.csv` defines positive/negative visitor signals and scoped rules. Exact type/domain categories live in `attraction_category_mapping.csv`. Unique exact/near-exact name plus close location evidence resolves aliases first; earlier low-threshold alias/constituent suggestions are not automatically accepted. Scenic designations and confidently landmark-supported REVIEW rows are retained subject to the documented policy. Supported EXCLUDE and unmatched Individual candidates need explicit positive signals; negative conflicts default to exclusion. Kaggle evidence remains provenance only. Visitor suitability/public access is not guaranteed by these experimental rules.

`attraction_id_registry.csv` persists source-key → `ATTR_` mappings. Reruns retain IDs, new source keys append, and inactive keys remain reserved. Do not delete/reset the registry after IDs have been consumed. No ratings, prices or hours are inferred. Source taxonomy, original CommonPlace decisions, landmark references and rule provenance remain in the final table.

`data/reports/attraction_auto_curation_report.csv` and its Markdown summary explain every shortlist decision. `attraction_duplicate_alias_audit.csv` retains alias/duplicate provenance; retained rows also preserve landmark evidence. Existing base duplicates remain because every automatic INCLUDE identity is required; additions undergo conservative source/name/location checks. Restaurant data and prior source audits remain unchanged.

### Google Local 2021 metadata matching for future reviews

Review source: [Google Local Reviews (2021), UCSD McAuley Lab](https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/). Snapshot coverage is through September 2021. It is intentionally frozen as a fixed offline review corpus for experimental subjective-constraint evaluation.

```sh
docker compose build
docker compose config
docker compose run --rm data-pipeline python scripts/download_reviews.py
docker compose run --rm data-pipeline python scripts/google_local_matching.py
docker compose run --rm data-pipeline python -m unittest discover -s tests
```

Only the **complete New York business metadata** is downloaded; the official index determines its actual filename. Gzip JSON lines are streamed into a geographic candidate table with disk-backed schema/duplicate counters. The canonical `restaurants.csv` and `attractions.csv` are the only application entities; their coordinates establish a padded matching region. Some canonical restaurants have New Jersey addresses, so the New York-only split can limit coverage. No entity tables are edited.

`data/metadata/google_local_entity_registry.csv` contains only unambiguous HIGH-confidence entity → gmap_id associations. The restaurant/attraction audits include every canonical entity; ambiguous candidate pairs and shared-gmap_id conflicts are separate reports. `google_local_entity_matching_report.md` documents thresholds, field quality, method/category coverage and diagnostic limitations. Shared Google representations are quarantined for all claimants; parent/constituent attractions are not collapsed by proximity alone. Existing registry assignments cannot silently change on rerun.

No full review file is downloaded or extracted at this stage, and no processed review CSVs are created. A later streaming extractor will use accepted gmap_ids and retain rating, review text, timestamp/date and entity_id; reviewer names and profiles are unnecessary downstream.

### Offline Google Local review corpora

Build only from the frozen HIGH-confidence entity registry:

```sh
docker compose build
docker compose config
docker compose run --rm data-pipeline python scripts/download_review_corpus.py
docker compose run --rm data-pipeline python scripts/build_review_corpora.py
docker compose run --rm data-pipeline python -m unittest discover -s tests
```

The complete New York Google Local 2021 review split is cached under ignored
`data/raw/reviews/google_local_2021/`. A single gzip JSONL pass filters the 887
accepted Google IDs into `data/interim/google_local_matched_reviews.sqlite`.
The rebuildable SQLite cache is Git-ignored and excluded from Docker image
contexts; Docker accesses it through the existing repository volume.
SQLite provides a disk-backed, bounded-memory interim representation without
adding a Parquet dependency. Completed extraction is reused only when the raw
SHA-256 and entity-registry SHA-256 match its provenance. Use `--reextract` to
explicitly rebuild this interim cache.

Processed `restaurant_reviews.csv` and `attraction_reviews.csv` contain only
non-empty, conservatively whitespace-normalized text. UTC epoch-millisecond
conversion supplies dates; exact content/rating/timestamp duplicates are removed.
The maximum is 100 text reviews per entity: 60 most recent plus 40 historical
reviews selected across available ratings using deterministic SHA-256 ranks
seeded with 42. Up to 100 unique text reviews are all retained. Persistent `RR_`
and `AR_` key registries retain prior IDs when selection changes.

This is historical evidence through September 2021, intentionally frozen for
reproducibility and bounded retrieval cost, not a statistically representative
sample or current business evidence. Missing mapping or zero text reviews means
UNKNOWN / evidence unavailable, never negative evidence about a subjective
constraint. No subjective labels are derived here. Reviewer names, user IDs,
profiles, photos and responses are omitted from interim and processed tables.
Source reviews remain unmodified in the ignored raw cache.

See `data/reports/review_dataset_summary.md`, the separate restaurant/attraction
review reports, `google_local_review_coverage.csv`, and extraction provenance JSON
for source counts, deduplication, sampling and actual text coverage. Counts before
deduplication are distinguished from unique and sampled counts. Canonical entity
tables and the accepted Google entity registry remain frozen.
