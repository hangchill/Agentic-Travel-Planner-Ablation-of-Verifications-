"""Offline pairwise analysis. No Streamlit dependency or experiment execution."""

COMPARISONS = {
    'r0_vs_r2': ('R0 vs R2 — Rollback protection', 'R0', 'R2', 'mechanism comparison / ablation-like comparison',
                 'Does rollback/protection reduce harmful accepted regressions?'),
    'r1_vs_r3': ('R1 vs R3 — Editing-scope flexibility', 'R1', 'R3', 'mechanism comparison',
                 'Does scheduled repair-scope widening improve outcomes relative to localized repair?'),
    'r3_vs_r4': ('R3 vs R4 — Advanced repair strategies', 'R3', 'R4', 'strategy comparison',
                 'How do the two advanced repair strategies compare in quality, regressions, cost and behaviour?'),
    'r0_vs_r4_matrix': ('R0 vs R4 — Matrix-guidance comparison', 'R0', 'R4', 'intended matrix-guidance comparison',
                        'What changes when moving from the R0 no-matrix baseline to the matrix-guided R4 strategy?'),
}
DIFFICULTIES = ('Easy', 'Medium', 'Human', 'All')
