# Ablations & Comparisons

The page follows TEST set in the six-page navigation. It reads only generated
outputs under `results/analysis/ablation_comparisons/` and offers exactly:

1. **R0 vs R2 — Rollback protection**
2. **R1 vs R3 — Editing-scope flexibility**
3. **R3 vs R4 — Advanced repair strategies**
4. **R0 vs R4 — Matrix-guidance comparison**

The fourth pair maps **R0 = no-matrix baseline**, **R4 = matrix-guided strategy**.
It requires the existing R0 and R4 TEST runs only. Its values/deltas are generated
under `r0_vs_r4_matrix/`, with **Delta (R4 - R0)**. If either input is absent,
the page names the missing R0 TEST or R4 TEST input. TRAIN and other strategies
are never substituted.

## Intended question versus empirical validity

Intended question: Does adding matrix-guided repair improve outcomes relative
to R0? Empirical validity: Are these runs sufficiently controlled to isolate
matrix guidance? The page presents both explicitly.

R0/R4 is not automatically a causal ablation. The offline audit checks population,
initial plans, model/config, budgets, scheduler, verifier/evaluator, and equivalent
prompt/repair logic, scope, acceptance, structural guards, candidate generation
and selection. Current source uses different prompt/parsing/guard paths and R4
has separate post-hoc selection. Both use whole-plan repair; R4 does not adopt
R3's widening schedule merely because it inherits its implementation contract.
Actual run metadata also has differing initial identities/implementations and
recorded configuration. The current fourth pair is **Descriptive comparison only**.

Only fully verified matrix-only component controls and a complete settings
snapshot permit **Controlled ablation**. Matching controls without complete
isolation may yield **Matched strategy comparison**; unknown/different controls
yield descriptive interpretation. Population/difficulty mismatch blocks deltas.
R3/R4 always retains **Strategy comparison — not a matrix ablation**.

## Sources and presentation

The page remains table-first: research question, classification, compatibility
checklist/repository audit, original/matched N, per-difficulty pairwise results,
mechanism evidence, one supplementary chart, definitions/coverage and provenance.
Easy/Medium/Human/All filters select generated rows with identical nonempty UID
cohorts. Explicit CLI intersection mode is labelled **Matched-query subset**, with
original N, matched N and excluded UIDs. It is never silently substituted.

PC/CS values retain original TEST Tables 1–2; costs/process retain Table 3 and
saved per-query rounds; evaluation retains all five Table 4 definitions. Candidate
versus accepted transitions, loop messages versus benchmark checks, complete
versus lower-bound tokens, raw evaluator exceptions and post-hoc outcomes remain
separate. No metric formula is implemented in this frontend. Definitions, exact
source cells and denominators are saved in `summary.csv` and documented in the
[offline README](../scripts/result_analysis/ablation_comparisons/README.md).

In the fourth pair, R4 shows logged supported/unsupported/no-relationship guidance,
support, structural guards, considered outcomes and initial/repaired selections.
R0's corresponding matrix-specific entries are **Not applicable**, never zero.
Machine-readable rows have blank numeric values and explicit N/A units; frontend
formatting and CSV export preserve that distinction. R0's general proposal and
outcome metrics remain applicable. Missing R4 evidence remains unavailable.

## Reproduction

```bash
.venv/bin/python -m scripts.result_analysis.ablation_comparisons.build_ablation_comparisons \
  --r0 experiments/subset_test-r0 \
  --r1 experiments/subset_test-r1 \
  --r2 experiments/subset_test-r2 \
  --r3 experiments/subset_test-r3 \
  --r4 experiments/subset_test-r4 \
  --test-reporting-dir test_result_analysis \
  --analysis-dir results/analysis/repair_strategies/test \
  --output-dir results/analysis/ablation_comparisons
```

Optional inputs are only R0–R4. The fourth pair needs no additional run, reporting
root or CLI flag. The output folder contains `summary.csv`, `mechanism.csv`,
`validity.json`, `metadata.json`; root tidy/index outputs use the four canonical
pairs. The obsolete generated comparison is retired on regeneration.

After final experiments, regenerate existing TEST tables/diagnostics, run the CLI,
and refresh/restart Streamlit. Source/output/code hashes remain mandatory; stale
outputs block display and require regeneration. No metric calculation or subprocess
runs on reruns. Other pages, experiment artifacts and metric definitions remain
unchanged.
