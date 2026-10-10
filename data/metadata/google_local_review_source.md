# Google Local review source

Source: [Google Local Reviews (2021), UCSD McAuley Lab](https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/).

Snapshot coverage: through September 2021. Role: fixed offline review corpus for experimental subjective-constraint evaluation. Historical coverage is intentionally frozen for reproducibility and does not represent current Google listings or current review content.

Only complete New York metadata is cached for this stage. The official index documents 272,189 businesses and 33,459,761 reviews; actual metadata counts are verified by streaming the downloaded snapshot. The downloader discovers the metadata URL from the index and records filename, retrieval date, bytes and SHA-256 in the ignored raw cache. Ratings-only and 10-core files are not used.

Application identity comes only from the frozen processed restaurant and attraction CSVs. The persistent accepted mapping records unambiguous HIGH-confidence associations. Ambiguous, medium/low and shared-gmap_id candidates remain audit evidence. The matching report describes geographic filtering, deterministic normalization and thresholds. A same-source gmap_id with conflicting metadata variants is not accepted automatically.

Review download/extraction is deferred. The later downstream schema will retain rating, review_text, timestamp/date, gmap_id and canonical entity_id, while omitting reviewer names and profiles. Raw reviewer identities are not needed by the metadata matching stage.
