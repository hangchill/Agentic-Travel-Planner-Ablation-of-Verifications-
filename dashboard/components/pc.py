"""Table-first, cross-strategy TEST PC reporting and accepted-loop diagnostics."""
import pandas as pd
import streamlit as st

from dashboard import data_loader as data
from dashboard import metrics as metrics
from dashboard.components.common import table
from dashboard.components import reporting


def _cohorts(ctx, runs):
    return reporting.cohorts(ctx, runs, 'pc', 'table1_pc')


def _warnings(runs):
    reporting.warnings(runs)


def render(ctx):
    st.subheader('Personal Constraints — comparison table')
    available = data.available_pc_runs(ctx['runs'])
    if not available:
        st.info('Common TEST PC reporting is Unavailable for the discovered runs.')
        return
    queries, attempts, summaries = _cohorts(ctx, available)
    difficulty, selected, difficulties = reporting.controls(queries, available, 'pc')
    if not selected:
        st.info('Select at least one strategy.')
        return
    shown_difficulties = difficulties + ['All'] if difficulty == 'All difficulties' else [difficulty]
    pivot = metrics.pc_report_pivot(summaries, queries, selected, shown_difficulties)
    st.caption('Benchmark PC values from the team TEST reporting tables. Columns are difficulty × strategy; Med means Medium. Query-change rows are counts. Missing metrics display Unavailable. The controls compare TEST reporting runs using page-local difficulty and strategy selections. Round views retain that cohort’s complete observed trajectories.')
    table(pivot, 'PC comparison table')
    st.caption('“Queries: all PC pass at start” is Unavailable: the existing generated row counts only initially perfect queries whose PC result also stayed unchanged. It is not the broader requested metric.')
    _warnings([available[s] for s in selected])
    if len({frozenset(queries[s].query_uid) for s in selected}) > 1:
        st.warning('Selected runs have different filtered query populations; compare them descriptively.')
    with st.expander('PC metric sources and definitions'):
        table(metrics.pc_reporting_sources(), 'PC metric sources')
        st.write({s: str(data.test_folder(available[s])) for s in selected})

    st.subheader('Final PC failures by constraint family')
    st.caption('PC family here uses the reporting builder’s existing PC-kind labels, not the matrix’s structural family taxonomy. Failure rate = failed constraints / total constraints of that kind. Difficulty slices reuse the builder’s table_pc_kinds helper.')
    failure_difficulty = st.selectbox('Failure difficulty', ['All'] + difficulties,
                                    index=(['All'] + difficulties).index(difficulty) if difficulty in difficulties else 0,
                                    key='pc_failure_difficulty')
    failure_frames = []
    for strategy in selected:
        run = available[strategy]
        full = data.test_table(run, 'per_query')
        q = metrics.pc_difficulty_queries(queries[strategy], failure_difficulty)
        if q.empty:
            continue
        if failure_difficulty == 'All' and set(q.query_uid) == set(full.query_uid):
            kinds = data.test_table(run, 'table1b_pc_failure_by_kind')
        else:
            refs = data.pc_references(run)
            kinds = metrics.team_table(q, 'pc_kinds', refs) if set(q.query_uid) <= set(refs) else pd.DataFrame()
        f = metrics.pc_failure_table(kinds, strategy, failure_difficulty)
        if not f.empty:
            failure_frames.append(f)
    failures = pd.concat(failure_frames, ignore_index=True) if failure_frames else pd.DataFrame()
    if not failures.empty:
        families = st.multiselect('PC families', sorted(failures['PC family'].unique()),
                                  default=sorted(failures['PC family'].unique()), key='pc_failure_families')
        failures = failures[failures['PC family'].isin(families)]
    table(failures, 'Final PC failures by constraint family')
    st.markdown('**Top remaining PC failures**')
    top = (failures[failures['Failure count'] > 0].sort_values(['Failure count', 'Failure rate (%)'], ascending=False).head(5)
           if not failures.empty else failures)
    table(top, 'Top remaining PC failures')

    st.subheader('PC outcomes by repair round')
    st.caption('Loop-verifier accepted-state diagnostics, separate from the benchmark comparison above. Rates are True/(True+False), UNKNOWN excluded. Round means use observed proposals only, with no forward fill. Still active means a later proposal is observed; percentages use the selected reporting-cohort size. Independent trials are not combined into one trajectory.')
    controls = st.columns(2)
    with controls[0]:
        round_strategy = st.selectbox('Round strategy', selected, key='pc_round_strategy')
    with controls[1]:
        round_difficulty = st.selectbox('Round difficulty', ['All'] + difficulties, key='pc_round_difficulty')
    q = metrics.pc_difficulty_queries(queries[round_strategy], round_difficulty)
    detail = metrics.pc_round_table(q, attempts[round_strategy], data.checkpoints(available[round_strategy]))
    table(detail, 'PC outcomes by repair round')

    st.subheader('Round-wise strategy comparison')
    controls = st.columns(2)
    with controls[0]:
        metric = st.selectbox('Metric', list(metrics.PC_ROUND_COMPARISONS), key='pc_round_compare_metric')
    with controls[1]:
        compare_difficulty = st.selectbox('Comparison difficulty', ['All'] + difficulties, key='pc_round_compare_difficulty')
    tables = {s: metrics.pc_round_table(metrics.pc_difficulty_queries(queries[s], compare_difficulty),
                                       attempts[s], data.checkpoints(available[s])) for s in selected}
    comparison, points = metrics.pc_round_comparison(tables, metric)
    table(comparison, 'PC round strategy comparison')
    st.caption('New-violation rate uses the existing accepted_new_violation_rate: accepted new violations / PCs passing before, averaged over defined proposals. It differs from the percentage of rounds introducing any violation. Event and activity rows have no invented Final values.')
    if not points.empty:
        st.plotly_chart(round_chart(points, metric), width='stretch')
    st.caption('Round source: persisted repair_history/final_verification and attempts.jsonl, with generated attempt_level.csv metrics when provenance matches; otherwise the existing shared compute_attempt_metrics helper. Initial/Final state rows use saved loop checkpoints. No benchmark scoring is run.')


def round_chart(points, metric):
    """Supplementary chart uses the comparison table's own long-form cells."""
    return reporting.round_chart(points, metric, metrics.PC_ROUND_COMPARISONS[metric])
