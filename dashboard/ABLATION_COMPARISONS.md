# Ablations & Comparisons

The page sits between TEST set and Strategy-Specific. It asks pairwise questions
rather than repeating every TEST table. Its only source is the offline builder's
outputs under `results/analysis/ablation_comparisons/`.

| Selector | Interpretation |
| --- | --- |
| R0 vs R2 — Rollback protection | Mechanism / ablation-like comparison; candidate regressions and R2 harmful-candidate rejection/preservation |
| R1 vs R3 — Editing-scope flexibility | Mechanism comparison; localization versus scheduled widening |
| R3 vs R4 — Advanced strategies | Strategy comparison — not a matrix ablation |
| R4 without vs with matrix — Matrix-guidance ablation | Controlled only when all recorded controls and treatment checks pass |

The page displays the research question, generated validity classification,
compatibility checklist, original/matched N, excluded UIDs for an explicitly
requested subset, difficulty-filtered common results, Right − Left deltas,
mechanism evidence, one optional metric chart, and command/provenance details.

## Sources and denominators

All values, deltas, sample counts, units, preferred directions and evidence coverage
are saved by the CLI. The frontend only filters/renames/plots rows; it never
computes a comparison metric. CSV downloads use the displayed dataframe.

- **PC**: original `table1_pc.csv` final/change/zero-failure/decreased cells.
  All-PC-pass rate uses its saved zero-failure count / query N. New violations and
  net change are explicitly labelled candidate-loop diagnostics from the shared
  proposal metric helper, including rejected proposals. Accepted regressions are
  a separate metric.
- **CS**: original `table2_cs.csv` final/change/zero-failure cells and strict >85%
  threshold count / N. Standard-check new/net transitions are unavailable rather
  than inferred from loop error messages.
- **Process**: saved per-query rounds, original `table3_repair_process.csv` token,
  completeness, time, plan-change, error-reply and cache rows. Explicit no-progress
  uses the shared analyzer's logged marker. Complete-token and lower-bound token
  definitions remain separate; lower-bound missing tokens never prove free calls.
- **Evaluation**: all five original `table4_eval_exp.csv` rows. Percentages are
  already 0–100; no additional scaling occurs. Raw CS micro includes the original
  evaluator-exception caveat. CS macro and all-pass remain distinct definitions.
- **Mechanisms**: original strategy analyzer hooks, validated candidate/accepted
  metrics, checkpoint raw-plan equality, logged R4 relationships/guards, validated
  R4 selection pool and existing TRAIN-matrix audit. Missing evidence is blank.

Every common row has its exact source row, denominator, known-value N and
unavailable reason in the page's definitions expander and `summary.csv`.
The full catalog and mechanism definitions are documented in
[`scripts/result_analysis/ablation_comparisons/README.md`](../scripts/result_analysis/ablation_comparisons/README.md).

## Safeguards

Population or difficulty mismatch blocks headline deltas. Explicit intersection
analysis must be requested using `--matched-query-subset`; the page labels it
**Matched-query subset**, retaining original N, matched N and excluded UIDs.
Other missing/differing controls downgrade to descriptive comparison. Initial
plans, implementation, scheduler, model/config, effective repair budgets,
verifier/evaluator, benchmark identities and intended differences are checked.
Only **Controlled ablation** permits causal language; the page otherwise displays
an explicit no-causal-effect warning. R3 vs R4 always retains its strategy
comparison label. R3 widening is scheduled, and R4 post-hoc selection is separate
from the final accepted TEST trajectory.

Missing R1 TEST never uses R1 TRAIN. Missing no-matrix R4 never uses R3 or the
with-matrix R4 run. Matrix ablation requires two independently bound R4 reporting
roots, explicit enabled/disabled flags, a declared complete matching control
snapshot, and verified TRAIN-only matrix provenance. Current metadata is never
edited to obtain a stronger classification.

## Reproduction and refresh

1. Finish final experiments.
2. Regenerate the existing TEST tables with their unchanged builder. Include all
   canonical strategies together; build no-matrix R4 into a separate reporting root.
3. Run the standalone comparison CLI with the final source paths. Optional
   partition-bound strategy diagnostics can be regenerated independently; the
   comparison CLI also reuses the same read-only analysis helpers directly.
4. Refresh/restart Streamlit. No dashboard source edits or file copying are needed.

Current command:

```bash
python -m scripts.result_analysis.ablation_comparisons.build_ablation_comparisons \
  --r0 experiments/subset_test-r0 \
  --r2 experiments/subset_test-r2 \
  --r3 experiments/subset_test-r3 \
  --r4 experiments/subset_test-r4 \
  --test-reporting-dir test_result_analysis \
  --analysis-dir results/analysis/repair_strategies/test \
  --output-dir results/analysis/ablation_comparisons
```

The CLI README includes complete future-run/no-matrix commands and the required
control metadata schema. No-matrix arguments are optional; unavailable comparisons
are emitted explicitly. Regenerating only one comparison is supported.

The loader verifies generated output hashes and recorded input/code hashes before
showing values. If inputs or analysis code changed, the page requests CLI
regeneration; it does not show stale deltas or launch a subprocess on rerun.
Missing output directories yield a generation hint without breaking the other
pages. This adds no global filters and leaves existing pages and numerical results
unchanged.
