# Deterministic attraction finalization

The previous 257-row shortlist is preserved. Blank manual columns are superseded by deterministic auto decisions; no manual input or NEEDS_REVIEW state is required.
## Accounting

CommonPlace base: 2901. Shortlist: 257. Final attractions: 3066.
| auto_decision | candidates |
| --- | --- |
| ADD | 165 |
| DO_NOT_ADD | 91 |
| ALIAS_OF_EXISTING | 1 |

## Additions by origin

| candidate_origin | auto_add |
| --- | --- |
| COMMONPLACE_EXCLUDE_LANDMARK_SUPPORTED | 5 |
| COMMONPLACE_REVIEW_LANDMARK_SUPPORTED | 33 |
| UNMATCHED_INDIVIDUAL_LANDMARK | 124 |
| UNMATCHED_SCENIC_LANDMARK | 3 |

## Additions by final category (after deduplication)

| category | added_rows |
| --- | --- |
| garden | 3 |
| historic_site | 41 |
| landmark | 18 |
| market | 1 |
| museum | 5 |
| park | 28 |
| religious_site | 24 |
| sports | 1 |
| theater | 35 |
| transport_landmark | 9 |

## Policy

Patterns, scopes, category signals and fort abbreviation normalization live in attraction_auto_curation_rules.csv. Facility categories use exact type/domain pairs in attraction_category_mapping.csv.
Alias first: unique similarity >=0.94 within 50m; exact normalized name within 150m or exact-name polygon containment. Full candidate/landmark names are checked. Constituent-name suggestions from the earlier audit do not establish aliases. Multiple strong identities default to DO_NOT_ADD.
Then designated Scenic ADD; matched eligible REVIEW ADD unless explicit negative wording; supported EXCLUDE and unmatched Individual require a positive visitor-facing whitelist signal. Negative wording blocks positive/negative conflicts. No name-only Kaggle evidence causes ADD.
Source eligibility is validated against frozen landmark clean tables. Individual currency remains unverified because its source has no current flag. These rule-based choices are experimental visitor-relevance policy, not guarantees of public access.
All 2,901 automatic INCLUDE source identities are retained, including pre-existing same-name/location records. Final duplicate checks remove only additions with same source key, exact normalized name within 10m, or same landmark identity and exact name within 50m; no fuzzy deduplication of the base.
Duplicate/alias provenance is retained in attraction_duplicate_alias_audit.csv and the retained landmark_evidence field. Distinct physical locations remain separate.
## Persistent IDs

attraction_id_registry.csv maps persistent canonical source keys to ATTR_ IDs. Existing assignments and retired keys remain; new keys append above the highest assigned number. IDs are never reassigned by output position. Scenic keys use LP designation numbers; CommonPlace and Individual use source IDs.
## Final schema

attraction_id, name, category, subcategory, borough, latitude, longitude, source, source_id, is_landmark, landmark_source, landmark_source_id, tourist_relevance_source, facility_type, facility_domain_code, facility_domain_label, commonplace_filter_decision, curation_candidate_id, kaggle_name_support, landmark_evidence

No ratings, prices or opening hours are invented. Original CommonPlace decisions, facility taxonomy and landmark evidence remain provenance fields.
## Duplicate and alias resolutions

| curation_candidate_id | candidate_name | resolution | target_key | reason | target_attraction_id |
| --- | --- | --- | --- | --- | --- |
| CUR_0054 | Fort Tryon Park | ALIAS_OF_EXISTING | commonplace:15705 | Unique exact/near-exact name with close coordinates or exact-name polygon agreement | ATTR_0898 |

CommonPlace source/classification/rules, restaurant pipeline, previous shortlist and source audits remain unchanged. No commit or push.
