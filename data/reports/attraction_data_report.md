# Final attraction data

`data/processed/attractions.csv` contains 3,066 frozen canonical attractions.
The universe retains all 2,901 CommonPlace INCLUDE identities and 165 additions
from the preserved shortlist under the existing deterministic finalization rules.
Stable ATTR_ IDs, source identities, categories, original taxonomy/filter decisions,
landmark evidence and tourist-relevance provenance remain in the final table.

CommonPlace is the base source. NYC LPC individual/scenic landmark exports support
name-and-location identity and shortlist evidence. Kaggle tourist locations remain
an audit signal; name-only candidates do not establish geographically confirmed
matches. The experimental rules do not guarantee tourist suitability or access.
No attraction ratings, prices, opening hours or subjective labels are inferred.

The historical shortlist is preserved as evidence. Manual curation is not required
for finalization. The finalizer resolves aliases conservatively and never turns
DO_NOT_ADD or ALIAS_OF_EXISTING decisions into additional canonical rows. Every
base INCLUDE identity remains retained, including documented existing duplicates.

Current production command: `python -m scripts.attractions.finalize_attractions`.
Configuration and persistent source-key/ID registries remain in `data/metadata/`.

Detailed evidence:

- [Automatic curation decisions](audit/attractions/attraction_auto_curation_report.csv)
- [Finalization methodology](audit/attractions/attraction_auto_curation_report.md)
- [Alias/duplicate audit](audit/attractions/attraction_duplicate_alias_audit.csv)
- [Historical shortlist](audit/attractions/final_attraction_curation.csv)
- [Source documentation](../metadata/attractions_sources.md)
- [Finalization verification](verification/attraction_finalization_verification.md)

Google entity matching and text-review coverage are separate evidence layers;
see [review summary](review_dataset_summary.md). Missing review evidence is UNKNOWN.
