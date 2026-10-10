# Restaurant schema

Application contract: `data/processed/restaurants.csv` is the sole restaurant
dataset consumed by downstream search, filtering, budget and hours functions.
Application code must not depend directly on `data/raw/` or `data/interim/`;
these are preprocessing inputs/audit artifacts, not alternative restaurant
datasets. Metadata supplies regeneration configuration and calendar dates.

Canonical core: beridzeg45/nyc-restaurants. No geographic filtering. Optional OSM enrichment is appended to the frozen 670 rows.

| Field | Datatype | Source / cleaning |
|---|---|---|
| restaurant_id | string | Derived deterministic REST identifier, persistent registry reused |
| name | string | Name, outer whitespace trimmed; required nonempty |
| rating | nullable float | Rating, missing preserved; 0–5 validation |
| rating_count | nullable number | Rating Count, preserved |
| price_category | nullable source number | Price Category retained exactly, no imputation; original value unchanged |
| price_min | nullable float | Derived lower bound from the experimental price mapping |
| price_max | nullable float | Derived upper bound; null for open-ended category 4 |
| price_open_ended | nullable boolean | True for category 4, false for bounded mapped categories; null when category missing |
| price_range_label | nullable string | Experimental display label, with typographic en dash for bounded ranges |
| address | nullable string | Address, outer whitespace trimmed |
| latitude | float | Lat, numeric; required valid -90..90 |
| longitude | float | Lon, numeric; required valid -180..180 |
| zipcode | nullable 5-character string | ZipCode; numeric-like ZIP padded, ZIP+4 uses 5-digit prefix |
| url | string | URL preserved exactly |
| source | string | google_maps_kaggle |

Detailed Ratings is excluded from the final table. Raw source duplicates are
checked across every raw field before column selection; distinct source rows
are retained. No other invalid records are silently removed: validation errors
require source review. Missing ratings and price categories remain missing.
No estimated_meal_cost is defined. Optional OSM fields are documented below.

The retained ID registry is required for stable canonical regeneration. Physical
keys use normalized name/address/coordinates; collisions receive deterministic
record suffixes. Bootstrap allocates new IDs in URL order; frozen enrichment
never assigns IDs. Identity corrections require registry review.

Experimental approximate per-person ranges: 1 → $10–20; 2 → $20–40;
3 → $40–100; 4 → $100+. See data_sources.md for manual-inspection provenance.
These estimates are not exact real-world guarantees.

Single source of truth: data/metadata/price_mapping.csv. Its range labels use
ASCII hyphens; the export uses en dashes for display. Category 4 is open-ended:
price_min=100, price_max=null, price_open_ended=true. Missing categories remain
missing, with all four derived fields null. No imputation or meal-cost estimate.
Budget-verification policy chooses how to use a range separately; an upper bound
is not available for category 4. Bounded ranges require price_min <= price_max.
Validation compares every derived value against the mapping metadata and verifies
source categories and URLs are unchanged. Manual observation records are never
autofilled by this mapping.

## Optional OSM fields

The original 15 columns are frozen, including their CSV string values and row
order. Only MATCHED one-to-one OSM records populate observed fields. Experimental hours are appended separately for missing observed general hours.

| Field | Type | Meaning |
|---|---|---|
| opening_hours_raw | nullable string | Verbatim opening_hours tag; not parsed or repaired |
| opening_hours_source | string | openstreetmap for observed hours; experimental_default for missing hours |
| opening_hours_kitchen_raw | nullable string | Verbatim opening_hours:kitchen, separate from general hours |
| opening_hours_kitchen_source | nullable string | openstreetmap only when kitchen hours exist |
| cuisine_raw | nullable string | Verbatim cuisine tag |
| cuisine | nullable JSON array string | Sorted unique lowercase semicolon-separated source tokens |
| cuisine_source | nullable string | openstreetmap only when cuisine exists |
| diet_vegetarian | nullable string | Explicit diet:vegetarian semantic value, verbatim |
| diet_vegan | nullable string | Explicit diet:vegan semantic value, verbatim |
| diet_halal | nullable string | Explicit diet:halal semantic value, verbatim |
| diet_kosher | nullable string | Explicit diet:kosher semantic value, verbatim |
| diet_gluten_free | nullable string | Explicit diet:gluten_free semantic value, verbatim |
| dietary_source | nullable string | openstreetmap if any supported dietary tag exists |
| osm_id | nullable string | Source element ID; pair with osm_type |
| osm_type | nullable string | node, way or relation |

No dietary boolean conversion or inference from names/cuisines. Source values
yes/no/only/limited and other values retain their semantics. No accepted match
means observed OSM fields are null; labelled general-hours defaults still apply. The interim table retains all *_raw tags, original
OSM address components, normalized name/address and source=openstreetmap.
Match reports include distance_meters, method, confidence (evidence score, not
probability), and MATCHED/UNMATCHED/AMBIGUOUS/REJECTED status for source/candidate
rows. Ambiguous candidates never enter the canonical table. Community-maintained
OSM schedules and tags may be incomplete or stale.

## Effective hours and holiday fields

| Field | Type | Meaning |
|---|---|---|
| opening_hours_effective | JSON object string | Typed weekly default or verbatim osm_opening_hours expression |
| opening_hours_is_assumed | boolean | true only for controlled experimental fallback |
| has_explicit_holiday_rule | boolean | Unquoted PH token exists in observed general hours |
| holiday_rule_raw | nullable string | Entire verbatim observed OSM expression if PH exists; never simplified |
| holiday_rule_status | string enum | EXPLICIT_CLOSED, EXPLICIT_OPEN, EXPLICIT_SPECIAL_HOURS, UNKNOWN or ASSUMED |
| holiday_rule_source | nullable string | openstreetmap for explicit PH; null for observed without PH; experimental_default for fallback |

Weekly default schedule: 11:00–22:00 daily, Monday through Sunday. This is a
controlled experimental assumption, not real restaurant information. Observed
OSM raw general and kitchen schedules are never replaced. No kitchen fallback.
Observed effective JSON uses format=osm_opening_hours and raw=verbatim syntax;
default JSON uses format=weekly and schedule=seven-day interval object.

Simple standalone PH clauses may be classified; compound, malformed, overnight
or otherwise unsupported expressions stay UNKNOWN. Observed schedules without
PH are UNKNOWN; defaults are ASSUMED. None of these status fields is a verifier
result. Calendar metadata is separate from per-restaurant evidence.

Holiday CSV columns: date (ISO date), holiday_name (string), holiday_type
(federal or federal_observed), source (US OPM). Configured coverage is the full
2026 calendar year, including 11 actual holidays and the separate July 3 observed
date. Other years fail explicitly. Both types flag a holiday for experiment
resolution, without implying any restaurant is closed.

## Matching and report semantics

Matching reuses shared name/address normalization and Haversine distance.
Exact normalized name within 50m provides strong evidence; up to 150m requires
exact name plus postcode or complete house-number/street agreement. Fuzzy name
similarity must reach 0.94, plus <=50m or strong address and postcode agreement.
No automatic acceptance beyond 150m; conflicting house numbers block acceptance.
These thresholds are heuristics, not ground truth. One-to-many/many-to-one
plausible conflicts remain AMBIGUOUS. Only unique MATCHED edges enrich rows.

Detailed reports include rejected nearby candidate pairs and unmatched source
rows. The main report distinguishes candidate counts from source-record counts;
source precedence is MATCHED, AMBIGUOUS, REJECTED, UNMATCHED. Confidence is an
evidence score, not a calibrated probability.

`resolve_hours(restaurant,date)` prioritizes explicit PH evidence on a calendar
holiday, ordinary OSM evidence on other dates, ordinary OSM evidence labelled
holiday UNKNOWN when no PH exists, and labelled defaults when observations are
missing. It classifies only a single standalone PH clause: off/closed, open/24/7,
or valid same-day time intervals. Compound selectors, quoted qualifications,
fallback/multiple clauses, overnight or malformed intervals remain UNKNOWN.
Quoted PH comments do not count as rules. Raw syntax is never silently repaired.
