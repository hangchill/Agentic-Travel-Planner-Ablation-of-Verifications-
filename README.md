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
