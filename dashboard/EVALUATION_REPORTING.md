# Table 4: ChinaTravel Evaluation Metrics

Final TEST benchmark reporting only. There is no Table 4 repair-round view and no
benchmark scoring in the dashboard. Difficulty × Strategy filtering, run binding,
population checks, provenance/freshness warnings and CSV downloads reuse the
Tables 1–3 infrastructure. Those tables' numerical behavior is unchanged.

## Audited pipeline and source artifacts

Audited before implementation:

1. `scripts/result_analysis/evaluate_repair_run.py` delegates to
   `chinatravel/evaluation/export_final_plans.py:evaluate_repair_run`.
2. The exporter reads the authoritative checkpoint's
   `final_verification.translated_plan`, never a rejected candidate or R4 post-hoc
   best-seen selection. Missing/failed plans export as `{}` and remain in the
   declared population rather than being dropped.
3. `eval_exp.py:evaluate_final_plans` evaluates schema, commonsense and reference
   hard-logic constraints. It writes `benchmark_eval/<strategy>-*/schema.csv`,
   `commonsense.csv`, `logical_py.csv`, and `benchmark_summary.json`.
4. `scripts/result_analysis/build_test_result_tables.py` writes
   `test_result_analysis/<strategy>/table4_eval_exp.csv` using `table_eval_exp()`.
   Its upstream build_queries/score_plans scores exported final plans with the
   same evaluator functions and persists per_query.csv.
5. The dashboard reads the bound generated Table 4. Filtered query cohorts call
   the unchanged `table_eval_exp()` helper on saved per-query benchmark fields,
   not a verifier or evaluator and not loop trajectory scores.

Main table mappings:

| Displayed metric | Exact table4_eval_exp.csv row |
|---|---|
| Commonsense micro* | Commonsense micro (%) - share of all (plan, check) pairs passed |
| Commonsense macro | Commonsense macro (%) - plans passing every CS check |
| Logical micro | Logical micro (%) - share of all personal constraints passed (pooled) |
| Logical macro | Logical macro (%) - plans passing every personal constraint |
| All-pass ratio | All-pass ratio (%) - schema + CS + PC all passed |

Easy, Medium, Human and All come directly from the source columns, with Medium
presented as Med. Source values are already percentages. The dashboard **never
multiplies them by 100 again**. Main/profile cells display two decimal places and
an explicit percentage unit. All is the aggregate cohort, not an independent
fourth difficulty or another statistical sample.

## Exact definitions

Let N be the number of evaluated queries/plans. Let C be the count of raw
commonsense result-matrix columns excluding data_id, including the evaluator
exception column if it exists. Let F be the sum of raw failure-marker cells.
Let L_i be query i's actual reference hard_logic_py constraint count and P_i its
number of passing reference constraints. Hard-logic padding columns are not actual
constraints and do not contribute to the denominator.

| Metric | Source CSV/helper | Evaluator implementation | Numerator | Denominator | Aggregation and conversion |
|---|---|---|---|---|---|
| Commonsense micro* | table4_eval_exp.csv / table_eval_exp | commonsense_constraint.py:evaluate_commonsense_constraints | N×C − F | N×C raw matrix cells | Pooled cells, 100×(1−F/(N×C)); reporting rounds to 2 decimals |
| Commonsense macro | same | evaluate_commonsense_constraints | Plans completing CS evaluation with raw row failure sum zero | N | 100×CS-success plans/N |
| Logical micro | same | hard_constraint.py:evaluate_hard_constraints_v2 | Sum P_i | Sum L_i | Pooled reference constraints, 100×sum(P_i)/sum(L_i) |
| Logical macro | same | evaluate_hard_constraints_v2 | Plans satisfying every actual reference hard_logic_py constraint | N | 100×all-PC-pass plans/N |
| All-pass ratio | same | eval_exp.py:evaluate_final_plans | Size of schema_pass ∩ commonsense_pass ∩ logical_pass | N | 100×three-way-success count/N |

These definitions come from evaluator code, not inference from metric names.
`table_eval_exp()` reproduces them from saved fields:

- CS micro: `100 * (1 - sum(cs_failed_raw_final) / sum(cs_total_raw_final))`.
- CS macro: `100 * count(cs_failed_raw_final == 0) / N`.
- Logical micro: `100 * sum(pc_passed_final) / sum(pc_total)`.
- Logical macro: `100 * count(pc_failed_final == 0) / N`.
- All-pass: `100 * count(all_pass_final) / N`; that flag was saved from the actual
  three-way success-set membership, not reconstructed from aggregate percentages.

The helper rounds percentage results to two decimals. Micro pools individual
cells/constraints; macro counts whole successful plans. Ordinary logical metrics
are not gated on CS or schema. The evaluator also returns separate conditional
logical metrics based on env_pass_id; those are **not** the Table 4 metrics shown.

Filtered/difficulty summaries retain the raw column population from the original
persisted evaluation. For example, an exception column introduced elsewhere in a
run remains part of that run's raw cell denominator for a difficulty slice. The
existing helper already uses this convention. The dashboard does not re-evaluate
a subset and thereby change its check-column universe.

## Error and missing-data handling

- CS evaluator exceptions are caught, add `Commonsense Evaluator Exception = 1`,
  and do not add that plan to the CS-success set. Earlier/unvisited standard
  categories can remain unmarked. Table 4 retains this raw evaluator behavior.
- `evaluate_constraints_py()` normalizes legacy DSL, executes each reference
  constraint, converts result to Boolean and returns False for a caught DSL
  exception or missing result. Benchmark logical evaluation has no loop-style
  UNKNOWN exclusion; all actual reference constraints remain in its denominator.
- Schema validation errors/exceptions do not add a plan to schema_pass. All-pass
  therefore fails when any of schema, CS or logical success is absent.
- Missing/failed plans stay in the evaluator population via `{}` exports. Their
  downstream scores are whatever the existing evaluator produces; the dashboard
  does not impute a blanket zero, exclude them, or repair the metric.
- Empty/zero micro denominators produce blank helper results, displayed
  Unavailable. Missing exact metric rows also stay Unavailable, not zero.
- The unfiltered generated CSV remains authoritative. If filtering is requested
  but required saved per-query evaluator fields are missing, the filtered helper
  adapter returns Unavailable for its five rows rather than running scoring or
  deriving missing results from totals. Optional drill-down fields independently
  remain Unavailable when absent.

No experiment, evaluator, metric definition or original numerical result changes.

## Commonsense micro* footnote

The established reporting caveat appears in
`test_result_analysis/README.md` and in the reporting builder's `readme()` and
`MERGED_TITLES` strings. They explicitly warn that raw Commonsense micro is
inflated for plans the checker could not evaluate. The builder's cs_micro()
comment also says it includes the benchmark exception column.

An exception may mark only one raw exception cell and leave ordinary checks at
zero. The raw metric can then treat those unmarked cells as passed. The additional
exception column also changes C for the evaluated matrix. Table 2 instead uses
standard categories and counts an exception as failing every standard check.

The UI attaches * to Commonsense micro and displays this **documented caveat**.
The generated CSV/helper does not itself contain a literal micro* annotation; the
historical provenance of an external example's asterisk is not separately encoded.
No undocumented explanation or numerical correction is invented.

## Relationship to Tables 1 and 2

“Logical” means reference personal constraints expressed in hard_logic_py. Table 1
benchmark PC scoring uses those same Boolean results and includes named-place
constraints unless a row explicitly excludes them. However:

- Table 1's average query PC pass percentage is a macro mean of query shares.
  Table 4 Logical micro pools all reference constraints, weighting queries by
  their constraint count. They need not be numerically equal.
- For aligned complete benchmark cohorts, Table 1 final-zero-failed-PC count/N
  corresponds to Table 4 Logical macro. Excluding named-place constraints changes
  the constraint population and is not the Table 4 definition.
- Loop-verifier PC pass rates may exclude UNKNOWN states. Table 4 benchmark Boolean
  outcomes do not use that loop denominator.
- Table 2 uses corrected standard CS categories and fails every check for evaluator
  exceptions. Table 4 micro uses raw cells including its exception column. These
  are not substituted for one another, even if current values coincide.
- Table 4 CS macro is the raw zero-failure success criterion. It is not All-pass:
  All-pass additionally requires schema and all logical constraints. Equality in
  a data slice can occur, for example when both are zero, without identical
  definitions. Tests include CS macro =100% with All-pass =0% to enforce this.

## Views, downloads and optional query detail

The main table is authoritative. The selected metric/difficulty bar chart reads
those exact source cells; its normal axis is 0–100%. Out-of-range source values
would be warned about and retained rather than clipped/rescaled. A strategy
profile shows all five source values together. Performance by difficulty shows
observed Easy/Medium/Human plus aggregate All with an explicit aggregate warning.
Every download uses the currently displayed dataframe and selected columns only.

The optional Query-level evaluation view exposes saved per_query.csv fields:

| Displayed field | Source |
|---|---|
| Query UID / Difficulty / Strategy | query_uid / group / bound run strategy |
| CS raw failed cells | cs_failed_raw_final |
| CS raw check cells | cs_total_raw_final |
| PC passed / PC total | pc_passed_final / pc_total |
| Schema passed | schema_final |
| All-pass | all_pass_final |
| CS raw all-checks pass | Existing helper criterion cs_failed_raw_final ==0, only when count is known |
| All PC pass | Existing helper criterion pc_failed_final ==0, only when count is known |

No missing per-query score is reverse-engineered from aggregate metrics. Detailed
per-check successes are not inferred from failure strings. The table does not add
round analysis or treat post-hoc R4 selections as final accepted benchmark plans.

Available strategies/difficulties remain data-driven. Population guards block
incompatible difficulty-specific UID cohorts without a silent intersection or
TRAIN substitution. Run/report binding and provenance/freshness checks remain in
place; source identity alone does not cryptographically establish freshness.
