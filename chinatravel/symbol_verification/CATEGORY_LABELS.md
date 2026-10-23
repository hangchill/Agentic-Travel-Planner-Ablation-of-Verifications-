# Scoped category comparison normalization

`shared_verifier.check_personal_constraints()` and the benchmark
`evaluate_constraints_py()` both call `dsl.execute_dsl_code()`. Concept functions
read database cuisine/type/feature strings unchanged. Previously, Python compared
those strings directly with DSL literals, so English database labels failed
Chinese equality/membership/subset requirements.

`category_labels.normalize_category_label(value, domain)` now canonicalizes known
categorical aliases. After existing DSL validation, a comparison-only AST pass
normalizes BOTH operands when a categorical concept domain can be traced through
calls, assignments, collection mutation, or iteration. It does not rewrite source
strings, queries, plans, databases, or concept-function return values. Native
Python comparison evaluation and chained-comparison short-circuiting are retained.
No model/network/fuzzy matching is involved.

## Taxonomy provenance

`category_taxonomy.json` records the parallel published concept lists under
`restaurant_type`, `attraction_type`, and `accommodation_type` in:

- `chinatravel/agent/nesy_agent/nl2sl_hybrid.py`
- `chinatravel/agent/nesy_agent/nl2sl_hybrid_en.py`

The lists contain 42 aligned cuisine pairs, 13 attraction pairs, and 73 hotel
feature pairs. Chinese `图书馆` and `特色 住宿` have no English entry in these lists:
they were excluded BEFORE positional pairing to avoid shifting subsequent pairs.
These omissions remain unmapped; no translation was invented. The taxonomy is a
reviewable static snapshot and does not import prompts at runtime.

Canonical English aliases additionally reuse the explicit mappings in
`environment/concept_labels.py` (previously used by offline migration/audits).
`Sichuan food` is one additional explicit synonym requested for `Sichuan cuisine`;
there is no general food/cuisine suffix rule.

## Scope and limitations

- `restaurant_type`: cuisine; `attraction_type`: attraction category;
  `accommodation_type`: hotel feature/category.
- `activity_type`, `innercity_transport_type`, `intercity_transport_type`: basic
  formatting normalization only. Their DSL documentation uses English enum codes
  in both languages; no speculative Chinese transport/activity aliases are added.
- Numeric `room_type` is unchanged. POI/entity identities, city names, locations,
  free text, and plain literal-only comparisons are NOT translated/normalized.
- Known aliases accept case, whitespace, dash/apostrophe variants and equivalent
  hyphen/slash spacing. Unknowns retain NFKC/casefolded/trimmed text with collapsed
  whitespace; unrelated unknown strings are not translated or merged.
- Mixed concept domains and variables reused for categorical/noncategorical
  values are conservatively left unnormalized. This is structural DSL analysis,
  not an unrestricted Python type inference engine. Unsupported access patterns
  should receive explicit provenance support rather than broad string rewriting.
- Legacy flat `hard_logic` expression evaluation is outside this hard_logic_py fix.

The shared verification dictionary exposes `category_normalization` diagnostics:
`constraint_index`, `category_domain`, operand `expression`, `raw_label`, and
`normalized_label`. Original constraint/observed values remain untouched. Callers
of `execute_dsl_code()` or `check_personal_constraints()` can also pass an optional
`category_diagnostics` list. Diagnostics do not change success/error definitions
or summary/matrix formulas. Actual evaluation errors retain existing UNKNOWN
(shared verifier) versus failure (benchmark) handling.
