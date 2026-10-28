# Cross-strategy TEST comparisons

Run from the repository root:

```powershell
..\.venv\Scripts\python.exe r4\r4-analysis\cross_comparison\analyze_all_strategies.py
```

The script reads only the saved per-query tables in `test_result_analysis/R0`
through `R4`. It validates that all five strategies have the same 30 query IDs,
the same difficulty per query, matching personal-constraint denominators, and
28 scored commonsense checks. It writes `source_audit.csv`, `paired_scores.csv`,
`omnibus_tests.csv`, and `pairwise_tests.csv` in this folder.

## Outcomes and tests

- **Combined:** percentage of personal-constraint and commonsense checks passed
  per request, with each applicable constraint weighted equally.
- **Personal:** percentage of the request's personal constraints passed.
- **Commonsense:** percentage of 28 commonsense checks passed.

The omnibus test is Friedman repeated-measures across R0–R4, run once per
outcome for the full test set and for each difficulty group. Its p-values are
Holm-adjusted across 12 omnibus tests. Pairwise comparisons use a two-sided
paired label-swap permutation test on the mean score difference. All 120
pairwise p-values (10 strategy pairs × 3 outcomes × 4 cohorts) are Holm-adjusted
as one family. Difficulty rows are exploratory, with 10 paired queries each.
The pairwise CSV includes a flag showing whether the corresponding adjusted
Friedman omnibus test passed its gate.

For groups of 10 queries, the permutation distribution is enumerated
exhaustively; for the 30-query overall cohort, 100,000 Monte Carlo permutations
are sampled with a fixed seed. Tests compare saved runs and cannot isolate
strategy causality: each strategy may have produced a different initial plan,
and model outputs can vary across runs.
