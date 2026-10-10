# Offline review corpus schema and policy

Source: Google Local Reviews (2021), UCSD McAuley Lab, complete New York review
split. Historical coverage through September 2021; intentionally fixed offline
corpus for experimental subjective-constraint evaluation.

`data/processed/restaurant_reviews.csv`:
`restaurant_review_id,restaurant_id,gmap_id,rating,review_text,review_date,source,source_review_key`.

`data/processed/attraction_reviews.csv`:
`attraction_review_id,attraction_id,gmap_id,rating,review_text,review_date,source,source_review_key`.

Review IDs are persistent RR_/AR_ identifiers. Source is `google_local_2021`.
Source review key hashes Google ID, NFC/whitespace-normalized text, rating and
original timestamp, without personal reviewer identifiers. This is a deterministic
content identity, not a Google-provided global review ID. Only exact identities
are deduplicated; merely similar reviews stay separate. Identical observations
from different people with identical content/rating/timestamp cannot be
distinguished under this identity-free deduplication policy.

UTC conversion assumes the source epoch values are milliseconds. Interim SQLite
retains original timestamp, UTC datetime and date, text presence, seeded sampling
rank and content key. Invalid/missing timestamps remain null and sort last.
Optional text is null, empty or whitespace-only when it contains no evidence.
Ratings-only observations remain in interim and source coverage counts, but do
not enter application-facing text corpora. Reviewer identity, photos and responses
are omitted from all derived review tables.

The cap is 100 unique text reviews per entity. If exceeded, keep 60 most recent
(timestamp descending, content-key tie break), then 40 additional historical
reviews in round-robin order across available ratings 1–5, with null ratings last.
Each rating stratum uses SHA-256 of `42:` plus source key for seeded selection.
Exhausted ratings are skipped, so no nonexistent ratings are oversampled.
Recent and historical selections never overlap. Up to 100 reviews are all kept.
The policy supports fixed evidence, snapshot recency, opinion diversity and
bounded LLM retrieval cost; it does not imply statistical representativeness.

Every review references a canonical entity and that entity's accepted HIGH Google
mapping. No matched entity or no text evidence means UNKNOWN, never a negative
subjective label. Availability is reported separately from frozen entity tables.
No reviewer profiles or subjective scores/labels are constructed.
