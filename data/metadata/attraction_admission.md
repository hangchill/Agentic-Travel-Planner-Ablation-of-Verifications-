# Attraction admission evidence

The 3,066 attraction identities and their original 20 columns are unchanged.
CommonPlace and LPC provide coordinates and source IDs, but no admission fields,
OSM/Wikidata IDs, official URLs or source URLs on canonical rows. No price is inferred
from an attraction's category or name. Enrichment is a separate offline stage after
identity finalization; it never writes an ID registry or any benchmark artifact.

## Columns and price basis

Ten columns are appended to `data/processed/attractions.csv`:

| Field | Meaning |
| --- | --- |
| admission_price_type | One of the eight types below |
| admission_price_usd | Exact ordinary admission cost, only for free/fixed |
| admission_price_min_usd | Defensible lower bound, when available |
| admission_price_max_usd | Defensible upper bound, when available |
| admission_price_raw | Original OSM tags, Wikidata statement or official price text |
| admission_price_source_type | official, wikidata or osm; blank without selected evidence |
| admission_price_source | Source feature/entity/offer URL; multiple URLs for unresolved conflicts |
| admission_price_observed_date | UTC snapshot retrieval date, not a guarantee of current ticket validity |
| admission_price_is_estimated | false; the pipeline does not manufacture estimates |
| admission_price_basis | General admission per person, or the explicitly retained ticket basis |

The intended numeric basis is standard adult/general admission per person in USD.
Unqualified USD OSM charges on an attraction itself are treated as ordinary admission.
Bare amounts, foreign currencies and malformed charges produce no USD number. `$`
means USD only in these NYC source snapshots. No currency conversion is performed.
Child/senior/resident/membership/group/tour/event/time-dependent prices are not silently
selected. Conditional fee tags and unresolved ticket categories are variable.

| Type | Numeric meaning |
| --- | --- |
| free | Reliable explicit evidence; exact USD = 0 |
| fixed | Defensible exact ordinary adult/general price |
| from | Known minimum; maximum and exact price remain null |
| range | Reliable minimum/maximum; exact price remains null |
| variable | Unresolved ticket/time/category variation; no invented number |
| pay_what_you_wish | Explicit voluntary/suggested contribution; only an explicitly stated minimum supplies a lower bound |
| paid_unknown | Reliable paid status, amount unavailable or unsuitable for this basis |
| unknown | No defensible admission-status evidence; all numeric fields null |

CSV nulls are empty cells. NULL is not free. OSM evidence can be incomplete or stale;
a known free admission fee also excludes separately required transportation (for
example, a ferry), which belongs to the transport budget.

## Sources, matching and conflict policy

Precedence is associated official structured admission records → Wikidata P2555 → OSM.
The official adapter accepts a `records` array with `external_id`, `source_url`,
`associated_source`, `associated_source_id`, `scope="admission"`, `basis`, `price_raw`
and optional `fee`, `name`, `latitude`, `longitude`. Exact numeric admission requires
`basis="standard adult per person"` or `"general admission per person"`. The source
and source ID must match an existing canonical source key uniquely. These records
must come from an authoritative associated source; an arbitrary asserted ATTR ID or
name does not establish identity. No associated official price feed was available in
this initial snapshot, so the official tier contributed no values.

OSM matches require exact shared normalized names and coordinates within 100 metres.
Coordinates alone and weak/fuzzy/name-only matches are rejected. More than one
plausible canonical identity is AMBIGUOUS; no nearest-candidate tie-break is used.
Only whole tourism museum/attraction/zoo/aquarium/theme_park/gallery/viewpoint or
leisure park/garden/nature_reserve features qualify. Parking, toilets, charging
stations and private/no-access features cannot establish admission prices. Subsidiary
parking/internet/toilet fee keys are ignored. `fee=no` establishes free admission;
`fee=yes` alone establishes paid_unknown. Clean USD `charge` can supply an amount,
range or minimum; conditional charges remain variable.

Wikidata entities are fetched only through QIDs on accepted OSM identities. P2555
statements are propagated through accepted OSM IDs, not Wikidata labels. A QID linked
to multiple canonical identities is quarantined. Deprecated statements are excluded.
Qualifiers are retained and treated conservatively as unresolved variable pricing.
Unqualified positive P2555 quantities establish paid status only: they do not prove a
standard adult/person basis. Unqualified no-value/zero fees establish free status.
See [P2555](https://www.wikidata.org/wiki/Property:P2555),
[OSM fee](https://wiki.openstreetmap.org/wiki/Key:fee) and
[OSM charge](https://wiki.openstreetmap.org/wiki/Key:charge).

Only ACCEPTED matches with admission evidence enrich the canonical table. Matching
artifacts retain source/external ID, method, distance in metres (`match_score`), names,
status, candidate IDs and normalized record. Identical top-tier prices select a stable
representative, with all observations retained in the matching artifact. Disagreements
at different authority tiers use the highest tier, even if its amount is unknown;
all competing records are retained in the conflict checkpoint. Disagreement within
the highest tier becomes variable with null numbers and combined source text/URLs.
Lower-tier evidence never silently fills an authoritative unknown price.

## Cached stages and commands

Explicit retrieval, using the shared Docker environment:

```sh
docker compose run --rm data-pipeline python -m scripts.attractions.download_admission_sources
```

The downloader saves exact Overpass JSON and linked Wikidata entities under the
Git-ignored `data/raw/attractions/admission/`, plus `retrieval_metadata.json` with
source URLs, retrieval timestamps, query/version/bounding box and raw SHA-256 checksums.
Wikidata metadata also records entity URLs and the OSM snapshot checksum. Valid caches
are reused; only `--refresh` requests replacement. An optional `--official-url` fetches
an associated source's structured records in the format above. There is no live
network request during enrichment or tests. Preserve snapshots when reproducing results;
a deliberate refresh can change evidence without changing canonical identities.

After `python3 -m scripts.attractions.finalize_attractions`, or on the existing canonical
identity table, run:

```sh
python3 -m scripts.attractions.enrich_admission_costs
python3 -m scripts.attractions.enrich_admission_costs --report data/reports/attraction_admission_coverage.json
```

Offline processing verifies snapshot checksums and writes four deterministic checkpoints
in `data/interim/`: `admission_cost_records.jsonl`, `admission_cost_matches.jsonl`,
`admission_cost_accepted.jsonl`, `admission_cost_conflicts.jsonl`. The last step appends
cost fields to the canonical CSV while checking every pre-existing field for equality.
It requires 3,066 unique ATTR_ identities. Reports are optional, generated on demand,
untracked, and never runtime inputs. Repeated processing of the same core/snapshots is
byte-identical. Raw snapshot retrieval dates are used instead of the processing date.
Tests use local synthetic fixtures and explicitly prohibit HTTP calls.

## Initial snapshot coverage

321 OSM fee records and 24 confidently linked Wikidata entities were inspected. One
entity supplied P2555, with a qualifier that prevents selecting an exact price.
There are 32 accepted external observations, 0 ambiguous and 290 rejected observations;
multiple accepted observations can concern the same attraction. One cross-source
conflict is retained and resolved by precedence.

| Admission status | Attractions |
| --- | ---: |
| free | 10 |
| fixed | 0 |
| from | 0 |
| range | 0 |
| variable | 9 |
| pay_what_you_wish | 1 |
| paid_unknown | 9 |
| unknown | 3,037 |

Selected sources: OSM 28, Wikidata 1, official 0. Admission-status evidence is
29/3,066 (0.946%); exact deterministic prices are 10/3,066 (0.326%), all known free.
Any usable numeric bound is 10/3,066 (0.326%), supplied by those exact zeros.
These are evidence coverage figures, not claims of complete/current ticket-price coverage.
No positive exact price or nonzero bound was defensibly available in this snapshot.

## Future budget policy

Attraction expenditure is mandatory admission plus an explicitly user-specified
incidental allowance. The default incidental allowance is **0** for hard-budget
verification; this does not predict actual discretionary spending. Souvenirs/snacks
are not attraction facts and have no invented per-attraction estimate. No planner or
budget verifier exists here, so this is a documented data-layer policy only.

For selected attractions and budget B: free contributes exact zero; fixed contributes
its exact price; range supplies lower/upper bounds; from supplies only a lower bound.
Variable/pay_what_you_wish/paid_unknown/unknown supply no fabricated exact cost. Use
source-backed bounds only where supported. Add any explicitly requested incidental
allowance to both bounds.

- **FAIL** if known/lower-bound total already exceeds B.
- **PASS** if every selected attraction has a sufficiently known upper bound and the total is ≤ B.
- **UNKNOWN** otherwise; unknown admission is never converted to zero for a PASS.

Thus $80 exact against $100 passes; $120 known costs against $100 fails; $60 known
plus unknown admission against $100 remains unknown. Required transport and other
components must be handled separately by the future verifier. Frozen benchmark
support declarations remain untouched until the later full-domain support audit.
