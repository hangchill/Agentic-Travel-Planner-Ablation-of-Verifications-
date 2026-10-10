# Attractions exploration: CommonPlace only

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

The notebook/report surface category-keyword exploration subsets only. Their
membership is not a final inclusion/exclusion policy. CommonPlace alone does
not establish tourism completeness and supplies no admission prices, opening
hours or visitor ratings. No processed attractions dataset is generated.
Restaurant scripts, metadata, tests and processed data are unchanged.
