# R4 TEST analysis outputs

Start with [ANALYSIS.md](ANALYSIS.md) for results, interpretation and demo traces.

One source file controls all analysis: [test_results_r4.py](test_results_r4.py). The root test_results_r4*.csv files retain the compact Excel table and coverage audits.

| Folder/file | Purpose |
|---|---|
| r4/ | Initial/final quality, per-query costs, constraint rankings, events, phases, rounds and validation |
| r0_vs_r4/ | Paired differences, compatibility checks, and R0 detail tables |
| guidance/ | Mutually exclusive query/attempt groups and supported/unsupported edge outcomes |
| metric_definitions.csv | Definitions, units and denominators |
| source_manifest.csv | Exact artifact and evaluator fingerprints |
| figures/ | Reproducible SVG figures referenced by the Markdown report |

## Main tables to use

| Question | Start here |
|---|---|
| How well does R4 finish, by difficulty? | r4/overview.csv |
| What happens on each query, including token/time cost? | r4/per_query.csv |
| Which kinds/families are fixed or broken most? | r4/constraint_types.csv |
| What happens at each repair step for a particular constraint? | r4/query_trace.csv |
| Which of the 28 CS checks improve or regress? | r4/commonsense_checks.csv |
| What differs between R0 and R4 on the same request? | r0_vs_r4/paired_queries.csv |
| Which settings/initial plans differ? | r0_vs_r4/compatibility.csv |
| How do supported-only and mixed queries compare? | guidance/query_groups.csv |
| How do advice categories compare within repair phases? | guidance/attempt_groups.csv |
| Was the particular regression edge supported? | guidance/edge_outcomes.csv |

Empty numeric CSV cells mean unavailable/not applicable, not zero. Preserve denominators, difficulty, phase and scoring basis when copying a value into Excel. Category totals are mutually exclusive only within the same grain, group and phase.

Only the requested analysis modes are refreshed. Use --analysis all for a coherent full report. Raw run artifacts are read-only. No p-values are computed.
