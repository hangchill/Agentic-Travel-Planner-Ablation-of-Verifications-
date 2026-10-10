# Google Local 2021 entity matching

[Official source](https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/). Complete New York metadata only; no review download or extraction.
Snapshot covers through September 2021 and is intentionally frozen for reproducibility: fixed offline corpus for experimental subjective-constraint evaluation.
## Retrieval

{
  "source": "google_local_2021",
  "source_url": "https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/",
  "download_url": "https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/meta-New_York.json.gz",
  "retrieved_at": "2026-10-10T12:33:15.358231+00:00",
  "filename": "meta-New_York.json.gz",
  "file_size_bytes": 60954605,
  "sha256": "b0d618a3e0d7286991f816a16079727e15ae20fdc2a6195d8d4ffae2cc28c534",
  "snapshot_coverage": "through September 2021",
  "role": "fixed offline experimental subjective-constraint review corpus; metadata-only matching stage"
}

## Streamed schema/quality inspection

{
  "raw_rows": 272189,
  "retained_nyc_rows": 118653,
  "region_bbox_lat_min_max_lon_min_max": [
    40.46909779542,
    40.940641274631,
    -74.283220339533,
    -73.684516461006
  ],
  "bbox_padding_degrees": 0.03,
  "keys": [
    "MISC",
    "address",
    "avg_rating",
    "category",
    "description",
    "gmap_id",
    "hours",
    "latitude",
    "longitude",
    "name",
    "num_of_reviews",
    "price",
    "relative_results",
    "state",
    "url"
  ],
  "types": {
    "MISC": {
      "NoneType": 53773,
      "dict": 218416
    },
    "address": {
      "str": 269457,
      "NoneType": 2732
    },
    "avg_rating": {
      "int": 52431,
      "float": 219758
    },
    "category": {
      "list": 271176,
      "NoneType": 1013
    },
    "description": {
      "NoneType": 217696,
      "str": 54493
    },
    "gmap_id": {
      "str": 272189
    },
    "hours": {
      "list": 214112,
      "NoneType": 58077
    },
    "latitude": {
      "float": 272189
    },
    "longitude": {
      "float": 272167,
      "int": 22
    },
    "name": {
      "str": 272187,
      "NoneType": 2
    },
    "num_of_reviews": {
      "int": 272189
    },
    "price": {
      "NoneType": 213559,
      "str": 58630
    },
    "relative_results": {
      "list": 252261,
      "NoneType": 19928
    },
    "state": {
      "str": 194940,
      "NoneType": 51863
    },
    "url": {
      "str": 272189
    }
  },
  "missing_or_null": {
    "MISC": 53773,
    "address": 2732,
    "avg_rating": 0,
    "category": 1013,
    "description": 217696,
    "gmap_id": 0,
    "hours": 58077,
    "latitude": 0,
    "longitude": 0,
    "name": 2,
    "num_of_reviews": 0,
    "price": 213559,
    "relative_results": 19928,
    "state": 77249,
    "url": 0
  },
  "empty_values": {},
  "duplicate_gmap_id_values": 1469,
  "duplicate_gmap_id_rows": 2938,
  "conflicting_duplicate_gmap_ids": [],
  "duplicate_name_groups": 11973,
  "duplicate_name_rows": 66811,
  "valid_coordinates": 272189,
  "invalid_or_missing_coordinates": 0
}

Schema counters and duplicate-name/ID counts are disk-backed; JSON lines are streamed without retaining all state metadata. NYC rows are written incrementally, then loaded for spatially indexed matching.
The geographic bounding box is derived from all canonical coordinates plus 0.03 degrees on every edge (~3km latitude). Boundary/New Jersey entities are preserved; New York-only source coverage may limit their matches. Invalid-coordinate metadata is accounted for but excluded from geographic matching.
## Canonical coverage

| entity_type | total_entities | high_confidence_matches | medium_candidates | ambiguous | unmatched | rejected | coverage_percent |
| --- | --- | --- | --- | --- | --- | --- | --- |
| restaurant | 670 | 246 | 1 | 1 | 309 | 114 | 36.71641791044776 |
| attraction | 3066 | 641 | 259 | 80 | 1269 | 1076 | 20.90671885192433 |

MEDIUM candidates counts canonical audit summaries with medium evidence (including ambiguous medium cases); only unambiguous HIGH enters the registry.
## Accepted match methods

| entity_type | match_method | entities |
| --- | --- | --- |
| attraction | EXACT_NAME_COORD | 582 |
| attraction | FUZZY_NAME_COORD_CATEGORY | 20 |
| attraction | NEAR_EXACT_NAME_COORD | 18 |
| attraction | NORMALIZED_ALIAS_COORD | 21 |
| restaurant | EXACT_NAME_ADDRESS | 1 |
| restaurant | GMAP_ID_NAME_COORD | 245 |

## Attraction category coverage

| category | total | matched | coverage_percent |
| --- | --- | --- | --- |
| amusement | 7 | 2 | 28.571428571428573 |
| beach | 49 | 5 | 10.204081632653061 |
| garden | 365 | 42 | 11.506849315068493 |
| historic_site | 41 | 5 | 12.195121951219512 |
| landmark | 190 | 38 | 20.0 |
| market | 1 | 0 | 0.0 |
| museum | 100 | 42 | 42.0 |
| park | 1302 | 339 | 26.036866359447004 |
| religious_site | 24 | 11 | 45.833333333333336 |
| sports | 655 | 63 | 9.618320610687023 |
| theater | 214 | 85 | 39.7196261682243 |
| transport_landmark | 9 | 4 | 44.44444444444444 |
| zoo | 109 | 5 | 4.587155963302752 |

## Attraction subcategory coverage

| subcategory | total | matched | coverage_percent |
| --- | --- | --- | --- |
| Amusement Park | 7 | 2 | 28.571428571428573 |
| Beach | 49 | 5 | 10.204081632653061 |
| Botanical Garden | 21 | 2 | 9.523809523809524 |
| Cemetery/Morgue | 4 | 0 | 0.0 |
| Center | 1 | 1 | 100.0 |
| Church | 18 | 9 | 50.0 |
| Ferry landing/terminal | 1 | 0 | 0.0 |
| Garden | 341 | 40 | 11.730205278592376 |
| Government Office | 3 | 0 | 0.0 |
| Museum | 95 | 42 | 44.21052631578947 |
| Official Landmark | 37 | 9 | 24.324324324324323 |
| Other | 6 | 1 | 16.666666666666668 |
| Park | 1274 | 337 | 26.452119309262166 |
| Pier | 1 | 0 | 0.0 |
| Point of Interest | 135 | 24 | 17.77777777777778 |
| Post Secondary Degree Granting Institution | 1 | 1 | 100.0 |
| Recreational Center | 1 | 1 | 100.0 |
| Sports | 654 | 62 | 9.480122324159021 |
| Synagogue | 1 | 1 | 100.0 |
| Theater/Concert Hall | 179 | 82 | 45.81005586592179 |
| UNKNOWN_UNDOCUMENTED | 1 | 1 | 100.0 |
| Zoo | 109 | 5 | 4.587155963302752 |
| individual_landmark | 124 | 15 | 12.096774193548388 |
| scenic_landmark | 3 | 1 | 33.333333333333336 |

## Attraction source coverage

| source | total | matched | coverage_percent |
| --- | --- | --- | --- |
| nyc_commonplace | 2939 | 625 | 21.265736645117386 |
| nyc_lpc_individual_landmarks | 124 | 15 | 12.096774193548388 |
| nyc_lpc_scenic_landmarks | 3 | 1 | 33.333333333333336 |

## Thresholds and identity policy

Restaurants: exact name <=30m; exact name <=75m with compatible address or same ZIP; exact name with strong numbered address <=150m or missing coordinates; fuzzy >=0.94 within 30m plus compatible numbered address; strong numbered address + name >=0.85 within 30m. Canonical Google Maps URL ID plus <=75m and name>=0.80 or compatible address is an additional explicit identity anchor.
Attractions: exact name <=75m; deterministic leading-the/ft-fort/st-saint/theatre-theater aliases <=50m; near-exact >=0.95 within 50m; fuzzy>=0.90 within 30m plus category support. Generic names and distinct functional words prevent relaxed HIGH acceptance. Category never replaces name/location.
Address normalization removes only an exact business-name prefix and standardizes common street/direction abbreviations. Compatible address >=0.85; strong >=0.92, both with agreeing leading street number. Explicit conflicting restaurant ZIPs and distances >150m block acceptance.
Spatial cells 0.002 degrees, ±2-cell neighbors with exact <=150m distance filtering; global exact normalized-name and address blocks expose distant candidates. No fuzzy name-only matches.
Multiple HIGH/medium plausible listings remain ambiguous. Any accepted gmap_id reused across canonical entities is blocked for ALL claimants and recorded for inspection. No shared representation is presumed legitimate.
Duplicate canonical identities are flagged by exact normalized alias name and <=30m; other all-attraction collisions are potential parent/child issues, mixed collisions remain matching/shared-representation issues. These are diagnostic classifications, not source-data corrections.
Persistent registry preserves existing entity → gmap_id associations across identical snapshots; conflicting/removal changes fail rather than silently replacing mappings.
## Duplicate Google-ID mapping issues

| entity_type | entity_id | entity_name | match_status | match_confidence | match_method | diagnostic_flags | candidate_gmap_id | google_name | google_address | google_latitude | google_longitude | google_categories | google_listing_state | distance_meters | name_similarity | address_similarity | category_compatible | evidence_reason | source | collision_classification | collision_entity_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| attraction | ATTR_1374 | SHUBERT THEATRE | MATCHED | HIGH | EXACT_NAME_COORD |  | 0x89c25852896a3193:0xfbc747d5ea21cea9 | Shubert Theatre | Shubert Theatre, 225 W 44th St, New York, NY 10036 | 40.7580922 | -73.9871606 | ["Performing arts theater"] |  | 11.845633272591149 | 1.0 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_2976 | Shubert Theater | MATCHED | HIGH | NORMALIZED_ALIAS_COORD |  | 0x89c25852896a3193:0xfbc747d5ea21cea9 | Shubert Theatre | Shubert Theatre, 225 W 44th St, New York, NY 10036 | 40.7580922 | -73.9871606 | ["Performing arts theater"] |  | 9.954344159695825 | 0.933333 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_2511 | MAJESTIC THEATRE | MATCHED | HIGH | EXACT_NAME_COORD |  | 0x89c2585487856a85:0xa8010c390fd031f8 | Majestic Theatre | Majestic Theatre, 245 W 44th St, New York, NY 10036 | 40.7583598 | -73.9880791 | ["Performing arts theater"] |  | 12.647283003076819 | 1.0 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_3011 | Majestic Theater | MATCHED | HIGH | NORMALIZED_ALIAS_COORD |  | 0x89c2585487856a85:0xa8010c390fd031f8 | Majestic Theatre | Majestic Theatre, 245 W 44th St, New York, NY 10036 | 40.7583598 | -73.9880791 | ["Performing arts theater"] |  | 9.166509677986857 | 0.9375 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_2709 | LYCEUM THEATRE | MATCHED | HIGH | EXACT_NAME_COORD |  | 0x89c258550a61e8b5:0x638fc348d6cc418c | Lyceum Theatre | Lyceum Theatre, 149 W 45th St, New York, NY 10036 | 40.7577485 | -73.9846178 | ["Performing arts theater"] |  | 6.759688257779886 | 1.0 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_3018 | Lyceum Theater | MATCHED | HIGH | NORMALIZED_ALIAS_COORD |  | 0x89c258550a61e8b5:0x638fc348d6cc418c | Lyceum Theatre | Lyceum Theatre, 149 W 45th St, New York, NY 10036 | 40.7577485 | -73.9846178 | ["Performing arts theater"] |  | 16.49826701640184 | 0.928571 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_2808 | CORT THEATRE | MATCHED | HIGH | EXACT_NAME_COORD |  | 0x89c25855f60976e9:0x9409d6da413e395c | Cort Theatre | Cort Theatre, 138 W 48th St, New York, NY 10036 | 40.759197 | -73.983008 | ["Performing arts theater"] |  | 6.916274485635664 | 1.0 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_3028 | Cort Theater | MATCHED | HIGH | NORMALIZED_ALIAS_COORD |  | 0x89c25855f60976e9:0x9409d6da413e395c | Cort Theatre | Cort Theatre, 138 W 48th St, New York, NY 10036 | 40.759197 | -73.983008 | ["Performing arts theater"] |  | 9.796604463341687 | 0.916667 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_2735 | LONGACRE THEATRE | MATCHED | HIGH | EXACT_NAME_COORD |  | 0x89c25856639258f7:0xbf564918ad5b6692 | Longacre Theatre | Longacre Theatre, 220 W 48th St, New York, NY 10036 | 40.7604459 | -73.9858825 | ["Performing arts theater"] |  | 3.9710664221783483 | 1.0 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_3001 | Longacre Theater | MATCHED | HIGH | NORMALIZED_ALIAS_COORD |  | 0x89c25856639258f7:0xbf564918ad5b6692 | Longacre Theatre | Longacre Theatre, 220 W 48th St, New York, NY 10036 | 40.7604459 | -73.9858825 | ["Performing arts theater"] |  | 13.157067025447772 | 0.9375 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_0302 | BOOTH THEATRE | MATCHED | HIGH | EXACT_NAME_COORD |  | 0x89c2585665784711:0x21635c43ec03681a | Booth Theatre | Booth Theatre, 222 W 45th St, New York, NY 10036 | 40.7584413 | -73.9869889 | ["Performing arts theater"] |  | 5.755489579485569 | 1.0 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_2973 | Booth Theater | MATCHED | HIGH | NORMALIZED_ALIAS_COORD |  | 0x89c2585665784711:0x21635c43ec03681a | Booth Theatre | Booth Theatre, 222 W 45th St, New York, NY 10036 | 40.7584413 | -73.9869889 | ["Performing arts theater"] |  | 12.037943671013037 | 0.923077 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | duplicate_canonical_entity | 2 |
| attraction | ATTR_1290 | HUDSON RIVER PARK TENNIS COURT 1 | MATCHED | HIGH | NEAR_EXACT_NAME_COORD |  | 0x89c259f3cc639b0f:0x121147d22edb68e2 | Hudson River Park Tennis Courts | Hudson River Park Tennis Courts, 92 Hudson River Greenway, New York, NY 10014 | 40.727243 | -74.0113267 | ["Tennis court"] | Closed ⋅ Opens 6AM | 43.33773090244814 | 0.952381 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | parent_child_attraction_issue | 3 |
| attraction | ATTR_1291 | HUDSON RIVER PARK TENNIS COURT 2 | MATCHED | HIGH | NEAR_EXACT_NAME_COORD |  | 0x89c259f3cc639b0f:0x121147d22edb68e2 | Hudson River Park Tennis Courts | Hudson River Park Tennis Courts, 92 Hudson River Greenway, New York, NY 10014 | 40.727243 | -74.0113267 | ["Tennis court"] | Closed ⋅ Opens 6AM | 7.906930453206384 | 0.952381 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | parent_child_attraction_issue | 3 |
| attraction | ATTR_1292 | HUDSON RIVER PARK TENNIS COURT 3 | MATCHED | HIGH | NEAR_EXACT_NAME_COORD |  | 0x89c259f3cc639b0f:0x121147d22edb68e2 | Hudson River Park Tennis Courts | Hudson River Park Tennis Courts, 92 Hudson River Greenway, New York, NY 10014 | 40.727243 | -74.0113267 | ["Tennis court"] | Closed ⋅ Opens 6AM | 28.880253289877295 | 0.952381 |  | True | Name/location evidence satisfies documented HIGH thresholds | google_local_2021 | parent_child_attraction_issue | 3 |

## Restaurant nonmatched examples

| entity_id | entity_name | match_status | diagnostic_flags |
| --- | --- | --- | --- |
| REST_0654 | The Firehouse Family Restaurant & Bar | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0474 | H Restaurant & SS Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0569 | Mompou Tapas Bar & Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0612 | Rasoi | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0614 | Restaurant Oyola | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0640 | Sublime Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0388 | Bravo Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0448 | Elia Mediterranean Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0425 | EcuAmerica Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0499 | Krakus Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0615 | Rico Rico Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0122 | Golden Krust Caribbean Restaurant | REJECTED | possible_closed_listing_snapshot;name_or_location_difference_possible |
| REST_0344 | უბანი | UNMATCHED | no_candidate_within_spatial_or_exact_name_block |
| REST_0226 | Oceana | REJECTED | possible_closed_listing_snapshot;name_or_location_difference_possible |
| REST_0257 | Restaurant Relax | REJECTED | possible_closed_listing_snapshot;name_or_location_difference_possible |
| REST_0473 | Gyro king Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0032 | Breniz restaurant | REJECTED | possible_closed_listing_snapshot;name_or_location_difference_possible |
| REST_0453 | Family c restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0164 | Junction Seafood Restaurant / Fast & Fresh Comida Típica | REJECTED | possible_closed_listing_snapshot;name_or_location_difference_possible |
| REST_0503 | La Guayaca Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0613 | Restaurant El Rinconcito De Doña Maria | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0568 | Mister Gusto Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0442 | El Pio Pio | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |
| REST_0256 | Restaurant Pearl | REJECTED | possible_closed_listing_snapshot;name_or_location_difference_possible |
| REST_0433 | El Jardin Restaurant | UNMATCHED | non_New_York_address_source_split_limitation;no_candidate_within_spatial_or_exact_name_block |

## Attraction nonmatched examples

| entity_id | entity_name | match_status | diagnostic_flags |
| --- | --- | --- | --- |
| ATTR_0001 | TIMES SQUARE PLAZA | AMBIGUOUS | historic_site_may_not_be_standalone_business;name_or_location_difference_possible |
| ATTR_0002 | HARLEM RIVER PARK W 145 ST | REJECTED | large_geographic_feature_possible;name_or_location_difference_possible |
| ATTR_0004 | FIRST TEMPLE OF DAVID GARDEN | UNMATCHED | large_geographic_feature_possible;no_candidate_within_spatial_or_exact_name_block |
| ATTR_0005 | HARLEM RIVER PARK LEXINGTON AVE & E 130 | UNMATCHED | large_geographic_feature_possible;no_candidate_within_spatial_or_exact_name_block |
| ATTR_0006 | SQUADRON A ARMORY | UNMATCHED | historic_site_may_not_be_standalone_business;no_candidate_within_spatial_or_exact_name_block |
| ATTR_0007 | WYCKOFF HOUSE | REJECTED | name_or_location_difference_possible |
| ATTR_0008 | PROSPECT PARK BOAT HOUSE | REJECTED | large_geographic_feature_possible;name_or_location_difference_possible |
| ATTR_0009 | RIVERSIDE PARK 146 & 147 BASEBALL FIELDS | UNMATCHED | large_geographic_feature_possible;no_candidate_within_spatial_or_exact_name_block |
| ATTR_0010 | OVER THE TRACKS TENNIS COURTS | REJECTED | large_geographic_feature_possible;name_or_location_difference_possible |
| ATTR_0011 | VAN CORTLANDT PARK CROTON WOODS | UNMATCHED | large_geographic_feature_possible;no_candidate_within_spatial_or_exact_name_block |
| ATTR_0012 | VAN CORTLANDT PARK INDIAN FIELD | UNMATCHED | large_geographic_feature_possible;no_candidate_within_spatial_or_exact_name_block |
| ATTR_0013 | PELHAM BAY PARK RICE STADIUM | UNMATCHED | no_candidate_within_spatial_or_exact_name_block |
| ATTR_0014 | VAN CORTLANDT PARK NORTHEAST FOREST | UNMATCHED | large_geographic_feature_possible;no_candidate_within_spatial_or_exact_name_block |
| ATTR_0015 | VAN CORTLANDT PARK PARADE GROUND NORTH | UNMATCHED | large_geographic_feature_possible;no_candidate_within_spatial_or_exact_name_block |
| ATTR_0018 | CENTRAL PARK CHARLES A DANA DISCOVERY CENTER | UNMATCHED | large_geographic_feature_possible;name_or_location_difference_possible |
| ATTR_0019 | BRONX ZOO - BRONX ZOO STORE | REJECTED | name_or_location_difference_possible |
| ATTR_0020 | DUKE ELLINGTON CIRCLE | REJECTED | large_geographic_feature_possible;name_or_location_difference_possible |
| ATTR_0021 | RIVER GARDEN | UNMATCHED | large_geographic_feature_possible;no_candidate_within_spatial_or_exact_name_block |
| ATTR_0022 | CENTRAL PARK UNTERMYER FOUNTAIN | UNMATCHED | large_geographic_feature_possible;name_or_location_difference_possible |
| ATTR_0023 | SKENE MONUMENT | REJECTED | historic_site_may_not_be_standalone_business;name_or_location_difference_possible |
| ATTR_0024 | CENTRAL PARK KING JAGIELLO STATUE | REJECTED | large_geographic_feature_possible;name_or_location_difference_possible |
| ATTR_0025 | THOMAS JEFFERSON PARK | AMBIGUOUS | large_geographic_feature_possible;name_or_location_difference_possible |
| ATTR_0026 | CENTRAL PARK HERNSHEAD | REJECTED | large_geographic_feature_possible;name_or_location_difference_possible |
| ATTR_0029 | MARTINS FIELD | UNMATCHED | no_candidate_within_spatial_or_exact_name_block |
| ATTR_0030 | PROSPECT PARK MUSIC PAGODA | UNMATCHED | large_geographic_feature_possible;no_candidate_within_spatial_or_exact_name_block |

Diagnostics identify possible gaps/name/location differences, not verified closures or absences. Listing-state evidence refers to the historical metadata snapshot.
## Review extraction deferred

No restaurant_reviews.csv or attraction_reviews.csv is created. Future extraction will retain rating, review_text, timestamp/date, gmap_id and entity_id; reviewer names/profiles are unnecessary and will not enter downstream tables.
Canonical restaurant/attraction data and prior source/enrichment/curation audits remain unchanged.
