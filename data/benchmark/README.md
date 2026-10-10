# Generalized NYC benchmark constraints

Version 2 has **18 generalized types**, replacing 66 top-level types. All 66 meanings
remain explicit variants selected by structured `value` fields; none are dropped.
The catalog's `legacy_type_mapping` and table below provide migration provenance,
not additional schema-valid top-level constraint types. The first 60 structured semantic cases are included; 180 frozen prompt variants are also included.
Destination remains fixed to NYC; arrival airports are JFK/LGA/EWR, while origin can vary.

## Variant resolution and support

Resolve a family using its category, operator and `value` selector (`kind`, or
subjective `target`/`attribute`). Resolve **variant-level** `currently_supported`,
`verification_type`, `default_hardness`, `data_source`, description and notes before
selecting a constraint. Family `currently_supported` means **at least one** variant
has evidence; it does not activate every variant. Family `verification_types` and
source/operator unions summarize possibilities, never override variant metadata.
For example attraction identity/category checks have data, but attraction rating does
not. Their distinct verification values are enforced by schema branches.

Supported counts remain 37 legacy meanings supported / 29 unsupported. Support means
evidence or declared plan-field availability, not an implemented verifier or guaranteed
per-entity decidability. Flight/accommodation/routing and other future-data meanings
remain unsupported. Absent diet/cuisine/review evidence is UNKNOWN. Meal prices remain
experimental intervals, never guaranteed or imputed meal cost. Whole-trip/component
budgets lack complete cost evidence. Reviews are historical through September 2021;
no subjective labels are introduced. Plan interval checks do not establish real-world
opening hours, booking availability or travel feasibility.

## Structured value contract

Attraction category inclusion uses `type=attraction_requirement`, `operator=include`,
`value={"kind":"category","value":"museum"}`. Entity inclusion/exclusion instead
uses kind=entity and an array of canonical IDs. Restaurant requirements select diet,
cuisine, rating or entity. All previous scalar/list/window values live inside the
structured envelope's `value` property without losing their original types.

Subjective quiet dining uses `type=subjective_preference`, `operator=prefer`,
`value={"target":"restaurant","attribute":"quiet"}`. For boolean subjective
preferences, omitted inner value means true; explicit true/false are preserved.
Crowdedness requires an explicit low/moderate/high value. Attribute/target pairs are
closed enums via per-variant schema branches; arbitrary subjective/other text is invalid.

`contains`/`excludes` migrate to `include`/`exclude`; eq/ne/gte/lte/in/not_in/between
retain their meanings. `prefer` is an additional eq alias for subjective preferences,
airline preference and preferred transport mode. Hardness remains independent: the
variant default is advisory, and a case can explicitly use hard or soft.
`in`/`not_in` wrap choice arrays inside the envelope; numeric/datetime between uses
an inner {min,max}. Time windows retain {start,end}; activity/meal windows retain
trip day and target fields. Time is NYC local wall time; datetime offsets must be
explicit and future trip dates resolve DST. Price/unit/count scopes remain in variant
metadata. Bounds are inclusive. Inner values remain required except the documented
boolean prefer shorthand.

## Schema and semantic validation

Cases retain semantic_case_id, difficulty, expected_solvability, trip_days, constraints
and metadata. Each constraint has constraint_id, generalized type, category, operator,
structured value, hardness, explicitness and resolved verification. Metadata's
constraint_types_present enumerates generalized families, not legacy variant names.
The schema checks every selector/operator/payload/verification combination. Unsupported
variants are representable with unavailable_until_data_added; schema validity does not
make a case executable.

UNSOLVABLE requires difficulty=unsolvable, unsat_reason and affected_constraint_ids;
SOLVABLE cases omit unsat fields. Missing evidence is not a logical contradiction.
The semantic validator checks unique IDs and affected-ID references, actual
canonical identities, trip_days consistency, day-index bounds, ordered numeric/time
bounds and exact metadata counts/sets. interaction_count uses the deterministic scope-pair rule documented below.
These cross-field arithmetic/reference invariants are not guaranteed by JSON Schema.

## Collective future coverage

Cover every supported family **and every supported variant** at least once, including
meaningful operator distinctions such as include versus exclude. Retain a variant-aware
coverage manifest so generalization cannot silently remove a meaning. Future-data
variants enter coverage after activation; deferred/inapplicable meanings need explicit
reasons. All ten categories appear at suitable difficulty levels once supported;
benchmark cases collectively include objective/subjective, explicit/implicit and
hard/soft constraints. Individual prompts remain realistic, not exhaustive catalogs.

Cross-category coverage includes flight+accommodation+budget;
accommodation+attraction+transport; attraction+food+schedule; food+budget+subjective;
full multi-domain trips; and defined other requirements mixed with normal categories.
The wording benchmark links three prompt variants to each frozen semantic case.

## Complete old → generalized mapping

| Generalized type | Previous types |
| --- | --- |
| `trip_requirement` | `trip_duration_days`, `number_of_travellers`, `traveller_type` |
| `flight_airport_requirement` | `required_departure_airport`, `required_arrival_airport` |
| `flight_time_constraint` | `departure_time_preference`, `arrival_time_preference` |
| `flight_requirement` | `direct_flight_only`, `airline_preference` |
| `accommodation_requirement` | `accommodation_type`, `minimum_hotel_rating`, `required_neighbourhood`, `accommodation_amenity` |
| `accommodation_time_constraint` | `check_in_constraint`, `check_out_constraint` |
| `accommodation_nightly_budget` | `accommodation_budget_per_night` |
| `attraction_requirement` | `required_attraction`, `excluded_attraction`, `attraction_category`, `avoid_attraction_category`, `minimum_attraction_rating` |
| `attraction_count_constraint` | `minimum_attraction_count`, `maximum_attraction_count` |
| `restaurant_requirement` | `dietary_requirement`, `cuisine`, `excluded_cuisine`, `minimum_restaurant_rating`, `required_restaurant`, `avoid_restaurant` |
| `meal_budget_constraint` | `meal_budget_per_person` |
| `transport_requirement` | `preferred_transport_mode`, `avoid_transport_mode` |
| `transport_limit` | `max_travel_time`, `max_walking_time`, `max_walking_distance` |
| `schedule_time_constraint` | `earliest_start_time`, `latest_end_time`, `required_activity_time`, `meal_time_constraint` |
| `schedule_requirement` | `max_activities_per_day`, `free_time_requirement`, `buffer_time_requirement` |
| `budget_constraint` | `total_budget`, `daily_budget`, `food_budget`, `attraction_budget`, `accommodation_budget`, `flight_budget` |
| `subjective_preference` | `quiet_restaurant`, `romantic_restaurant`, `authentic_restaurant`, `family_friendly_restaurant`, `good_for_groups_restaurant`, `scenic_attraction`, `family_friendly_attraction`, `educational_attraction`, `relaxing_itinerary`, `crowdedness_preference`, `cultural_trip`, `adventurous_trip` |
| `other_requirement` | `accessibility_requirement`, `weather_sensitive_preference`, `indoor_only_preference`, `avoid_repeated_categories`, `required_rest_period`, `special_event_requirement` |

Run `python3 -m pytest` or the root README's Docker test command. Tests validate all
variant/operator branches, support inheritance, migration semantics, structured values,
closed other/subjective selectors, fixed destination and unsatisfiability structure.


## Full-domain benchmark-design generation

```bash
python3 -m scripts.benchmark.generate_semantic_cases --random-state 42
python3 -m scripts.benchmark.validate_semantic_cases
python3 -m pytest
```

The generator writes `semantic_cases.jsonl` and `semantic_case_manifest.csv`: 60 cases,
15 per difficulty, with random state 42. Canonical rows are sorted before seeded
shuffling. The same seed and inputs produce byte-identical outputs. The semantic generator writes no prompt variants; the separate wording generator below
uses the frozen cases. No processed datasets or registries are written.

### Availability is a design assumption, not an implementation claim

The real catalog still has 37 supported and 29 unsupported variants. The catalog,
verification declarations and base `benchmark_schema.json` are unchanged. For this
benchmark generation only, variants in **flight, accommodation, transport and budget**
are treated as `AVAILABLE_FOR_BENCHMARK_DESIGN`. They use illustrative airport, airline,
time-window, hotel, neighborhood, amenity, transport-limit and USD budget values.
There are no flight, hotel, routing or complete cost datasets loaded or created.
Existing `unavailable_until_data_added` verification values remain unchanged on these
constraints, explicitly recording the status of the real verifier/data sources.

Every generated case includes two additional metadata fields:

- `benchmark_support_assumption`: true when any constraint uses an assumed domain;
  false otherwise, including unavailable-information cases outside those domains.
- `solvability_basis`: `assumed_full_domain_availability` for assumed cases,
  or `validated_current_data` for the remaining cases.

The strict existing schema forbids extra metadata. To keep that schema unchanged,
`validate_semantic_cases.py` validates its **core projection** after removing only
these two named extension fields, then validates the closed extension separately.
The extension requires a boolean tag and one of the two basis strings; both values
are recomputed from resolved variants. Direct validation of the extended JSONL against
only the base schema will reject these new fields: use the semantic validator for
this benchmark-design format. Arbitrary extra metadata is still rejected.

SOLVABLE cases in the assumed mode are **design-feasible**, conditional on future-domain
availability; they are not validated flight offers, hotel availability, routes, or
complete real-world budgets. Current-data-backed constraints still undergo canonical
entity, explicit diet/cuisine, rating, price-interval, count, and declared schedule
checks. A case without assumptions uses the existing offline evidence model.
Soft subjective preferences remain aspirations, not labels asserted from reviews.
Named restaurants/attractions always refer to the frozen canonical tables. NYC is
fixed, and New Jersey restaurant rows are excluded from current-data feasibility witnesses.

Unavailable-information cases deliberately retain variants outside the four assumed
domains: accessibility, indoor status, weather evidence, attraction rating and special
events. Assuming flight/hotel/transport/budget availability does not imply every entity
has every other attribute. `validated_current_data` on an UNSOLVABLE case describes the
basis of its failure diagnosis, not a claim that all its requested evidence is available.

### Metadata, interactions and validation

The manifest includes assumption/basis fields, JSON arrays of present categories/types/
variants, and per-case `category_distribution`, `type_distribution`, `variant_distribution`
JSON counters. Sum these counters to recover exact occurrence distributions, and count
the basis/tag columns to recover basis distributions and the assumed-case count. Variant keys use the catalog's stable legacy identifiers; there
are still only 18 schema-valid generalized types. Counts include every occurrence.
`subjective_constraint_count` includes LLM-only and combined verification.

`interaction_count` counts unordered pairs with identical effective scopes, or these
cross-scope pairs: trip+schedule, attraction+schedule, food+schedule, flight+accommodation,
flight+transport, accommodation+transport, and budget with flight/accommodation/food/
attraction/transport. Subjective restaurant targets use food scope, attraction/place
use attraction scope, and itinerary uses schedule scope. This deterministic structural
proxy counts both hard and soft constraints; it does not assert real routing or cost data.

The validator rejects unknown types/variants, invalid operators/values, unsupported
unassumed variants in solvable cases, inconsistent duration, invalid IDs/day indices,
reversed bounds, inaccurate metadata, duplicate semantic sets and unverified failures.
Duplicate detection ignores IDs, order, explicitness and derived metadata, sorts choice
lists and normalizes the documented preference alias/boolean shorthand.

The five machine-readable failure reasons each have three cases:
`contradiction`, `no_feasible_entity`, `impossible_schedule`, `impossible_budget`, and
`unsupported_information` (unavailable information). Affected constraint IDs must
exactly match the validator's diagnosis. Budget failures use known named-restaurant
price lower bounds, within the experimental range model; no real-world cost guarantee
is made. Trip-duration constraints agree with `trip_days` in every case.

All 18 types and all 66 catalog variants appear. All 37 real-supported variants and
all 24 benchmark-assumed variants appear in SOLVABLE cases. The five remaining
unsupported variants appear only in deliberate unavailable-information cases.

## Seed-42 full-domain coverage snapshot

All 60 cases remain split 15/15/15/15. Of the 45 SOLVABLE cases, **37** depend on
assumed future-domain availability and **8** use current-data validation. Including
the 15 diagnosed UNSOLVABLE cases, basis counts are **37 assumed / 23 current-data**.

| Category | Constraint occurrences | Cases containing category |
| --- | ---: | ---: |
| trip | 11 | 10 |
| flight | 38 | 21 |
| accommodation | 50 | 27 |
| attraction | 44 | 27 |
| food | 54 | 27 |
| transport | 28 | 23 |
| schedule | 26 | 22 |
| budget | 36 | 23 |
| subjective | 18 | 18 |
| other | 19 | 18 |

| Generalized type | Occurrences | Structured variants (occurrences) |
| --- | ---: | --- |
| `trip_requirement` | 11 | `trip_duration_days` 6; `number_of_travellers` 1; `traveller_type` 4 |
| `flight_airport_requirement` | 16 | `required_departure_airport` 6 [assumed]; `required_arrival_airport` 10 [assumed] |
| `flight_time_constraint` | 13 | `departure_time_preference` 7 [assumed]; `arrival_time_preference` 6 [assumed] |
| `flight_requirement` | 9 | `direct_flight_only` 5 [assumed]; `airline_preference` 4 [assumed] |
| `accommodation_requirement` | 28 | `accommodation_type` 9 [assumed]; `minimum_hotel_rating` 6 [assumed]; `required_neighbourhood` 8 [assumed]; `accommodation_amenity` 5 [assumed] |
| `accommodation_time_constraint` | 14 | `check_in_constraint` 7 [assumed]; `check_out_constraint` 7 [assumed] |
| `accommodation_nightly_budget` | 8 | `accommodation_budget_per_night` 8 [assumed] |
| `attraction_requirement` | 28 | `required_attraction` 12; `excluded_attraction` 5; `attraction_category` 5; `avoid_attraction_category` 5; `minimum_attraction_rating` 1 [unavailable] |
| `attraction_count_constraint` | 16 | `minimum_attraction_count` 10; `maximum_attraction_count` 6 |
| `restaurant_requirement` | 43 | `dietary_requirement` 3; `cuisine` 7; `excluded_cuisine` 4; `minimum_restaurant_rating` 4; `required_restaurant` 19; `avoid_restaurant` 6 |
| `meal_budget_constraint` | 11 | `meal_budget_per_person` 11 |
| `transport_requirement` | 11 | `preferred_transport_mode` 7 [assumed]; `avoid_transport_mode` 4 [assumed] |
| `transport_limit` | 17 | `max_travel_time` 7 [assumed]; `max_walking_time` 6 [assumed]; `max_walking_distance` 4 [assumed] |
| `schedule_time_constraint` | 20 | `earliest_start_time` 7; `latest_end_time` 6; `required_activity_time` 2; `meal_time_constraint` 5 |
| `schedule_requirement` | 6 | `max_activities_per_day` 2; `free_time_requirement` 2; `buffer_time_requirement` 2 |
| `budget_constraint` | 36 | `total_budget` 7 [assumed]; `daily_budget` 4 [assumed]; `food_budget` 7 [assumed]; `attraction_budget` 5 [assumed]; `accommodation_budget` 5 [assumed]; `flight_budget` 8 [assumed] |
| `subjective_preference` | 18 | `quiet_restaurant` 2; `romantic_restaurant` 2; `authentic_restaurant` 2; `family_friendly_restaurant` 1; `good_for_groups_restaurant` 1; `scenic_attraction` 4; `family_friendly_attraction` 1; `educational_attraction` 1; `relaxing_itinerary` 1; `crowdedness_preference` 1; `cultural_trip` 1; `adventurous_trip` 1 |
| `other_requirement` | 19 | `accessibility_requirement` 1 [unavailable]; `weather_sensitive_preference` 1 [unavailable]; `indoor_only_preference` 1 [unavailable]; `avoid_repeated_categories` 8; `required_rest_period` 7; `special_event_requirement` 1 [unavailable] |

Across 324 constraints: **306 hard / 18 soft**, **299 explicit / 25 implicit**.
Verification declarations remain **149 deterministic**, **15 LLM subjective**,
**3 deterministic plus LLM**, and **157 unavailable in real data**. Of those 157,
152 occurrences are assumed available for benchmark design and 5 remain unavailable.
All 66 variants have coverage; all 61 real-supported or assumed variants occur in
SOLVABLE cases. Each of the five failure reasons has three cases. The validator CLI
prints live distributions and the manifest carries per-case occurrence counters.


## Naturalized benchmark layers and regeneration

- **Semantic ground truth:** `semantic_cases.jsonl` contains 60 cases, canonical ATTR/REST
  IDs, exact ISO timestamps/numbers/operators, hardness, explicitness and verification.
- **Prompt layer:** `prompt_variants_naturalized.jsonl` contains 180 natural user-facing
  prompts, three styles per case. Internal entity IDs are hidden; canonical display
  names are resolved from processed tables. All 18 types and all 66 variants remain
  represented through semantic links.
- **Case manifest:** `semantic_case_manifest.csv` contains 60 case-level rows.
- **Prompt manifest:** `benchmark_manifest.csv` contains 180 rows, including prompt ID,
  semantic ID, difficulty, variant/style, request text, expected solvability, trip length
  and every case-level metadata/count/distribution field.

The incoming case manifest incorrectly contained 180 prompt rows. It was corrected to
60 case rows, while the prompt manifest was expanded to the full prompt-level contract.
These CSV corrections are intentional; neither naturalized JSONL was rewritten into
robotic wording. New CSVs reproduce byte-identically after this correction.

```bash
python3 -m scripts.benchmark.generate_semantic_cases --random-state 42
python3 -m scripts.benchmark.generate_prompt_variants --random-state 42
python3 -m scripts.benchmark.validate_semantic_cases
python3 -m scripts.benchmark.validate_prompt_variants
python3 -m pytest
```

The semantic generator reproduces the supplied JSONL's compact serialization and uses
`nyc_holiday_concert_2026_11_02` for the holiday event. Semantic data keeps canonical IDs;
prompts use title-cased all-uppercase canonical names while preserving existing mixed
case. Unresolved entity IDs fail clearly. No canonical names are embedded in code.

The previously naturalized text is frozen in independent sentence/order plans at
`scripts/benchmark/fixtures/naturalized_wording_plans.json`. Plans retain the supplied
introductions and modality framing, with constraint slots populated from semantic
values and canonical tables. They contain no hard-coded place names. Semantic digests
prevent silently applying a frozen wording plan to changed constraints or annotations.
Random state 42 is the frozen configuration; other wording seeds fail rather than
create a new experimental benchmark. No LLM or network calls are involved.

V1 is concise/direct, V2 conversational, V3 contextual/persona-style. Party/persona
context appears only where supported by the case. NYC remains the fixed implicit
destination. Three variants are repeated wording observations, not independent cases;
group splits and analysis by semantic_case_id. There are 45 prompts per difficulty,
111 assumed-domain prompt rows (37 cases), and 69 current-data rows (23 cases).

Validation resolves names against canonical data and normalizes case, accents,
punctuation, currency, unit conversions, clocks, and dates. It accepts `1500 metres` /
`1.5 km`, `60 minutes` / `an hour`, `USD 250` / `$250`, `18:00` / `6pm`, and local date/time
forms without requiring ISO strings or internal IDs. ISO offsets are converted to NYC
local time, not discarded. An omitted year uses the fixed 2026 semantic-date context;
this is not inferred from the execution date. Changed dates, values, entities and
polarity remain errors.

Validation is deliberately bounded: equivalent value surfaces and canonical name
normalizations are accepted within the frozen natural sentence plans. Clause coverage
and remaining framing detect missing/extra constraints and hard/soft changes. Semantic
digests preserve explicitness/hardness annotations; implicit subjective preferences
remain soft and implicit hard constraints retain mandatory intent. This is not an
unrestricted natural-language entailment model, so previously unreviewed paraphrases
may require extending the reviewed phrase aliases or sentence plans. It never requires
old controlled-language clauses or literal ATTR/REST IDs in requests.

**Experimental runs read these frozen artifacts; they never regenerate wording.**
Generation commands are explicit maintenance operations and reproduce all four corrected
artifacts byte-identically. No processed datasets, registries, catalog or schema semantics
are changed by this benchmark pipeline.
