# Final attraction manual-curation candidates

Evidence-only review table. The automatic 2,901 CommonPlace INCLUDE rows are untouched and excluded from this table. No final attraction IDs, processed attractions.csv, decisions, promotions or source union are created.
Total candidates: 257. Temporary CUR_ IDs track this fixed snapshot; they are not canonical IDs and may shift if snapshots change.

## Priority

| review_priority | candidates |
| --- | --- |
| HIGH | 190 |
| MEDIUM | 67 |
| LOW | 0 |

## Origin

| candidate_origin | candidates |
| --- | --- |
| COMMONPLACE_EXCLUDE_LANDMARK_SUPPORTED | 20 |
| COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | 33 |
| UNMATCHED_INDIVIDUAL_LANDMARK | 200 |
| UNMATCHED_SCENIC_LANDMARK | 4 |

## Selection and truncation

{
  "individual_gap_rows": 1429,
  "individual_signal_rows": 493,
  "excluded_keyword_infrastructure": 66,
  "excluded_keyword_private": 213,
  "pre_dedup_candidate_rows": 550,
  "post_dedup_candidate_rows": 548,
  "dedup_merges": 2,
  "individual_distinct_before_cap": 491,
  "individual_retained": 200,
  "individual_truncated": 291
}

All confident landmark-supported REVIEW/EXCLUDE identities and all active unmatched scenic records are retained. Only eligible unmatched/rejected individual records enter keyword screening.
Individual cap: 200, applied AFTER conservative deduplication. Sort by descending selection_score, normalized name, LP number, then landmark source ID. No LLM classification.
Keyword weights: {"bridge": 8, "castle": 8, "cathedral": 8, "church": 5, "concert": 8, "fort": 8, "garden": 8, "hall": 4, "historic": 4, "house": 2, "library": 8, "mansion": 2, "market": 8, "memorial": 8, "monument": 8, "museum": 8, "park": 8, "plaza": 8, "square": 8, "station": 4, "synagogue": 5, "temple": 5, "terminal": 8, "theater": 8, "theatre": 8, "tower": 4}.
Score = 10 × strongest keyword weight + 2 × keyword count (capped at 4) + 5 for institutional-name signal + 3 for nonempty designation address − 10 for explicit private-residence wording.
Institutional-name signal is the presence of documented institution/public-space keywords, not independently verified public access. A clear-address signal means a nonempty source designation address, not geocoding or verified visiting instructions.
Institutional keywords: bridge, castle, cathedral, church, concert, fort, garden, library, market, memorial, monument, museum, park, plaza, square, synagogue, temple, terminal, theater, theatre.
Explicit infrastructure exclusion regex: `\b(?:lampposts?|lamp\s*posts?|street\s*lights?|hydrants?|sewers?|ventilation|vent\s+structures?|maintenance|storage\s+tanks?|substations?)\b`.
Explicit private-residence regex: `\b(?:apartments?|residences?|residential|dwellings?|row\s+houses?)\b|^\s*\d+[\w-]*\s+.*\b(?:house|houses)\b`. Exclude these only without an institutional-name signal. House/mansion alone are weaker review signals, not proof of public access.
HIGH: all mandatory origins; very strong possible INCLUDE alias (similarity >=0.90 and <=50m or containment); or weight-8 keyword plus institutional-name and address signals. MEDIUM: other institutional-name signal or score >=40. LOW: remaining weaker retained records. Priorities do not decide inclusion.
## Conservative deduplication

Same CommonPlace source ID or same landmark source reference merges. Otherwise exact normalized landmark name plus same LP within 50m, or exact normalized name within 10m. Distinct CommonPlace identities and distant physical branches remain separate. Location comparisons use a fixed first-record anchor to prevent transitive proximity chains. All source evidence is combined in landmark_evidence JSON. The earliest mandatory origin wins over optional individual evidence.
## Possible INCLUDE aliases

Every retained candidate is searched against the 2,901 frozen INCLUDE rows. Potential evidence requires similarity >=0.65 plus a shared distinctive token (or similarity >=0.90), and distance <=150m or containment in a contributing landmark polygon.
Only the best candidate is displayed: highest name similarity, then shortest distance, then source ID. Candidate count records alternative suggestions. Names of constituent facilities inside a park may surface: these are possible alias/constituent evidence, not confirmed same-place identity.
Candidates with possible aliases: 23. Candidates with weak Kaggle name support: 6.
Kaggle support uses only existing name-only audit pairs, joined by CommonPlace source ID or exact normalized candidate/landmark name correspondence. It cannot originate a new candidate or confirm identity.
landmark_supported means a confident landmark-to-CommonPlace match; unmatched designated landmarks retain landmark_designated=true but landmark_supported=false.
Individual designation currency remains unverified because the source lacks a current flag. Source geometry/landmark-matching audits are preserved.

## Manual workflow

Edit final_attraction_curation_manual.csv as the primary review file. manual_decision, manual_reason and manual_notes start blank. The builder refuses to overwrite files with populated manual fields.
Allowed manual_decision vocabulary: ADD (add a new attraction later); DO_NOT_ADD (omit); ALIAS_OF_EXISTING (same place as an automatic INCLUDE row); NEEDS_REVIEW (undecided). Blank also remains undecided. No automatic decisions or final union are produced.
Join the compact and full tables using curation_candidate_id. Record alias source identity in manual_notes when useful.

## REVIEW subtype breakdown

| facility_type | facility_domain_code | facility_domain_label | candidates |
| --- | --- | --- | --- |
| 13 | 3 | Cemetery/Morgue | 4 |
| 13 | 4 | Other | 1 |
| 13 | 5 | UNKNOWN_UNDOCUMENTED | 1 |
| 3 | 1 | Center | 1 |
| 3 | 5 | Other | 2 |
| 4 | 10 | Other | 1 |
| 4 | 7 | Recreational Center | 1 |
| 6 | 2 | Ferry landing/terminal | 1 |
| 6 | 7 | Pier | 1 |
| 9 | 1 | Church | 18 |
| 9 | 2 | Synagogue | 1 |
| 9 | 6 | Other | 1 |

## EXCLUDE subtype breakdown

| facility_type | facility_domain_code | facility_domain_label | candidates |
| --- | --- | --- | --- |
| 1 | 2 | Private Development | 4 |
| 2 | 3 | Public High School | 3 |
| 2 | 7 | Post Secondary Degree Granting Institution | 1 |
| 7 | 2 | Business | 3 |
| 7 | 4 | Hotel/Motel | 4 |
| 8 | 1 | Government Office | 3 |
| 8 | 6 | Military | 1 |
| 8 | 7 | Other | 1 |

## Landmark source

| landmark_source | candidates |
| --- | --- |
| nyc_lpc_individual_landmarks | 252 |
| nyc_lpc_scenic_landmarks | 5 |

## Borough (known source codes normalized; original values preserved in landmark evidence)

| borough | candidates |
| --- | --- |
| Bronx | 24 |
| Brooklyn | 41 |
| Manhattan | 150 |
| Queens | 22 |
| Staten Island | 17 |
|  | 3 |

## HIGH-priority examples

| curation_candidate_id | candidate_name | candidate_origin | evidence_summary |
| --- | --- | --- | --- |
| CUR_0001 | BEDFORD PARK CONGREGATION CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (fuzzy_name_within_50m) |
| CUR_0002 | GRACE MEMORIAL HOUSE | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains) |
| CUR_0003 | JUDSON MEMORIAL CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains) |
| CUR_0004 | PARK EAST SYNAGOGUE | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains) |
| CUR_0005 | WEST PARK PRESBYTERIAN CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains) |
| CUR_0006 | ST PATRICKS OLD CATHEDRAL | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (fuzzy_name_polygon_contains); Kaggle name-only support (unconfirmed) |
| CUR_0007 | WHITEHALL FERRY TERMINAL | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_within_150m) |
| CUR_0008 | VERDI SQUARE | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains) |
| CUR_0009 | ANTIOCH BAPTIST CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains) |
| CUR_0010 | EMMANUEL BAPTIST CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains); Kaggle name-only support (unconfirmed) |
| CUR_0011 | GRACE CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains) |
| CUR_0012 | MARBLE COLLEGIATE CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains); Kaggle name-only support (unconfirmed) |
| CUR_0013 | METROPOLITAN BAPTIST CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains) |
| CUR_0014 | NEW LOTS REFORMED CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains) |
| CUR_0015 | RIVERDALE PRESBYTERIAN CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (exact_name_polygon_contains) |
| CUR_0016 | ROSSVILLE AME ZION CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (fuzzy_name_polygon_contains) |
| CUR_0017 | ST ALBANS EPISCOPAL CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (fuzzy_name_polygon_contains) |
| CUR_0018 | ST MARTINS EPISCOPAL CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (fuzzy_name_polygon_contains) |
| CUR_0019 | ST MARYS EPISCOPAL CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (fuzzy_name_polygon_contains) |
| CUR_0020 | ST NICHOLAS OF MYRA ORTHODOX CHURCH | COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | CommonPlace REVIEW row; confident LPC designated-landmark match (fuzzy_name_polygon_contains) |

## Unmatched scenic candidates and possible aliases

| candidate_name | possible_existing_include_name | possible_existing_include_distance_m | possible_existing_include_name_similarity |
| --- | --- | --- | --- |
| Fort Tryon Park | FT TRYON PARK | 123.90633129205582 | 0.9285714285714286 |
| Grand Army Plaza |  |  |  |
| Prospect Park | PROSPECT PARK ZOO | 480.6777933295133 | 0.8666666666666667 |
| Coney Island (Riegelmann) Boardwalk |  |  |  |

## Integrity

CommonPlace remains INCLUDE 2901, REVIEW 5790, EXCLUDE 11760, UNMAPPED 0, total 20451. Restaurants, rule metadata, automatic candidate base, Kaggle audit and landmark matching inputs are read-only.
All manual fields are blank. No final ATTR_ IDs, processed attractions.csv, automatic additions, commit or push.
