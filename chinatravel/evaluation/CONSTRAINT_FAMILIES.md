# Deterministic constraint families (Phase 3A)

`classify_constraint(descriptor)` returns a JSON-serializable dictionary.
`classify_constraints(descriptors)` preserves input order and original indices.
These pure helpers use `ast.parse` and static provenance propagation. They never
execute DSL, import the verifier, call models, or change repair behavior.

Input fields are copied, including exact `hard_logic_py`, optional
`hard_logic_nl`, and `constraint_index`. Indices must be positive integers;
invalid indices raise `ValueError` rather than being renumbered. Missing,
malformed, or unsupported DSL returns `unmapped` with a diagnostic reason.

Output adds:

```text
family: str | None
classification_status: mapped | unmapped | ambiguous | compound
matched_pattern_id: str | None
normalizer_version: "1.0.0"
features:
  concept_functions: sorted list of supported concept calls found in the AST
  operators: sorted AST operator names
  candidate_families: sorted families contributing result evidence
reason: str | None
```

The concept-call inventory includes unused code; classification follows value
and guard provenance reaching `result`, not the global inventory. Human text,
variable names, POI names, and threshold values are not classification keywords.
Pattern IDs describe structural family recognizers (`structural.<family>.v1`),
not unique exact-rule identities. Version the normalizer when rules change.

## Taxonomy and supported patterns

| Family | Supported repository-style structures |
| --- | --- |
| `trip_specification` | Direct day/people comparisons |
| `party_resources` | Ticket, metro-ticket, and taxi-car quantities, including mode/type guards |
| `monetary_budget` | Accumulated activity/transport spending with a numeric inequality; includes dining, hotel, attraction, and daily spending |
| `accommodation` | Room quantity/type, hotel feature, guarded hotel-name sets and distinct-hotel counts |
| `dining` | Guarded restaurant-name sets, cuisine sets, meal-type presence and counts |
| `attraction` | Guarded attraction names/types/counts, including counts filtered by zero activity cost |
| `transport_mode` | Required/forbidden mode sets, mode comparisons and mode-use counts |
| `travel_extent` | Accumulated transport distance or transport duration |
| `schedule_order` | Activity/transport clock comparisons, activity duration, named-entity day placement, and sequence flags |

Evidence comes from `synthetic_query_generation/constraints.py` and native
translation examples in `chinatravel/agent/nesy_agent/{nl2sl.py,prompts/prompts.py}`.
This is a deliberately limited template subset, not general DSL semantics.

Assignments, accumulators, local set/list additions, loops, comparisons,
Boolean composition and branch provenance are analyzed structurally. Measured
values are distinguished from selectors: a dining filter on a money accumulator
does not turn the budget into dining; a taxi guard on vehicle quantity does not
turn it into a transport-mode restriction. A zero-cost filter on an attraction
counter does not make the counter monetary. Clock requirements take precedence
over entity selectors within the same time-window predicate.

Separate recognized requirements from different families yield `compound`,
including the generator's result-list OR construction. A mixed-domain entity
selector without distinct requirements yields `ambiguous`. Neither receives a
family. Same-family requirements may map together. A recognized clause alongside
an unsupported result dependency is conservatively left `unmapped`.

## Intentionally not classified

- Unguarded named-entity existence: `activity_position(...) == 'some name'`
  does not establish whether the entity is a restaurant, hotel, or attraction.
- Unknown calls/names, imports, arbitrary methods, comprehensions, unsupported
  syntax, or constant-only `result=True/False` fixtures.
- Direct dictionary/subscript access, custom aliases to concept functions,
  general arithmetic rewrites, and arbitrary equivalent programs outside the
  supported subset. `poi_distance`/`poi_recommend_time` are not classified in v1.
- Malformed legacy strings remain unmapped; no heuristic quote repair is applied.
- NL-only hints never resolve missing structural domain information.

Static analysis does not prove runtime validity, reachability, satisfiability,
or equivalence. Branches are merged conservatively; multiple result writes retain
evidence even if later overwritten. Review mapping coverage on representative
native records before using classifications in scientific analysis.

## Decisions for the group

The implementation makes these explicit provisional choices: named-entity day
placement is schedule/order, while day-specific counts and meal presence retain
their domain family; monetary constraints retain budget despite domain filters;
multi-family predicates have no primary family. Agree on these boundaries and
expand patterns through reviewed fixtures, rather than guessing from NL text.
No matrix eligibility, attribution, or aggregation is implemented here.
