# CommonPlace exploration — no canonical attractions dataset

Source: [NYC Open Data CommonPlace](https://data.cityofnewyork.us/City-Government/CommonPlace/t95h-5fsr).
Dictionary: [CityOfNewYork metadata](https://raw.githubusercontent.com/CityOfNewYork/nyc-geo-metadata/main/Metadata/Metadata_PointsOfInterest.md).
Only CommonPlace was downloaded; the dictionary documents this same source. No other POI source is merged.
Retrieval: `2026-10-10T09:23:53.216021+00:00`; raw SHA-256: `610349a84644efe7bc934c5a7708c9fdd0e08329c7e06dd8d9179c3bead00e89`.

## Overview

| metric | value |
| --- | --- |
| row_count | 20451 |
| raw_column_count | 21 |
| interim_column_count | 36 |
| exact_duplicate_rows | 0 |
| unique_names | 20233 |
| rows_with_duplicate_names | 418 |
| duplicate_name_groups | 200 |
| same_name_same_location_rows | 0 |
| same_name_different_location_rows | 418 |
| same_name_multiple_location_groups | 200 |
| near_duplicate_name_variant_groups | 1 |
| duplicate_objectid_rows | 0 |
| duplicate_placeid_rows | 0 |
| duplicate_agency_sourceid_rows | 86 |
| non_missing_complexid_rows | 7878 |
| shared_complexid_groups | 904 |
| coordinate_complete_rows | 20451 |
| invalid_coordinate_rows | 0 |
| facility_domain_codes | 18 |
| facility_types | 13 |
| unresolved_taxonomy_rows | 220 |
| unsupported_borough_code_rows | 4 |
| candidate_tourist_rows | 4736 |
| candidate_unlikely_rows | 4010 |

## Actual schema and missingness

| column | inferred_dtype | missing_count | missing_percentage |
| --- | --- | --- | --- |
| the_geom | str | 0 | 0.0 |
| SEGMENTID | float64 | 10 | 0.04889736443205712 |
| COMPLEXID | float64 | 12573 | 61.478656300425406 |
| SAFTYPE | str | 8914 | 43.58711065473571 |
| PLACEID | int64 | 0 | 0.0 |
| BIN | float64 | 6332 | 30.961811158378566 |
| SOURCE | str | 0 | 0.0 |
| OBJECTID | int64 | 0 | 0.0 |
| SOS INDICATOR | float64 | 581 | 2.840936873502518 |
| FACILITY DOMAINS | int64 | 0 | 0.0 |
| BOROUGH CODE | float64 | 211 | 1.031734389516405 |
| SOURCE ID | str | 14688 | 71.82044887780549 |
| CREATED_BY | str | 19469 | 95.198278812772 |
| CREATED_DATE | str | 2 | 0.009779472886411423 |
| MODIFIED_BY | str | 19570 | 95.69214219353577 |
| MODIFIED_DATE | str | 1503 | 7.349273874138183 |
| FACILITY TYPE | int64 | 0 | 0.0 |
| B7SC | float64 | 8930 | 43.665346437827004 |
| PRIMARY ADDRESS POINT ID | float64 | 7357 | 35.97379101266442 |
| FEATURE NAME | str | 0 | 0.0 |
| SECURITY LEVEL | int64 | 0 | 0.0 |

FEATURE NAME → name; FACILITY DOMAINS → facility_domain code; FACILITY TYPE → facility_type code;
BOROUGH CODE → borough_code; SOURCE → source_agency; OBJECTID → source_record_id;
PLACEID → source_place_id; SOURCE ID → source_agency_record_id; the_geom → raw WKT and longitude/latitude.
Raw codes and all 21 raw columns are retained. No missing values are imputed. No rows are filtered or deduplicated.
Coordinates are parsed from the source WKT POINT longitude/latitude values; no geocoding is used.

## Facility taxonomy

Important: FACILITY TYPE is the broad category; FACILITY DOMAINS is a subtype code scoped to that type.
Domain code 1 has different meanings across types. Never interpret a domain code independently.
Decoded labels are source documentation, not final attraction categories. Unmapped codes remain null.
The dictionary is older metadata; unresolved codes and future schema drift require review.

### Raw domain codes (all values)

| facility_domain | count | percentage |
| --- | --- | --- |
| 1 | 4053 | 19.81810180431275 |
| 3 | 4025 | 19.68118918390299 |
| 2 | 2570 | 12.566622659038678 |
| 8 | 1653 | 8.08273434061904 |
| 4 | 1626 | 7.950711456652486 |
| 7 | 1311 | 6.410444477042687 |
| 9 | 1111 | 5.432497188401545 |
| 6 | 846 | 4.136717030952031 |
| 5 | 796 | 3.892230208791746 |
| 10 | 719 | 3.515720502664906 |
| 11 | 706 | 3.452153928903232 |
| 12 | 561 | 2.7431421446384037 |
| 16 | 154 | 0.7530194122536795 |
| 13 | 103 | 0.5036428536501882 |
| 17 | 84 | 0.41073786122927974 |
| 15 | 80 | 0.39117891545645694 |
| 14 | 41 | 0.20047919417143417 |
| 18 | 12 | 0.05867683731846853 |

### Broad facility types (all values)

| facility_type | count | percentage | facility_type_label |
| --- | --- | --- | --- |
| 4 | 4111 | 20.101706518018677 | Recreational Facility |
| 2 | 3712 | 18.1507016771796 | Education Facility |
| 1 | 3057 | 14.947924306879859 | Residential |
| 6 | 2009 | 9.823480514400273 | Transportation Facility |
| 9 | 1586 | 7.755121998924258 | Religious Institution |
| 5 | 1510 | 7.383502029240624 | Social Services |
| 7 | 1010 | 4.9386338076377685 | Commercial |
| 8 | 915 | 4.474108845533226 | Government Facility (non public safety) |
| 13 | 780 | 3.8139944257004545 | Miscellaneous |
| 11 | 618 | 3.0218571219011294 | Public Safety |
| 3 | 588 | 2.8751650286049584 | Cultural Facility |
| 12 | 287 | 1.403354359200039 | Water |
| 10 | 268 | 1.3104493667791306 | Health Services |

### Largest type-dependent domain combinations

| facility_domain | facility_type | facility_domain_label | facility_type_label | count |
| --- | --- | --- | --- | --- |
| 3 | 1 | Public Housing Development | Residential | 2608 |
| 1 | 9 | Church | Religious Institution | 1321 |
| 1 | 4 | Park | Recreational Facility | 1274 |
| 9 | 4 | Playground | Recreational Facility | 1031 |
| 8 | 6 | Bridge | Transportation Facility | 954 |
| 2 | 5 | Day Care Center | Social Services | 875 |
| 7 | 2 | Post Secondary Degree Granting Institution | Education Facility | 842 |
| 1 | 2 | Public Elementary School | Education Facility | 745 |
| 8 | 4 | Sports | Recreational Facility | 654 |
| 11 | 6 | Water Navigation | Transportation Facility | 584 |
| 3 | 2 | Public High School | Education Facility | 469 |
| 10 | 4 | Other | Recreational Facility | 461 |
| 2 | 1 | Private Development | Residential | 385 |
| 4 | 7 | Hotel/Motel | Commercial | 363 |
| 2 | 2 | Public Junior High-Intermediate-Middle | Education Facility | 354 |
| 12 | 4 | Garden | Recreational Facility | 341 |
| 2 | 7 | Business | Commercial | 309 |
| 4 | 2 | Private/Parochial Elementary School | Education Facility | 284 |
| 4 | 13 | Other | Miscellaneous | 274 |
| 3 | 5 | Adult Day Care | Social Services | 257 |
| 1 | 8 | Government Office | Government Facility (non public safety) | 250 |
| 4 | 8 | Consulate | Government Facility (non public safety) | 226 |
| 5 | 13 |  | Miscellaneous | 220 |
| 2 | 3 | Library | Cultural Facility | 217 |
| 5 | 12 | Other | Water | 208 |
| 2 | 9 | Synagogue | Religious Institution | 191 |
| 3 | 8 | Post Office | Government Facility (non public safety) | 182 |
| 3 | 3 | Theater/Concert Hall | Cultural Facility | 179 |
| 7 | 8 | Other | Government Facility (non public safety) | 167 |
| 10 | 2 | Public K-8 | Education Facility | 163 |

## Borough distribution

| borough_code | count | percentage | borough |
| --- | --- | --- | --- |
| 1 | 5830 | 28.507163463889295 | Manhattan |
| 3 | 5562 | 27.196714097110164 | Brooklyn |
| 4 | 3756 | 18.36585008068065 | Queens |
| 2 | 3622 | 17.710625397291086 | Bronx |
| 5 | 1466 | 7.168353625739572 | Staten Island |
| (missing) | 211 | 1.031734389516405 |  |
| 8 | 4 | 0.019558945772822845 |  |

Unsupported borough code 8 is retained without inventing a borough name.

## Duplicate and feature identity exploration

Exact rows, names, OBJECTID, PLACEID, SOURCE+SOURCE ID and COMPLEXID are checked separately.
Same-name coordinate equality is exact, with no distance tolerance or canonical merging.
Repeated names may represent branches, constituents or generic labels. Shared COMPLEXID indicates grouping, not proof of identical features.
Case/whitespace-only name variants are surfaced separately without merging; fuzzy/geographic identity resolution remains future work.

### Same name, same location examples

| name | source_record_id | source_place_id | latitude | longitude |
| --- | --- | --- | --- | --- |

### Same name, different location examples

| name | source_record_id | source_place_id | latitude | longitude |
| --- | --- | --- | --- | --- |
| MADISON | 54 | 16703 | 40.814135426802 | -73.932373265544 |
| MACOMBS DAM | 27 | 9906 | 40.828043308349 | -73.934494158842 |
| MARBLE HILL HOUSES BUILDING 12 | 15083 | 1017746 | 40.874590433843 | -73.908383558502 |
| FIRST PRESBYTERIAN CHURCH | 9876 | 3668 | 40.696994864415 | -73.993538716238 |
| ST FRANCIS XAVIER SCHOOL | 3820 | 10420 | 40.848420897311 | -73.852448177004 |
| ST FRANCIS XAVIER CHURCH | 7383 | 15616 | 40.847984984251 | -73.853149918891 |
| SURROGATES COURT | 6078 | 2837 | 40.704543705542 | -73.808391576645 |
| JJ BYRNE MEMORIAL | 58 | 16716 | 40.733218965368 | -73.940533448131 |
| CEMETERY OF THE B'NAI JESHURUM | 4758 | 7012 | 40.690999609933 | -73.88222832198 |
| MARBLE HILL HOUSES BUILDING 1 | 13403 | 1005546 | 40.874625858682 | -73.908924050046 |

## Candidate tourist-relevant subset

Keyword matching uses only documented category labels actually observed in the source, not feature names.
Keywords: museum, gallery, park, garden, zoo, aquarium, historic, landmark, monument, cultural, theater, theatre, performing, recreation, visitor, attraction. This is exploration only, not a final inclusion rule.
Candidate rows: 4736.

Candidate domain distribution:
| facility_domain | count | percentage |
| --- | --- | --- |
| 1 | 1340 | 28.29391891891892 |
| 9 | 1031 | 21.769425675675674 |
| 8 | 654 | 13.809121621621623 |
| 10 | 461 | 9.733952702702704 |
| 12 | 341 | 7.200168918918918 |
| 2 | 224 | 4.72972972972973 |
| 3 | 201 | 4.244087837837838 |
| 4 | 144 | 3.040540540540541 |
| 6 | 109 | 2.30152027027027 |
| 7 | 92 | 1.9425675675675675 |
| 5 | 89 | 1.8792229729729728 |
| 11 | 50 | 1.0557432432432432 |

Candidate type distribution:
| facility_type_label | count | percentage |
| --- | --- | --- |
| Recreational Facility | 4111 | 86.80320945945947 |
| Cultural Facility | 588 | 12.41554054054054 |
| Miscellaneous | 37 | 0.78125 |

Candidate categories:
| facility_domain | facility_type | facility_domain_label | facility_type_label | count |
| --- | --- | --- | --- | --- |
| 1 | 4 | Park | Recreational Facility | 1274 |
| 9 | 4 | Playground | Recreational Facility | 1031 |
| 8 | 4 | Sports | Recreational Facility | 654 |
| 10 | 4 | Other | Recreational Facility | 461 |
| 12 | 4 | Garden | Recreational Facility | 341 |
| 2 | 3 | Library | Cultural Facility | 217 |
| 3 | 3 | Theater/Concert Hall | Cultural Facility | 179 |
| 6 | 4 | Zoo | Recreational Facility | 109 |
| 4 | 3 | Museum | Cultural Facility | 95 |
| 7 | 4 | Recreational Center | Recreational Facility | 92 |
| 5 | 3 | Other | Cultural Facility | 68 |
| 11 | 4 | Pool | Recreational Facility | 50 |
| 4 | 4 | Beach | Recreational Facility | 49 |
| 1 | 13 | Official Landmark | Miscellaneous | 37 |
| 1 | 3 | Center | Cultural Facility | 29 |
| 3 | 4 | Golf Course | Recreational Facility | 22 |
| 5 | 4 | Botanical Garden | Recreational Facility | 21 |
| 2 | 4 | Amusement Park | Recreational Facility | 7 |

Candidate examples:
| name | facility_type_label | facility_domain_label | borough | latitude | longitude |
| --- | --- | --- | --- | --- | --- |
| MCGOLRICK PLAYGROUND COMFORT STATION | Recreational Facility | Other | Brooklyn | 40.724827480825 | -73.943478646583 |
| THOMAS JEFFERSON PARK | Recreational Facility | Park | Manhattan | 40.793070363719 | -73.936113484306 |
| ARTHUR ASHE STADIUM | Recreational Facility | Sports | Queens | 40.749665456207 | -73.8469462415 |
| HARLEM GROWN 134 ST GREEN HOUSE | Recreational Facility | Park | Manhattan | 40.81410593537 | -73.943313433901 |
| RIVERSIDE PARK BASKETBALL COURTS W 111 ST | Recreational Facility | Sports | Manhattan | 40.806235003283 | -73.96974958994 |
| PELHAM BAY PARK RICE STADIUM | Recreational Facility | Sports | Bronx | 40.849162167749 | -73.822723726794 |
| PROSPECT PARK WILLINK HILL | Recreational Facility | Park | Brooklyn | 40.662003008286 | -73.96356475917 |
| DR RONALD MCNAIR PARK | Recreational Facility | Park | Brooklyn | 40.670853115747 | -73.961996682758 |
| RANDALLS ISLAND FIELD 63 | Recreational Facility | Sports | Manhattan | 40.782979677881 | -73.92453957718 |
| HIGH BRIDGE PARK POOL | Recreational Facility | Other | Manhattan | 40.842901197239 | -73.934137494374 |

## Exploratory potentially non-tourist categories

Keywords: school, education, government office, maintenance, utilities, storage, service facilities, administrative office. Only actual documented categories are surfaced; no exclusion is applied.
Rows: 4010.
| facility_domain_label | count | percentage |
| --- | --- | --- |
| Post Secondary Degree Granting Institution | 842 | 20.997506234413965 |
| Public Elementary School | 745 | 18.5785536159601 |
| Public High School | 469 | 11.69576059850374 |
| Public Junior High-Intermediate-Middle | 354 | 8.82793017456359 |
| Private/Parochial Elementary School | 284 | 7.082294264339152 |
| Government Office | 250 | 6.234413965087282 |
| Public K-8 | 163 | 4.064837905236908 |
| Private/Parochial High School | 160 | 3.99002493765586 |
| Private/Parochial K-8 | 154 | 3.8403990024937653 |
| Public School Building | 103 | 2.56857855361596 |
| Public Secondary School | 88 | 2.1945137157107233 |
| Private/Parochial K-12 all grades | 84 | 2.0947630922693268 |
| Private/Parochial Early Childhood | 80 | 1.99501246882793 |
| Transit/Maintenance Yard | 48 | 1.1970074812967582 |
| Public Early Childhood | 47 | 1.172069825436409 |
| Public School Annex | 41 | 1.022443890274314 |
| Private/Parochial Junior/Middle School | 39 | 0.972568578553616 |
| Public  K-12 all grades | 34 | 0.8478802992518704 |
| Other | 13 | 0.3241895261845386 |
| Private/Parochial Secondary School | 12 | 0.29925187032418954 |

## Observations for future canonical design

CommonPlace covers far more than visitor attractions; counts alone do not establish tourist completeness.
Paired taxonomy codes, repeated names, complex constituents and out-of-borough records require review.
Source fields provide no opening hours, admission prices or visitor ratings; no such metadata was inferred.
Source IDs are retained for traceability, not designated final attraction IDs.
Deterministic samples use five rows per observed domain code/type, random_state=42, after sorting source IDs.
No final inclusion/exclusion rule, final attraction ID or processed attraction table is produced.
