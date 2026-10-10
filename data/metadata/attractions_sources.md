# Attraction sources and geometry methodology

Source: [NYC Open Data CommonPlace, t95h-5fsr](https://data.cityofnewyork.us/City-Government/CommonPlace/t95h-5fsr).
The downloader uses the official CSV export and schema API. It caches the exact
CSV, API schema, source dictionary and retrieval metadata under
`data/raw/attractions/commonplace/`, ignored by Git. Metadata records dataset
name/ID, source/download URLs, retrieval time, row count, exact columns and checksum.
`--refresh` explicitly replaces the cached source; subsequent exploration is offline.

Only documentation of this same CommonPlace source is additionally retrieved:
[CityOfNewYork PointsOfInterest metadata](https://github.com/CityOfNewYork/nyc-geo-metadata/blob/main/Metadata/Metadata_PointsOfInterest.md).
It documents dispatch-oriented points of interest and paired taxonomy codes.
FACILITY TYPE is the broad category; FACILITY DOMAINS is a type-dependent subtype,
not an independently meaningful domain label. `commonplace_taxonomy.csv` is
regenerated from the cached dictionary, preserving source codes and labels.
The dictionary is older than the current CSV; missing documented labels remain
null and must be reviewed rather than inferred from feature names.

`data/interim/commonplace_attractions_clean.csv` retains all source rows and all
21 original fields as raw-prefixed string columns, alongside standardized names,
source codes/IDs, decoded labels and WKT-derived longitude/latitude. OBJECTID,
PLACEID and agency SOURCE ID retain source identity semantics. They are not final
canonical attraction IDs. Blank source fields remain null; no imputation,
deduplication, geocoding or tourism filtering is applied. Unsupported borough
code 8 is retained with a null borough label.

Generated diagnostics surface category-keyword exploration subsets only. Their
membership is not a final inclusion/exclusion policy. CommonPlace alone does
not establish tourism completeness and supplies no admission prices, opening
hours or visitor ratings. Finalization constructs the processed attraction universe from CommonPlace INCLUDE
identities and the existing deterministic shortlist rules; see data/DATA_CATALOG.md.

## LPC landmarks and supporting evidence

Individual Landmark Sites (`buis-pvji`) and Scenic Landmarks (`qexa-qpj6`) are the
only added LPC sources; historic-district building records are excluded. Individual
eligibility uses designated status, with currency unverified because a current flag
is absent. Scenic eligibility requires current_=true and DESIGNATED status without
conflicting inactive/calendared/rescinded action. All source rows/status groups remain
in clean checkpoints; only eligible features support matching.

Socrata exports retain EPSG:2263 projected geometry despite GeoJSON conventions and
an incorrectly WGS84-labelled Shapefile .prj. Cached LPC spatial-reference metadata
resolves the conflict. Geometries are repaired deterministically where needed;
representative points lie inside/on polygons. Individual transformed coordinates and
scenic extents are checked against source geographic/LPC spatial evidence. No geocoding.

Matching requires normalized name plus location evidence: within 50 m, exact names
within 150 m, or polygon containment for large sites. Multiple plausible candidates
remain ambiguous; proximity alone cannot collapse different names/functions. Existing
fuzzy thresholds, scoped rules, source-ID deduplication and shortlist ranking/caps
remain in the construction modules and metadata. Kaggle geographic confirmation is
unavailable in this snapshot; its name-only evidence cannot originate additions.

The unchanged classified checkpoint has 20,451 rows: INCLUDE 2,901, REVIEW 5,790,
EXCLUDE 11,760. No whole REVIEW subtype was promoted; the selective shortlist and
finalizer apply the preserved experimental policy. Historical blank manual fields
are not required decisions; populated manual edits remain protected against overwrite.

## Admission enrichment

The separate [admission pipeline](attraction_admission.md) appends ten cost/provenance
fields from checksum-verified public source snapshots without altering identities,
classification or source rules. Precedence is associated official structured admission
records, then confidently linked Wikidata P2555, then OSM whole-attraction fee/charge.
Only accepted source-ID or exact-normalized-name/location matches apply. Missing
evidence remains unknown; the initial snapshot has 29 status observations and ten
exact free admissions across 3,066 canonical attractions. All source snapshots are
Git-ignored; optional reports are generated on demand and never consumed at runtime.
