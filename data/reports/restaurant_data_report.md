# Restaurant data report

## Canonical data

- Canonical restaurants: 670
- Missing price category: 123
- Successfully mapped price rows: 547
- Missing rating: 4

| Category | Rows | Experimental per-person range |
|---|---:|---|
| 1 | 204 | $10–20 |
| 2 | 310 | $20–40 |
| 3 | 26 | $40–100 |
| 4 | 7 | $100+ |

Representative original Google Maps URLs were manually inspected by the project team.
Ranges are approximate experimental estimates, not exact real-world guarantees.
Missing categories remain null in all derived price fields; category 4 has no upper bound.
No estimated_meal_cost is defined. See data/metadata/price_mapping.csv for the single mapping source.

## Cleaning and provenance

Canonical source: Kaggle beridzeg45/nyc-restaurants. All source locations are retained.
Names/addresses are trimmed, ZIP formatting is normalized, and only exact full-source duplicates are removed.
Ratings, price categories, original URLs and missing values are preserved. Invalid required data fails validation.
Raw rows: 670; exact duplicates: 0.
Google Maps raw SHA-256: `8e642bbc313c5b72d397d14b52f3c2fdacc047ea2119c522101e0af027bfddf9`.

## Integrity and verification

The ID registry is retained for stable canonical regeneration. Frozen OSM processing never assigns IDs.
All 670 IDs, row order and 15 core fields must pass exact CSV-projection equality before enrichment is written.
Processed output and OSM audit files are deterministic from the same raw cache and metadata.
Active tests cover cleaning, stable IDs, price mapping, OSM extraction/matching/diet tags,
hours defaults, PH handling, calendar scope, frozen core and determinism.
Verification command: `docker compose run --rm data-pipeline python -m unittest discover -s tests -v`.
Cleanup verification: 27 active tests passed; frozen core and complete restaurant CSV stayed byte-identical;
repeat preprocessing matched output checksums, Docker rebuilt without cache, and notebook execution passed.

## OpenStreetMap enrichment

Retrieval succeeded; cached JSON was processed offline.
Raw restaurant records: 8465.

Retrieval metadata: `{"bounding_box": [40.6025183, -74.19504049999999, 40.911720300000006, -73.7861987], "canonical_file_sha256": "5aa6cde08939a5110d906ae43ba3e74faa1a8a7eb6857e38778f6237a69c488f", "overpass_endpoint": "https://overpass-api.de/api/interpreter", "query": "[out:json][timeout:90];nwr[\"amenity\"=\"restaurant\"](40.6025183,-74.1950405,40.9117203,-73.7861987);out center tags;", "query_version": "restaurant-bbox-v1", "retrieved_at": "2026-10-10T08:25:47.563488+00:00"}`

© OpenStreetMap contributors; [ODbL attribution](https://www.openstreetmap.org/copyright).
Community-maintained data may be incomplete or stale. Hours are preserved verbatim, without parsing or repair.

## Source coverage

- Opening hours: 3968 / 8465
- Kitchen hours: 61 / 8465
- Cuisine: 6607 / 8465
- Any supported dietary tag: 747 / 8465
- Any explicit diet:* tag (including unsupported kinds): 771 / 8465

## Match statuses

Candidate counts include rejected nearby pairs. Source counts use precedence MATCHED > AMBIGUOUS > REJECTED > UNMATCHED; each source is counted once.

- MATCHED: 114 candidate/report rows; 114 source records
- AMBIGUOUS: 0 candidate/report rows; 0 source records
- REJECTED: 776 candidate/report rows; 676 source records
- UNMATCHED: 7675 candidate/report rows; 7675 source records

## Canonical coverage

- Opening hours: 50 / 670
- Kitchen hours: 1 / 670
- Cuisine: 100 / 670
- Any dietary tag: 7 / 670
- vegetarian: 6 / 670
- vegan: 1 / 670
- halal: 2 / 670
- kosher: 1 / 670
- gluten_free: 0 / 670

All 670 IDs, row order and all 15 frozen core columns passed byte-identical CSV-projection validation.
Matching thresholds are heuristics: <=50m strong; <=150m requires exact name plus postcode/address, or fuzzy >=0.94 plus full address and postcode. No matches beyond 150m. Conflicting house numbers block acceptance.
Confidence is an evidence score, not a calibrated probability. All one-to-many/many-to-one plausible conflicts stay AMBIGUOUS.
No meal-cost estimate, cuisine-based dietary inference or custom opening-hours parser is used.

Raw OSM schedules containing unquoted PH tokens: 7 / 8465

## Effective hours and holiday evidence

- Observed OSM opening hours: 50 / 670
- Experimental default hours: 620 / 670
- Effective opening-hours coverage: 670 / 670
- Restaurants with explicit OSM PH rules: 0
- Matched observed OSM schedules containing unquoted PH tokens: 0
- EXPLICIT_CLOSED: 0
- EXPLICIT_OPEN: 0
- EXPLICIT_SPECIAL_HOURS: 0
- UNKNOWN: 50
- ASSUMED: 620

The 11:00–22:00 daily default is a controlled experimental assumption, not actual restaurant information.
Calendar scope: 2026; actual federal dates plus separately labelled federal observed dates.
The static calendar flags dates; it never implies blanket restaurant closure.
Only explicit OSM PH syntax supplies holiday behaviour. Complex syntax remains UNKNOWN and raw text is preserved.
Effective observed hours use typed JSON containing verbatim OSM syntax; no general schedule parser is supplied.
