# Offline review corpus summary

{
  "provenance": {
    "review_sha256": "847fff4eb277aa9c0a257c7b3008bef641ef4bc6f65067cbe4edae2eccfb0687",
    "registry_sha256": "353476becaf464b0610eadacc411601cfdf7738efe7f8430dabd0e010b8369e5",
    "download": {
      "source": "google_local_2021",
      "download_url": "https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/review-New_York.json.gz",
      "retrieved_at": "2026-10-10T12:50:19.956649+00:00",
      "filename": "review-New_York.json.gz",
      "file_size_bytes": 2649939478,
      "sha256": "847fff4eb277aa9c0a257c7b3008bef641ef4bc6f65067cbe4edae2eccfb0687",
      "snapshot_coverage": "through September 2021"
    },
    "policy_version": 1
  },
  "raw_source_reviews": 33459761,
  "raw_matched_reviews": 596154,
  "timestamp_unit": "epoch milliseconds; UTC"
}

entity_type,canonical_entities,matched_entities,entities_with_source_reviews,entities_with_text_reviews,text_coverage_percent,raw_matched_reviews,text_reviews,ratings_only_reviews,exact_duplicates_found,duplicates_removed,entities_requiring_cap,entities_at_100,entities_below_cap,processed_reviews,date_min,date_max
restaurant,670,246,246,246,36.71641791044776,131200,73766,57434,1618,1618,158,158,88,20349,1990-12-31,2021-08-20
attraction,3066,641,641,638,20.808871493803,464954,231404,233550,6130,6130,254,254,387,36203,2008-02-04,2021-08-30

Historical snapshot through September 2021; fixed offline evidence, recent observations within that snapshot, rating diversity, and bounded LLM retrieval cost. The sample is not statistically representative of all Google reviews. Missing mapping or zero text reviews means UNKNOWN / review evidence unavailable, never negative subjective evidence. No subjective labels or reviewer profiles are created.

Cap 100: all unique text reviews retained up to the cap; otherwise 60 most recent plus 40 historical selections round-robin across available 1–5 ratings (null ratings last), each stratum ordered by SHA-256 of seed 42 and source review key. Timestamp ties use content key. Exact duplicates use gmap_id, normalized text, rating, and original timestamp; source_review_key is their SHA-256, with no user identity. Coverage source counts are before deduplication; unique counts and processed counts are separate. UTC epoch milliseconds conversion; invalid dates remain null and sort last. SQLite interim stores all unique accepted observations including ratings-only, without source names, user IDs, photos, or responses. IDs persist in append-only key registries, including formerly selected keys.
