# Data navigation and reproducibility

Application/tool code consumes only these frozen CSVs:

| File | Rows |
| --- | ---: |
| `processed/restaurants.csv` | 670 |
| `processed/attractions.csv` | 3,066 |
| `processed/restaurant_reviews.csv` | 20,349 |
| `processed/attraction_reviews.csv` | 36,203 |

`raw/` contains ignored source downloads. `interim/` contains reproducible pipeline
intermediates, audit inputs and intentionally expensive caches. All current
intermediates remain: reference searches found pipeline consumers or audit/cache
purposes. The 355 MB matched-review SQLite cache is ignored by Git and Docker image
contexts, and validated against raw/registry SHA-256 before reuse.

Metadata remains flat intentionally: configuration and registry paths are stable,
and Google review extraction provenance depends on the accepted registry bytes.
Restaurant ID, attraction ID, RR_/AR_ review ID and accepted Google entity registries
must not be reset. Source/rule/schema documentation lives alongside them.

## Final reporting layer

- `reports/restaurant_data_report.md`: restaurant policies and enrichment coverage.
- `reports/attraction_data_report.md`: final attraction universe and provenance.
- `reports/review_dataset_summary.md`: mapping versus text-review coverage.
- `reports/{restaurant,attraction}_review_report.md`: volume, ratings, dates and sampling.
- `reports/audit/{restaurants,attractions,reviews}/`: detailed tables and historical methodology evidence.
- `reports/verification/`: preserved prior execution reports and current cleanup verification.
- `reports/repository_cleanup_inventory.csv`: complete pre-cleanup file classification and old → current path mapping.

Detailed audit and historical verification files were moved without rewriting
content. Paths/commands recorded inside them describe the historical run; consult
the cleanup inventory for current destinations and the root README for runnable
package commands. Production writers now target the grouped audit paths.

## Evidence boundaries

Restaurant price ranges and default hours are experimental. Attraction rules do
not guarantee visitor access. Google Local evidence is frozen through September
2021; the review sample combines recency within that snapshot with rating diversity
and bounded retrieval cost, not statistical representativeness. Reviewer identity
is omitted from derived review data. Missing review evidence means UNKNOWN and
must not become a negative subjective label.

Production transformations live in domain packages under `scripts/`; notebooks
are read-only exploration. This cleanup changes paths/imports/navigation only,
with no threshold, schema, identifier, row-order or curation-policy changes.
