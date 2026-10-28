# R0 versus R4 satisfaction tests

Run from the workspace root with its existing Python environment:

```powershell
.\.venv\Scripts\python.exe .\Agentic-Travel-Planner-Ablation-of-Verifications-\r4\r4-analysis\significance\analyze_significance.py
```

The script reads the saved R0 and R4 per-query TEST tables and writes
`significance_tests.csv`, the difficulty-stratified results in
`difficulty_significance_tests.csv`, and the auditable input `paired_scores.csv`
in this folder. It does not regenerate scores or edit the source analysis.

## Outcomes and tests

- **Primary, combined satisfaction:** For each request, the percentage of all
  assessed personal constraints and 28 commonsense checks passed. The paired
  t-test tests whether the mean request-level satisfaction differs between R4
  and R0. The CSV includes the mean difference and its 95% confidence interval.
- **Secondary, personal satisfaction:** Percentage of that request's personal
  constraints passed. An exact paired sign test tests whether R4 improvements
  and declines are equally likely among non-tied requests.
- **Secondary, commonsense satisfaction:** Percentage of 28 commonsense checks
  passed. The same exact paired sign test is used.

All p-values are two-sided. Holm-adjusted p-values control the family-wise error
rate across the three overall outcomes. The difficulty CSV reports the same
three tests separately for Easy, Medium and Human requests (10 paired requests
per group); its Holm adjustment covers all nine subgroup comparisons. These
small subgroup analyses have limited power. The rows are paired by query ID;
each query is the analysis unit. The initial-plan hashes differ between R0 and
R4, so these tests compare the observed runs and do not isolate a causal
strategy effect.
