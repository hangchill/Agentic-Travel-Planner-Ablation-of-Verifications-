# Kaggle tourist-relevance cross-check — audit only

Source: [anirudhmunnangi/348-new-york-tourist-locations](https://www.kaggle.com/datasets/anirudhmunnangi/348-new-york-tourist-locations). Raw files remain ignored; no canonical source replacement.
## Actual source schema

[
  {
    "filename": "New_York_Tourist_Locations.xlsx",
    "sheet": "Sheet1",
    "row_count": 347,
    "columns": [
      "Tourist_Spot",
      "Address",
      "Zipcode"
    ],
    "dtypes": {
      "Tourist_Spot": "str",
      "Address": "str",
      "Zipcode": "object"
    },
    "missingness": {
      "Tourist_Spot": 0,
      "Address": 0,
      "Zipcode": 0
    },
    "exact_duplicate_rows": 2,
    "sha256": "a77d9608ae99d85940a59cd592c0e9b7b5d766caf538ed3a3c7fa5e877e99dfc",
    "duplicate_name_rows": 8,
    "duplicate_name_groups": 4
  }
]

Actual rows: 347. The dataset title says 348, but the downloaded workbook has 347 data rows.
Invalid/missing normalized ZIP values: 0.
Repeated normalized-name rows: 8.
Exact duplicates and repeated names are preserved for alias/duplicate review.

## Geographic-evidence limitation

CommonPlace has coordinates, but no addresses or ZIP columns. Kaggle has addresses/ZIPs, but no coordinates.
Opaque source/address-point IDs and boroughs are not address/ZIP evidence. No geocoding or ZIP inference was added.
Therefore this snapshot cannot support the requested geographic/address-backed matching hierarchy.
Zero accepted matches means insufficient comparable evidence, not proven absence from CommonPlace.
Name-only candidates are preserved separately for manual inspection and cannot support REVIEW promotion.

## Row-level status accounting

| match_status | rows |
| --- | --- |
| MATCHED_INCLUDE | 0 |
| MATCHED_REVIEW | 0 |
| MATCHED_EXCLUDE | 0 |
| UNMATCHED | 229 |
| AMBIGUOUS | 4 |
| REJECTED | 114 |

Current INCLUDE representation confirmed by accepted matches: 0/347 (0.00%).
INCLUDE + REVIEW confirmed representation: 0/347 (0.00%).
These are confirmed-match lower bounds; overall source overlap/completeness is unknown with the available fields.
Rows without an accepted primary INCLUDE/REVIEW match: 347; preserved in the unmatched review file, including ambiguous/rejected/diagnostic EXCLUDE statuses.

## REVIEW subtype support

| facility_type | facility_domain_code | facility_domain_label | review_rows_total | review_rows_matched_by_kaggle | support_rate | sample_supported_places |
| --- | --- | --- | --- | --- | --- | --- |
| 12 | 1 | Island | 31 | 0 | 0.0 | [] |
| 12 | 2 | River | 5 | 0 | 0.0 | [] |
| 12 | 3 | Lake | 20 | 0 | 0.0 | [] |
| 12 | 5 | Other | 208 | 0 | 0.0 | [] |
| 12 | 6 | Pond | 23 | 0 | 0.0 | [] |
| 13 | 3 | Cemetery/Morgue | 114 | 0 | 0.0 | [] |
| 13 | 4 | Other | 274 | 0 | 0.0 | [] |
| 13 | 5 | UNKNOWN_UNDOCUMENTED | 220 | 0 | 0.0 | [] |
| 3 | 1 | Center | 29 | 0 | 0.0 | [] |
| 3 | 2 | Library | 217 | 0 | 0.0 | [] |
| 3 | 5 | Other | 68 | 0 | 0.0 | [] |
| 4 | 10 | Other | 461 | 0 | 0.0 | [] |
| 4 | 11 | Pool | 50 | 0 | 0.0 | [] |
| 4 | 3 | Golf Course | 22 | 0 | 0.0 | [] |
| 4 | 7 | Recreational Center | 92 | 0 | 0.0 | [] |
| 4 | 9 | Playground | 1031 | 0 | 0.0 | [] |
| 6 | 2 | Ferry landing/terminal | 54 | 0 | 0.0 | [] |
| 6 | 6 | Marina | 53 | 0 | 0.0 | [] |
| 6 | 7 | Pier | 158 | 0 | 0.0 | [] |
| 6 | 8 | Bridge | 954 | 0 | 0.0 | [] |
| 7 | 1 | Center | 73 | 0 | 0.0 | [] |
| 7 | 3 | Market | 47 | 0 | 0.0 | [] |
| 9 | 1 | Church | 1321 | 0 | 0.0 | [] |
| 9 | 2 | Synagogue | 191 | 0 | 0.0 | [] |
| 9 | 3 | Temple | 17 | 0 | 0.0 | [] |
| 9 | 4 | Convent/Monastery | 9 | 0 | 0.0 | [] |
| 9 | 5 | Mosque | 8 | 0 | 0.0 | [] |
| 9 | 6 | Other | 40 | 0 | 0.0 | [] |

No subtype is promoted by this audit. Unsupported matches cannot establish a subtype support rate beyond confirmed matches.
## Matched REVIEW examples

| kaggle_row_id | kaggle_name | kaggle_address | kaggle_zipcode | commonplace_source_id | commonplace_name | commonplace_facility_type | commonplace_facility_type_label | commonplace_domain_code | commonplace_domain_label | commonplace_borough | commonplace_filter_decision | commonplace_address | commonplace_zipcode | distance_meters | match_method | match_confidence | match_status | matching_pass | evidence_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Matched INCLUDE subtype counts

| commonplace_facility_type | commonplace_domain_label | matched_rows |
| --- | --- | --- |

## Name-only REVIEW candidates — NOT accepted matches

| kaggle_name | commonplace_name | commonplace_domain_label | match_method | match_status |
| --- | --- | --- | --- | --- |
| Abyssinian Baptist Church | ABYSSINIAN BAPTIST CHURCH | Church | exact_name_only | REJECTED |
| Barclays Center | BARCLAYS CENTER | Center | exact_name_only | REJECTED |
| Bronx Library Center | BRONX LIBRARY CENTER | Library | exact_name_only | REJECTED |
| Brooklyn Historical Society | BROOKLYN HISTORICAL SOCIETY | Other | exact_name_only | REJECTED |
| Calvary Cemetery | CALVARY CEMETERY | Cemetery/Morgue | exact_name_only | REJECTED |
| Douglaston Golf Course | DOUGLASTON GOLF COURSE | Golf Course | exact_name_only | REJECTED |
| Ellis Island | ELLIS ISLAND | Island | exact_name_only | REJECTED |
| Governors Island | GOVERNORS ISLAND | Island | exact_name_only | REJECTED |
| Green-Wood Cemetery | GREENWOOD CEMETERY | Cemetery/Morgue | fuzzy_name_only | REJECTED |
| Greenbelt Nature Center | GREENBELT NATURE CENTER | Recreational Center | exact_name_only | REJECTED |
| Hell Gate Bridge | HELL GATE BRIDGE | Bridge | exact_name_only | REJECTED |
| Poe Park | POE PARK | Playground | exact_name_only | REJECTED |
| Prospect Park Lake | PROSPECT PARK LAKE | Lake | exact_name_only | REJECTED |
| Roosevelt Island | ROOSEVELT ISLAND | Island | exact_name_only | REJECTED |
| Schomburg Center for Research in Black Culture | SCHOMBURG CENTER FOR RESEARCH IN BLACK CULTURE | Library | exact_name_only | REJECTED |
| St. Patrick’s Old Cathedra | ST PATRICKS OLD CATHEDRAL | Church | fuzzy_name_only | REJECTED |
| Woodlawn Cemetery | WOODLAWN CEMETERY | Cemetery/Morgue | exact_name_only | AMBIGUOUS |
| Woodlawn Cemetery | WOODLAND CEMETERY | Cemetery/Morgue | fuzzy_name_only | AMBIGUOUS |
| Brookfield Place | BROOKFIELD PLACE | Center | exact_name_only | REJECTED |
| Andrew Heiskell Braille and Talking Book Library | ANDREW HEISKELL BRAILLE AND TALKING BOOK LIBRARY | Library | exact_name_only | REJECTED |
| New York Aquarium | NEW YORK AQUARIUM | Other | exact_name_only | REJECTED |
| Saint Augustine's Episcopal Church | ST AUGUSTINES EPISCOPAL CHURCH | Church | fuzzy_name_only | AMBIGUOUS |
| Saint Augustine's Episcopal Church | ST AUGUSTINES EPISCOPAL CHURCH | Church | fuzzy_name_only | AMBIGUOUS |
| Emmanuel Baptist Church | EMMANUEL BAPTIST CHURCH | Church | exact_name_only | AMBIGUOUS |
| Emmanuel Baptist Church | EMMANUEL BAPTIST CHURCH | Church | exact_name_only | AMBIGUOUS |
| Emmanuel Baptist Church | EMANUEL BAPTIST CHURCH | Church | fuzzy_name_only | AMBIGUOUS |
| St. Ann & The Holy Trinity Church | ST ANN & THE HOLY TRINITY CHURCH | Church | exact_name_only | REJECTED |
| Old Quaker Meeting House | OLD QUAKER MEETING HOUSE | Church | exact_name_only | REJECTED |
| Castle Clinton National Monument | CASTLE CLINTON NATIONAL MONUMENT | Other | exact_name_only | REJECTED |
| InterChurch Center | INTERCHURCH CENTER | Church | exact_name_only | REJECTED |

## Unmatched tourist-location examples

| name | address | zipcode | match_status |
| --- | --- | --- | --- |
| 47th Street - The Diamond District | 47th St. betw. Fifth & Sixth Aves. Manhattan, NY 10036, Midtown West | 10036 | UNMATCHED |
| 9/11 Memorial & Museum | World Trade Center (museum: 180 Greenwich St.) Manhattan, NY 1000, Lower Manhattan | 10007 | UNMATCHED |
| Abyssinian Baptist Church | 132 Odell Clark Place New York, NY 10030, Harlem | 10030 | REJECTED |
| Alice Austen House Museum | 2 Hylan Blvd. Staten Island, NY 10305, Staten Island | 10305 | REJECTED |
| Alice Tully Hall | 1941 Broadway Manhattan, NY 10023, Upper West Side | 10023 | REJECTED |
| Alvin Ailey American Dance Theate | 405 W. 55th St. Manhattan, NY 10019, Midtown West | 10019 | UNMATCHED |
| American Girl Place | 609 Fifth Ave. Manhattan, NY 10017, Midtown East | 10017 | UNMATCHED |
| American Museum of Natural History | Central Park West at 79th St. Manhattan, NY 10024, Upper West Side | 10024 | REJECTED |
| Apollo Theater | 253 W. 125th St.  Manhattan, NY 10027, Harlem | 10027 | UNMATCHED |
| arts>Brookfield Place | 230 Vesey St. Manhattan, NY 10281, Battery Park City | 10281 | UNMATCHED |
| Barclays Center | 620 Atlantic Ave. Brooklyn, NY 11217, Prospect Heights | 11217 | REJECTED |
| Bartow-Pell Mansion Museum | 895 Shore Rd. Bronx, NY 10464, Pelham Bay | 10464 | REJECTED |
| Bateaux New York | Pier 61, Chelsea Piers (23rd St. & Hudson River) Manhattan, NY 10011, Chelsea | 10011 | UNMATCHED |
| Bronx Brewery | 856 East 136th Street NY 10454, South Bronx | 10454 | REJECTED |
| Bronx Library Center | 310 E. Kingsbridge Rd. Bronx, NY 10458, Fordham | 10458 | REJECTED |
| Bronx Zoo | 2300 Southern Blvd. Bronx, NY 10460, Fordham | 10460 | REJECTED |
| Brooklyn Botanic Garden | 1000 Washington Ave. Brooklyn, NY 11225, Prospect Heights | 11225 | UNMATCHED |
| Brooklyn Bridge | Tillary St Brooklyn, NY 11201,Downtown Brooklyn | 11201 | UNMATCHED |
| Brooklyn Heights Promenade | Brooklyn-Queens Expressway Brooklyn , NY 11201, Brooklyn Heights | 11201 | UNMATCHED |
| Brooklyn Historical Society | 128 Pierrepont St. Brooklyn, NY 11201, Brooklyn Heights | 11201 | REJECTED |

## Matching policy and integrity

Fuzzy SequenceMatcher threshold: 0.94; exact-name coordinate threshold: 50m.
Shared Unicode/punctuation/address normalization is reused without removing meaningful name words.
Exact/fuzzy names require same ZIP or exact normalized full address; exact names may use <=50m coordinates.
Conflicting ZIP or >150m coordinates blocks acceptance. Multiple plausible records remain AMBIGUOUS.
EXCLUDE is diagnostic only after primary UNMATCHED; it never changes authoritative decisions.
One CommonPlace record claimed by multiple accepted Kaggle rows becomes AMBIGUOUS pending alias review.
Confidence is a name-evidence score, not a calibrated probability. Summary counts each Kaggle row once; full reports expose candidate pairs.
Audit signals are written to a separate interim copy. False means no accepted match, not proven non-tourist status.
CommonPlace source rows, taxonomy rules and INCLUDE/REVIEW/EXCLUDE pools remain unchanged.
No additional canonical rows, final attraction IDs or processed attractions.csv are created.
