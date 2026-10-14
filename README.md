# Agentic Travel Planner — Verification Ablations

This project studies verification in an agentic travel planner. The completed
restaurant, attraction and offline review pipelines supply the four frozen
application-facing datasets below. Other project stages are maintained separately.

| Dataset | Rows | Purpose |
| --- | ---: | --- |
| `data/processed/restaurants.csv` | 670 | Restaurant identity, location, prices, hours and cuisine evidence |
| `data/processed/attractions.csv` | 3,066 | Attraction identity/categories/provenance and conservative admission evidence |
| `data/processed/restaurant_reviews.csv` | 20,349 | Text evidence for 246 restaurants |
| `data/processed/attraction_reviews.csv` | 36,203 | Text evidence for 638 attractions |

Supporting tables for areas, weather and transport sit alongside them in
`data/processed/` (see [Area, weather, transport and accommodation data](#area-weather-transport-and-accommodation-data)):

| Dataset | Rows | Purpose |
| --- | ---: | --- |
| `data/processed/areas.csv` | 5 | Naive lookup of the five NYC boroughs (`area_id` primary key) with bounding boxes |
| `data/processed/weather.csv` | 1,825 | Daily 2025 weather per borough; a 4-season, 14-day window sample (280 rows) can be taken from it, see below |
| `data/processed/transport_modes.csv` | 4 | Naive fare table for walking, bus, subway and taxi |
| `data/processed/accomodation.csv` | 365 | Hotels with location, rating, stars, price and amenities (work in progress, see below) |

**Application/tool code should consume only files in `data/processed/`.**
Raw/interim datasets exist for reproducibility and provenance, and metadata holds
pipeline configuration and persistent identity registries.

## Navigation

- `scripts/{restaurants,attractions,reviews}/`: production construction modules.
- `scripts/shared/`: shared entity normalization and geographic matching helpers.
- `tests/{restaurants,attractions,reviews}/`: existing regression coverage.
- `data/metadata/`: stable source/rule/schema documentation and persistent registries.
- `data/reports/`: generated on demand by pipeline commands, ignored by Git and not tracked. This directory may be absent until a pipeline runs.

See [data/DATA_CATALOG.md](data/DATA_CATALOG.md) for lineage, policies and artifact locations.
Do not delete/reset ID registries or change source snapshots when reproducing the
frozen outputs. Production never reads reports. Reproduction checkpoints live in `data/interim/`;
reports can be removed without affecting construction.

## Local setup and tests

The diagram's nine sandbox table models and workflow compatibility rules are
documented in [Schema alignment](docs/SCHEMA_ALIGNMENT.md).

For the importable recovery controller, offline tests, synthetic demonstration,
saved-plan experiment runner and scorer, see [Recovery and evaluation](docs/RECOVERY.md).
For a beginner-friendly file-by-file explanation, VS Code terminal commands and
a runnable offline notebook cell, see [Component walkthrough](docs/COMPONENT_WALKTHROUGH.md).
That guide includes Windows PowerShell commands using the existing parent `.venv`.
Docker is optional for this work; LangGraph does not require Docker.

Use Python 3.13 (validated with 3.13.6) from the repository root. Install and run
with the same interpreter:

```sh
python3 -m pip install -r requirements.txt
python3 -c "import shapely; print(shapely.__version__)"
python3 -m pytest
```

`requirements.txt` is the authoritative dependency source for local setup and
Docker, including Shapely 2.2.0 and pytest 8.4.2. Shapely 2.2.0 supports Python
3.13. Missing geometry dependencies must be installed; tests are not skipped.
An optional virtual environment can be created with `python3 -m venv .venv` and
activated with `source .venv/bin/activate` before the commands above.

## Docker and tests

Use the existing Docker service and repository bind mount:

```sh
docker compose build
docker compose config
docker compose run --rm data-pipeline python -m pytest
```

Run modules from the repository root with `python -m`; direct file execution is
superseded by package-safe module commands. Downloads reuse cached sources where
supported. Refresh flags intentionally change snapshots and are not part of a
frozen-output reproduction.

## Restaurant pipeline

Google Maps Kaggle supplies identity/location/ratings and ordinal prices.
OSM/Overpass adds optional hours, cuisine and explicit dietary evidence.
For a fresh construction workspace, initialize the core table first with
`python -m scripts.restaurants.preprocess_restaurants`, preserving the existing ID
registry. Then fetch cached OSM data and enrich as below. The initializer refuses
to overwrite an already enriched table; existing frozen installations only need
`--enrich-osm`. Rebuild from raw in a separate workspace, not over consumed outputs.

```sh
docker compose run --rm data-pipeline python -m scripts.restaurants.download_restaurants
docker compose run --rm data-pipeline python -m scripts.restaurants.download_restaurants_osm
docker compose run --rm data-pipeline python -m scripts.restaurants.preprocess_restaurants --enrich-osm
```

The numeric price mapping is experimental: 1 → $10–20, 2 → $20–40,
3 → $40–100, 4 → $100+; category 4 has no upper bound and missing categories
remain missing. Default hours are experimental fallbacks, not verified schedules.
See [data catalog](data/DATA_CATALOG.md) and
[restaurant schema](data/metadata/restaurant_schema.md).

## Attraction pipeline

NYC CommonPlace supplies the base universe; Kaggle tourist locations and NYC LPC
individual/scenic landmarks supply audited supporting evidence. Deterministic
rules finalize the preserved shortlist without requiring manual curation.

```sh
docker compose run --rm data-pipeline python -m scripts.attractions.download_attractions
docker compose run --rm data-pipeline python -m scripts.attractions.download_attractions --source kaggle
docker compose run --rm data-pipeline python -m scripts.attractions.download_attractions --source landmarks
docker compose run --rm data-pipeline python -m scripts.attractions.explore_attractions
docker compose run --rm data-pipeline python -m scripts.attractions.filter_attractions
docker compose run --rm data-pipeline python -m scripts.attractions.match_attractions_kaggle
docker compose run --rm data-pipeline python -m scripts.attractions.audit_landmarks
docker compose run --rm data-pipeline python -m scripts.attractions.build_attraction_curation
docker compose run --rm data-pipeline python -m scripts.attractions.finalize_attractions
docker compose run --rm data-pipeline python -m scripts.attractions.download_admission_sources
docker compose run --rm data-pipeline python -m scripts.attractions.enrich_admission_costs
```

See [data catalog](data/DATA_CATALOG.md) and
[attraction sources](data/metadata/attractions_sources.md). Source taxonomy,
filtering/alias configuration remains in metadata; candidate and matching checkpoints
live in `data/interim/`. Manual curation is not required.

Admission enrichment reads checksum-verified OSM/Wikidata snapshots offline, keeping
unknown prices null. The initial snapshot has status evidence for 29/3,066 attractions
and exact prices for 10/3,066 (all free). No positive ticket price is invented.
See [admission schema, source hierarchy and budget policy](data/metadata/attraction_admission.md).
An optional `--report data/reports/attraction_admission_coverage.json` writes an
on-demand, Git-ignored coverage report. Fetch once explicitly; skip downloads for
cached reproduction. Source-backed admission is separate from incidental spending,
whose hard-budget default is zero unless the user specifies an allowance.

## Google Local matching and review corpora

[Google Local Reviews (2021), UCSD McAuley Lab](https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/)
is historical evidence through September 2021, intentionally frozen for offline
subjective-constraint experiments. Only the 887 accepted HIGH-confidence entity
mappings feed review extraction; ambiguous/shared Google IDs are quarantined.

```sh
docker compose run --rm data-pipeline python -m scripts.reviews.download_reviews
docker compose run --rm data-pipeline python -m scripts.reviews.google_local_matching
docker compose run --rm data-pipeline python -m scripts.reviews.download_review_corpus
docker compose run --rm data-pipeline python -m scripts.reviews.build_review_corpora
```

With the accepted Google registry already present, the minimal review rebuild is
`python -m scripts.reviews.build_review_corpora`; both review files are built together.
The metadata-download/matching commands above are only needed to rebuild the accepted
Google mappings. On a cached installation the minimal attraction rebuild is
`python3 -m scripts.attractions.finalize_attractions` followed by
`python3 -m scripts.attractions.enrich_admission_costs`; the preceding commands rebuild
its checkpoints from raw sources. Enrichment does not modify benchmark artifacts or registries.

A single streaming scan of the full New York split writes an identity-free,
disk-backed SQLite interim cache. Repeated corpus builds validate source/registry
hashes and reuse that cache. Text corpora retain at most 100 unique reviews per
entity: 60 most recent plus 40 historical reviews selected across rating strata
using seed 42. Up to 100 unique text reviews are all retained. This is not a
statistically representative sample. Persistent RR_/AR_ registries preserve IDs.

No reviewer identities or subjective scores/labels are derived. Missing mapping or
zero text reviews means **UNKNOWN / evidence unavailable**, never negative evidence.
See [data catalog](data/DATA_CATALOG.md) and
[review schema/policy](data/metadata/review_corpus_schema.md).

## Area, weather, transport and accommodation data

These four tables are built by hand or in notebooks (`scripts/weather/`, `scripts/accoms/`), not
by the `python -m` pipelines above, and are not covered by the frozen-output guarantees. The
notebooks use absolute paths from one team member's checkout, so edit them before re-running
elsewhere, and need `pandas` and `pyarrow` (for the parquet read). `data/raw/` is not tracked
in Git, so the raw inputs must be shared separately.

| Output | Built from | How |
| --- | --- | --- |
| `data/processed/areas.csv` | Chosen borough list and bounding boxes | Written by hand; no script (`scripts/naives_/area.ipynb` is an empty placeholder) |
| `data/processed/transport_modes.csv` | Assumed fares | Written by hand; no script |
| `data/processed/weather.csv` | `data/raw/{Bronx,Brooklyn,Manhattan,Queens,Staten} all year.csv` | `scripts/weather/weather_processing.ipynb` |
| `data/processed/accomodation.csv` | `data/raw/hotels.parquet`, `data/raw/accomodations_manhatten.csv` | `scripts/accoms/processing.ipynb` |

### Areas

The lookup of the five boroughs we have data for: `area_id` is the primary key (1 Manhattan,
2 Brooklyn, 3 Queens, 4 Bronx, 5 Staten Island), plus `area_name` and a rough rectangular
bounding box per borough. The boxes overlap and are not borough boundaries. The box column
headers are mislabeled: values are south-latitude, west-longitude, north-latitude,
east-longitude, not longitude/latitude as the header says. Other tables store the borough
name, not `area_id` (`weather.csv` and `accomodation.csv` use `area`), so join on name.
`weather_processing.ipynb` numbered the boroughs differently in an earlier draft (Bronx 2,
Brooklyn 3, Queens 4), so do not reuse ids from there.

### Transport modes

One hand-written row per mode, in USD: `walking` is free; `bus` and `subway` are a flat $3.00
per trip; `taxi` is a $3.00 base fare plus about $2.17 per km (the yellow-cab rate of $0.70
per fifth of a mile). `vehicle_capacity` is a rough number, blank for walking. Surcharges,
tolls, tips and waiting time are ignored, and the rates come from memory rather than a checked
MTA/TLC source, so treat them as naive approximations.

### Weather

The design is a four-season sample: one 14-day window per season, meant to stand in for typical
conditions in each borough and season rather than a full calendar. The windows are 8-21 May
(spring), 8-21 June (summer), 8-21 October (autumn) and 8-21 December (winter). The raw inputs
are five per-borough daily weather exports for 2025 (Open-Meteo archive format). The notebook
tags each with its `area`, concatenates them, drops `weather_code`, renames columns to a
common schema (`time` to `date`, `rain_sum` to `rainfall`, and so on) and writes
`data/processed/weather.csv`. Columns: date, max/min/mean temperature (°C), precipitation sum
(mm), rainfall (mm), precipitation hours, maximum wind speed (km/h) and `area`.

**The season filter is not applied to the saved file yet.** The notebook builds the 280-row
sample (4 windows x 14 days x 5 areas) in a `seasonal` DataFrame, but `weather.csv` is still
written from the full-year data, so it has 1,825 rows (365 days x 5 areas) and an unnamed
leading index column. The filter is kept for later tooling; filter `weather.csv` to the four
windows (combined with `|`) before using it as seasonal weather.

### Accommodations

Two sources are merged, and every gap is filled, so the table has no missing values.
1. *Google parquet* (`hotels.parquet`, 1,093 hotels across New York State): drop identifier,
   contact, link, photo, owner and data-quality columns, keep rows whose `city` is one of the
   five boroughs (242 rows) and rename `city` to `area`. This filter loses nearly all Manhattan
   and Queens hotels, because the parquet labels Manhattan `New York` and most of Queens by
   neighborhood.
2. *Manhattan export* (`accomodations_manhatten.csv`, 124 hotels from a booking site), added to
   fix that imbalance: columns are renamed to the parquet schema (`overallScore` halved into
   `rating`, `reviewCount` into `review_count`, `city` mapped to `area`) and columns with no
   equivalent are dropped. It has no address, zipcode, price or amenities, so those are random,
   seeded values (seed 42) that rise with `hotel_stars`; street numbers do not point to real
   buildings.
3. *Gap filling for the parquet rows* (rating is the anchor): missing `hotel_stars` come from
   a linear fit on rating, `price_usd` from a log-price regression on stars, rating and borough,
   and `rating` from stars or the borough median. `district` is copied from the nearest hotel,
   `review_count` is a random draw that rises with stars, `description` is a sentence built
   from the row's own columns, and extra amenity flags are added at star-based chances.
4. A hotel in both sources (within about 25 m) is kept once, from the parquet.

The result has 365 rows (Brooklyn 154, Manhattan 123, Bronx 67, Staten Island 14, Queens 7)
and no index column. Observed values are never changed, but many fields are synthetic: do not
use the filled addresses, prices, review counts or amenities as real facts. Ratings and review
counts come from different platforms, so treat them as only roughly comparable. Queens is
still thin until its neighborhoods are mapped to the borough.

## Benchmark specification

[data/benchmark/README.md](data/benchmark/README.md) documents the fixed-NYC constraint
catalog and semantic-case schema, including current versus future data support and
collective coverage requirements. The 60 structured semantic cases use seed 42 and explicitly tagged benchmark-only assumptions
for planned flight, accommodation, transport and budget domains; real support flags remain unchanged.
The frozen naturalized wording benchmark is `data/benchmark/prompt_variants_naturalized.jsonl`:
180 prompts (three styles per semantic case), with human-readable entity names and hidden IDs.
`semantic_cases.jsonl` retains canonical IDs and exact values. The case/prompt manifests
contain 60/180 rows respectively. Experiments read frozen prompts and never regenerate them.
Generate with `python3 -m scripts.benchmark.generate_prompt_variants` and validate with
`python3 -m scripts.benchmark.validate_prompt_variants`.
Regenerate with `python3 -m scripts.benchmark.generate_semantic_cases` and validate with
`python3 -m scripts.benchmark.validate_semantic_cases`.
