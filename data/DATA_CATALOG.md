# Final data catalog

Application/tool code consumes only `data/processed/`. Raw snapshots and interim
checkpoints support reproducibility; metadata contains source-of-truth rules and
persistent registries. Do not reset registries or refresh snapshots when reproducing
these frozen outputs.

| Dataset | Rows | Primary key | Foreign keys | Main source and purpose |
| --- | ---: | --- | --- | --- |
| `processed/restaurants.csv` | 670 | `restaurant_id` | None | Google Maps Kaggle identity/location/rating/price, with optional OSM hours/cuisine/diet evidence |
| `processed/attractions.csv` | 3,066 | `attraction_id` | None | CommonPlace base plus deterministically selected NYC LPC landmark-supported additions; identity/categories/provenance |
| `processed/restaurant_reviews.csv` | 20,349 | `restaurant_review_id` | `restaurant_id` → restaurants; `(restaurant_id,gmap_id)` → accepted Google registry | Historical Google Local text evidence for 246 restaurants |
| `processed/attraction_reviews.csv` | 36,203 | `attraction_review_id` | `attraction_id` → attractions; `(attraction_id,gmap_id)` → accepted Google registry | Historical Google Local text evidence for 638 attractions |

## Missing-value semantics

Missing restaurant price categories remain missing, without imputation. Experimental
price ranges are approximate; category 4 is open-ended, not an unknown bounded maximum.
Observed hours and assumed defaults remain distinguishable. Absent OSM dietary tags
mean unknown, not false. See [restaurant schema](metadata/restaurant_schema.md).

Attraction fields absent in a source remain null; no admission price, rating or hours
are inferred. Source taxonomy and category mappings retain experimental visitor rules;
they do not establish public access. Source/rule provenance remains in each row.

Review text is nonempty in processed corpora. Missing source timestamps remain null;
valid source epochs are converted as milliseconds in UTC. Some historical values are
unusually early (restaurant minimum 1990-12-31) and are preserved, not repaired.
No mapping or no text reviews means UNKNOWN / evidence unavailable, never negative
subjective evidence. Reviewer identity and subjective labels are omitted.
See [review schema/policy](metadata/review_corpus_schema.md).

## Construction and methodology

Restaurants use the Google Maps Kaggle source plus cached OSM enrichment. Numeric
prices derive from manual inspection of representative URLs, not guaranteed real-world
costs: 1 → $10–20; 2 → $20–40; 3 → $40–100; 4 → $100+. No estimated meal cost is defined.
Price mapping and public holidays remain metadata; `price_validation.csv` preserves
human-observation fields and the existing refusal to overwrite populated validation.

Attractions retain 2,901 CommonPlace INCLUDE identities and 165 rule-selected additions.
Filtering, category/auto-curation configuration, source-key IDs and taxonomy remain
in metadata. The shortlist builder is a reproducibility stage, not a required human
curation workflow. Its scoped signals, cap and alias safeguards remain unchanged in
construction code. Landmark geometry/status and matching decisions are documented in
[attraction sources](metadata/attractions_sources.md).

Google Local 2021 is intentionally frozen through September 2021. Conservative
name/location/address matching accepts 887 HIGH mappings (246 restaurants, 641
attractions). Ambiguous/shared Google IDs are excluded; thresholds and collision
handling remain in `scripts/reviews/google_local_matching.py`. New York-only metadata
limits coverage for canonical restaurants outside New York. Registry associations
cannot silently change. Review extraction scans 33,459,761 records, retaining 596,154
accepted-mapping observations: 305,170 text-bearing and 290,984 ratings-only.
Content/rating/timestamp exact deduplication removes 7,748 duplicate observations.
Processed text selection caps at 100: 60 recent plus 40 seeded rating-diverse historical
observations, with persistent RR_/AR_ IDs. The sample is not statistically representative.

## Necessary intermediates

- CommonPlace clean/classified/INCLUDE tables: source normalization, filtering and finalization inputs.
- Individual/scenic clean landmarks: geometry/status checkpoints for shortlist/finalization.
- Kaggle name-only evidence: weak provenance support only, never geographic confirmation.
- Landmark matching summary, REVIEW/EXCLUDE support and unmatched landmarks: shortlist/finalization inputs.
- Full and compact shortlist: candidate checkpoint and existing manual-edit overwrite protection.
- Google metadata clean table: geographic matching checkpoint; OSM records are extracted directly from cached raw JSON.
- Google matched-review SQLite: intentionally expensive single-pass, identity-free cache, Git-ignored; source/registry hashes validate reuse.

All these checkpoints live in `data/interim/`; production never reads `data/reports/`.
Reports are generated on demand by pipeline commands under `data/reports/`.
The entire directory is ignored by Git and is not tracked; it may be absent until
construction runs. Generated summaries and diagnostics are optional local inspection
artifacts, not committed documentation or pipeline inputs. This catalog and the
metadata documentation provide permanent dataset and methodology references.
Deleting generated reports does not affect construction.

Raw local snapshots are preserved and ignored by Git. Dependencies and Docker commands
are documented in the root README. Tests retain all 117 existing behaviors. Optional notebooks and historical
subtype-resolution reporting are removed; production requires neither.

## Minimal dependency chains and commands

Run these package commands from the repository root using the shared requirements
(or prefix with `docker compose run --rm data-pipeline python -m` instead of `python3 -m`).
Raw downloads and cached source metadata are preserved; do not refresh snapshots.

| Output | Required dependency chain | Minimal cached regeneration |
| --- | --- | --- |
| restaurants.csv | Google Maps CSV + restaurant ID/price metadata → core preprocessing → cached OSM JSON + hours/holiday helpers → enriched table | `python3 -m scripts.restaurants.preprocess_restaurants --enrich-osm` |
| attractions.csv | CommonPlace raw/dictionary → explore_attractions cleaning → filter_attractions; Kaggle raw → match_attractions_kaggle name evidence; LPC raw → audit_landmarks geometry/matches → build_attraction_curation shortlist; all + rules/categories/ID registry → finalize_attractions | `python3 -m scripts.attractions.finalize_attractions` |
| restaurant_reviews.csv | Frozen restaurant/attraction coordinates + Google metadata → google_local_matching accepted registry; full review gzip + registry → build_review_corpora SQLite extraction → text deduplication/sampling + RR registry | `python3 -m scripts.reviews.build_review_corpora` |
| attraction_reviews.csv | Same accepted registry/extraction/cache/sampling chain + AR registry | Built by the same review command |

The restaurant cached command intentionally uses the frozen canonical core already
present. Fresh raw reconstruction initializes that core with
`python3 -m scripts.restaurants.preprocess_restaurants` in an isolated construction
workspace before OSM download/enrichment. Preserve the ID registry. The initializer
refuses to overwrite an enriched schema. Full raw/checkpoint command sequences are
in the root README; skip downloads when valid local snapshots already exist.

`explore_attractions` and `audit_landmarks` remain construction stages despite their
historical names: they produce essential clean/taxonomy/geometry/matching inputs.
The compact shortlist remains to preserve the tested manual-edit overwrite guard;
manual decisions are not required for finalization. Shared normalization/distance
helpers are already reused. Google aliases/address cleaning and text identity helpers
have distinct semantics and are intentionally not conflated. No production stage
reads reports or notebooks. Review coverage is generated reporting only.
