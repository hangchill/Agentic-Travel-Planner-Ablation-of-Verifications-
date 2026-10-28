# R0-R4 constraint trajectories

Run from the repository root using Python with the project evaluator
dependencies and Matplotlib installed (the current default Python has both):

```powershell
python r4\r0_r4_constraint_graph\plot_constraint_trajectories.py
```

For each of R0-R4, the folder contains two graphs in PNG and SVG:

- `rX_satisfied_counts`: average number of personal and commonsense constraints
  satisfied per query after attempts 1-6.
- `rX_net_change`: average change in those satisfied counts relative to the
  initial plan, before attempt 1.

Every point averages the same 30 held-out TEST queries. If a query stops before
attempt 6, its last accepted plan is carried forward. Rejected candidates do
not replace the accepted plan. Carried-forward positions are not additional
model calls. Personal constraints vary by request; commonsense always uses the
same 28 benchmark categories. The two types therefore have different maxima.
Net-change values are descriptive arithmetic differences, not significance
tests or isolated causal effects.

The script scores saved translated plans locally using the existing project
benchmark evaluator. It makes no model calls. It validates initial and final
per-query counts against `test_result_analysis/R0` through `R4`; the final
accepted plan must also match the corresponding saved benchmark export.

`attempt_summary.csv` provides cohort averages and totals for steps 0-6.
`per_query_attempt_scores.csv` provides all query-level counts, changes, real
attempt flags, and carry-forward flags. Step 0 is the baseline and is retained
in the data but omitted from the plotted x-axis as requested.
`source_manifest.csv` records source-table and evaluator fingerprints.
`benchmark_score_cache.json` speeds up reruns; `--refresh-scores` rescans saved
plans with the local evaluator.
