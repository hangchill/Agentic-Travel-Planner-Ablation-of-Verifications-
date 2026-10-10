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
| `data/processed/weather.csv` | 1,825 | Daily 2025 historical weather per borough (365 days × 5 areas) |
| `data/processed/transport_modes.csv` | 4 | Naive fare table for walking, bus, subway and taxi |

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

These tables are built by hand or in notebooks (`scripts/weather/`, `scripts/accoms/`), not by
the `python -m` pipelines above, and are not covered by the frozen-output guarantees. Paths in
the notebooks are absolute and point at one team member's checkout, so edit them before
re-running elsewhere. The notebooks need `pandas` (pinned in `requirements.txt`) and `pyarrow`
(for the parquet read), which are not both guaranteed by `requirements.txt`.

### Pipeline

| Output | Built from | How |
| --- | --- | --- |
| `data/processed/areas.csv` | Hand-chosen borough list and bounding boxes | Written by hand as a static CSV; no script (`scripts/naives_/area.ipynb` is an empty placeholder) |
| `data/processed/transport_modes.csv` | Assumed fares (see below) | Written by hand as a static CSV; no script |
| `data/processed/weather.csv` | `data/raw/{Bronx,Brooklyn,Manhattan,Queens,Staten} all year.csv` | `scripts/weather/weather_processing.ipynb` |
| `data/processed/accomodation.csv` (planned) | `data/raw/hotels.parquet` | `scripts/accoms/processing.ipynb`; the notebook writes it, but the file has not been generated yet |

**Weather.** The raw inputs are five per-borough daily weather exports for 2025 (Open-Meteo
archive format, one `<Borough> all year.csv` each, kept in the untracked `data/raw/`). The
notebook:
1. reads the five files and tags each with an `area` column (Bronx, Brooklyn, Manhattan,
   Queens, Staten Island);
2. concatenates them and drops `weather_code (wmo code)`;
3. renames `time` to `date`, `temperature_2m_max/min` to `temperature_max/min`, and
   `rain_sum` to `rainfall`, and parses `date`;
4. writes `data/processed/weather.csv` with the default pandas index, so the file has an
   unnamed leading index column.

The notebook also contains a seasonal-window filter (spring, summer, autumn, winter, 14 days
each). It is not applied: the result is never assigned and the conditions are combined with
`&`, so the filter would match nothing. `weather.csv` therefore holds all 365 days per borough
(1,825 rows). It contains a few column-name encoding issues (the degree sign in the `°C`
headers) that can show as garbled characters depending on the reader.

**Areas.** `area_id` is the primary key (1 Manhattan, 2 Brooklyn, 3 Queens, 4 Bronx, 5 Staten
Island), with a rough rectangular bounding box per borough (south/west/north/east corners).
The boxes overlap and are not borough boundaries. The box column headers in the file are
mislabeled: values are in south-latitude, west-longitude, north-latitude, east-longitude order,
not longitude/latitude as the header says. `weather.csv` stores the borough name in `area`
rather than `area_id`, so join on `area_name`.

**Transport.** One row per mode, in USD. `walking` is free; `bus` and `subway` are a flat
$3.00 per trip; `taxi` is a $3.00 base fare plus about $2.17 per km (yellow-cab rate of $0.70
per fifth of a mile). `vehicle_capacity` is a rough value and blank for walking. Surcharges,
tolls, tips and waiting time are ignored, and the rates come from memory rather than a checked
MTA/TLC source.

**Accommodations.** `data/raw/hotels.parquet` has 1,093 hotels across New York State
(address, `district`, `city`, coordinates, rating, stars, price, amenities). The notebook:
1. drops identifier, contact, link, photo, owner and data-quality columns;
2. keeps rows whose `city` is Bronx, Queens, Staten Island, Manhattan or Brooklyn;
3. renames `city` to `area` and writes `data/processed/accomodation.csv` (note the spelling).

That `city` filter is a work in progress: in the raw data most Manhattan hotels are labelled
`New York` and most Queens hotels are labelled by neighborhood (Jamaica, Flushing, Long Island
City and so on), so the filter keeps few Manhattan and Queens rows until those values are mapped
to boroughs. The output also keeps the default pandas index column. Treat the accommodations
table as not yet ready for application use. `data/raw/` is not tracked in Git, so teammates
need the raw files shared separately.

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
