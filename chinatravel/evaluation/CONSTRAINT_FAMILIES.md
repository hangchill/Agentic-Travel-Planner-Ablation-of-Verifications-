# Deterministic constraint families

`classify_constraint(descriptor)` and `classify_constraints(descriptors)` analyze
`hard_logic_py` using AST parsing and static provenance, never DSL execution,
models, or NL keyword classification. Source strings, optional `hard_logic_nl`,
input ordering and positive 1-based indices are preserved.

Results add `family`, `classification_status`, `matched_pattern_id`,
`normalizer_version`, sorted concept/operator/candidate-family features and a
reason. Status is `mapped`, `unmapped`, `ambiguous`, or `compound`; only mapped
results receive a family. Invalid indices raise; malformed/unsupported DSL is
unmapped. Pattern IDs identify structural recognizers, not exact source strings.

| Family | Supported repository-style patterns |
| --- | --- |
| `trip_specification` | Direct day/people requirements |
| `party_resources` | Ticket, metro-ticket and taxi-car quantities |
| `monetary_budget` | Activity/transport spending bounded numerically, including daily/domain-specific spending |
| `accommodation` | Hotel identity/features, rooms/type, distinct-hotel counts |
| `dining` | Guarded restaurant names, cuisine, meal presence/counts |
| `attraction` | Guarded names/types/counts, including free-attraction counts |
| `transport_mode` | Required/forbidden modes and mode-use counts |
| `travel_extent` | Accumulated transport distance/duration |
| `schedule_order` | Clock/duration requirements, named-entity day placement, sequence flags |

Measured values are distinguished from filters: dining spending is budget, taxi
quantity is party resources, free-attraction count is attraction, and a restaurant
time window is schedule/order. Day-specific counts/meal presence retain their
domain family. Thresholds, POI names and variable names are not keywords.

Separate cross-family requirements are compound; mixed-domain selectors without
separate requirements are ambiguous. Same-family requirements may map together.
Unsupported result dependencies remain unmapped. The global function inventory
may include unused code; classification follows provenance reaching `result`.

Intentionally unmapped: unguarded entity identities, unknown calls/names,
constant-only results, unsupported syntax/arbitrary equivalent programs, direct
subscript access, `poi_distance`/`poi_recommend_time`, and malformed legacy strings.
No quote repair or NL guessing is applied. Static analysis does not prove runtime
validity, reachability or satisfiability; branch evidence is merged conservatively.

Patterns are grounded in `synthetic_query_generation/constraints.py` and native
translation examples. Expand coverage through reviewed fixtures and version rule
changes. Review coverage on real trajectories before interpreting a
[regression matrix](REGRESSION_MATRIX.md).
