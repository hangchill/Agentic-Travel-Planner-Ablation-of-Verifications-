# Restaurant data provenance

Source roles:

- Google Maps Kaggle → canonical identity/location/rating/price source.
- OpenStreetMap / Overpass → opening/kitchen-hours, cuisine and explicit dietary enrichment.
- Manual inspection → experimental price-category-to-range mapping.
- US OPM calendar → 2026 federal-holiday date metadata.

The only application-facing restaurant dataset is `data/processed/restaurants.csv`.
Only `google_maps/` and `osm/` remain under `data/raw/restaurants/`; raw and interim
data are regeneration inputs and audit artifacts, never downstream restaurant tables.

## Canonical Google Maps Kaggle source

Dataset: `beridzeg45/nyc-restaurants`. Raw file:
`data/raw/restaurants/google_maps/google_maps_restaurants(cleaned).csv`.
The raw source has 670 rows and is preserved unchanged. Original columns:
URL, Name, Rating, Rating Count, Detailed Ratings, Price Category, Address,
Lat, Lon, ZipCode. All source locations are retained, without geographic filtering.
The persistent ID registry preserves canonical assignments.

## Experimental price mapping

The source provides ordinal price categories. Representative original Google
Maps URLs were manually inspected by the project team to infer approximate
per-person ranges for budget experiments. `price_mapping.csv` is the sole mapping
source. These estimates are experimental, not exact real-world guarantees.
Manual observation records remain separate in
`data/reports/manual_price_category_check.csv`; they are never autofilled.
Field semantics and ranges are in `restaurant_schema.md`.

## Optional OpenStreetMap / Overpass

OSM supplies explicit general/kitchen opening hours, cuisine and supported
`diet:*` tags. It never replaces canonical identity/location/rating/price fields.
Data is community-maintained, potentially incomplete or stale.
© OpenStreetMap contributors; [ODbL and attribution](https://www.openstreetmap.org/copyright).

The downloader requests restaurant nodes/ways/relations within canonical
coordinate bounds plus a 0.005-degree margin. It uses Overpass JSON and
`out center tags;`, without scraping HTML. Successful raw caches record
retrieved_at, endpoint, query_version, exact query and bounds. Raw data is ignored
by Git. Failed retrieval preserves existing cache/output; unavailable coverage
is unknown rather than zero. Preprocessing is offline and deterministic.

Independent clean and enrichment tables retain raw tag values for audit.
The main report summarizes coverage, while matching/ambiguity CSVs expose
candidate evidence. Matching thresholds and tag semantics are in the schema.

## Controlled hours assumptions and federal calendar

Missing general hours receive 11:00–22:00 daily as an experimental fallback,
not observed restaurant information. Raw OSM hours and kitchen hours are unchanged.
Provenance always distinguishes real OSM evidence from fallback assumptions.

`us_public_holidays.csv` is the sole calendar source for all of **2026**,
chosen because experiment dates were unspecified. Verified from
[US OPM federal holiday schedule](https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/):
11 actual federal dates plus July 3 as the separately labelled observed
Independence Day date. Both types flag experiment holidays; neither implies
restaurant closure. This federal scope does not model all local OSM PH holidays.

Only explicit unquoted OSM PH syntax supplies source-provided holiday behaviour.
The whole source expression is preserved; unsupported syntax remains UNKNOWN.
The resolver uses static metadata and rejects out-of-scope years, without
runtime calendar services or locale-dependent computation.
