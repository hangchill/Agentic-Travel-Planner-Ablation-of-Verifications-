# Agentic Travel Planner — Verification Ablations

This project studies verification in an agentic travel planner. The completed
restaurant, attraction and offline review pipelines supply the four frozen
application-facing datasets below. Other project stages are maintained separately.

| Dataset | Rows | Purpose |
| --- | ---: | --- |
| `data/processed/restaurants.csv` | 670 | Restaurant identity, location, prices, hours and cuisine evidence |
| `data/processed/attractions.csv` | 3,066 | Attraction identity, categories and source provenance |
| `data/processed/restaurant_reviews.csv` | 20,349 | Text evidence for 246 restaurants |
| `data/processed/attraction_reviews.csv` | 36,203 | Text evidence for 638 attractions |

**Application/tool code should consume only files in `data/processed/`.**
Raw/interim datasets exist for reproducibility and provenance, and metadata holds
pipeline configuration and persistent identity registries.

## Navigation

- `scripts/{restaurants,attractions,reviews}/`: production construction modules.
- `scripts/shared/`: shared entity normalization and geographic matching helpers.
- `tests/{restaurants,attractions,reviews}/`: existing regression coverage.
- `data/metadata/`: stable source/rule/schema documentation and persistent registries.
- `data/reports/`: final summaries; `audit/{restaurants,attractions,reviews}/` holds detailed evidence; `verification/` holds execution checks.
- `notebooks/`: two short read-only exploratory notebooks.

See [data/README.md](data/README.md) for lineage, policies and artifact locations.
Do not delete/reset ID registries or change source snapshots when reproducing the
frozen outputs. Historical verification reports retain the paths and commands
used at the time; the cleanup inventory records their current destinations.

## Docker and tests

Use the existing Docker service and repository bind mount:

```sh
docker compose build
docker compose config
docker compose run --rm data-pipeline python -m unittest discover -s tests -t . -v
```

Run modules from the repository root with `python -m`; direct file execution is
superseded by package-safe module commands. Downloads reuse cached sources where
supported. Refresh flags intentionally change snapshots and are not part of a
frozen-output reproduction.

## Restaurant pipeline

Google Maps Kaggle supplies identity/location/ratings and ordinal prices.
OSM/Overpass adds optional hours, cuisine and explicit dietary evidence.

```sh
docker compose run --rm data-pipeline python -m scripts.restaurants.download_restaurants
docker compose run --rm data-pipeline python -m scripts.restaurants.download_restaurants_osm
docker compose run --rm data-pipeline python -m scripts.restaurants.preprocess_restaurants --enrich-osm
```

The numeric price mapping is experimental: 1 → $10–20, 2 → $20–40,
3 → $40–100, 4 → $100+; category 4 has no upper bound and missing categories
remain missing. Default hours are experimental fallbacks, not verified schedules.
See [restaurant report](data/reports/restaurant_data_report.md) and
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
docker compose run --rm data-pipeline python -m scripts.attractions.resolve_attraction_review
docker compose run --rm data-pipeline python -m scripts.attractions.filter_attractions
docker compose run --rm data-pipeline python -m scripts.attractions.match_attractions_kaggle
docker compose run --rm data-pipeline python -m scripts.attractions.audit_landmarks
docker compose run --rm data-pipeline python -m scripts.attractions.build_attraction_curation
docker compose run --rm data-pipeline python -m scripts.attractions.finalize_attractions
```

See [attraction report](data/reports/attraction_data_report.md). Source taxonomy,
filtering/alias evidence and historical manual-curation tables remain preserved
under `data/reports/audit/attractions/`.

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

A single streaming scan of the full New York split writes an identity-free,
disk-backed SQLite interim cache. Repeated corpus builds validate source/registry
hashes and reuse that cache. Text corpora retain at most 100 unique reviews per
entity: 60 most recent plus 40 historical reviews selected across rating strata
using seed 42. Up to 100 unique text reviews are all retained. This is not a
statistically representative sample. Persistent RR_/AR_ registries preserve IDs.

No reviewer identities or subjective scores/labels are derived. Missing mapping or
zero text reviews means **UNKNOWN / evidence unavailable**, never negative evidence.
See [review summary](data/reports/review_dataset_summary.md) and
[review schema/policy](data/metadata/review_corpus_schema.md).

## Read-only exploration

```sh
docker compose run --rm data-pipeline jupyter nbconvert --to notebook --execute --output-dir /tmp notebooks/explore_restaurants.ipynb notebooks/explore_attractions.ipynb
```

Notebooks inspect existing outputs; they do not construct or overwrite data.
Raw files, credentials and the expensive SQLite cache remain Git-ignored.
