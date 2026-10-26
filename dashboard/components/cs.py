"""Table-first benchmark CS reporting with explicitly separate loop diagnostics."""
import pandas as pd
import streamlit as st

from dashboard import data_loader as data, metrics
from dashboard.components import reporting
from dashboard.components.common import table


def _cohorts(ctx, runs):
    return reporting.cohorts(ctx, runs, 'cs', 'table2_cs')


def _population_guard(queries, strategies, difficulties):
    return reporting.population_guard(queries, strategies, difficulties)


def render(ctx):
    st.subheader('Commonsense Constraints — comparison table')
    available = data.available_reporting_runs(ctx['runs'])
    if not available:
        st.info('Common TEST CS reporting is Unavailable for the discovered runs.')
        return
    queries, attempts, summaries = _cohorts(ctx, available)
    difficulty, selected, difficulties = reporting.controls(queries, available, 'cs')
    if not selected:
        st.info('Select at least one strategy.')
        return
    shown = difficulties + ['All'] if difficulty == 'All difficulties' else [difficulty]
    st.caption('Benchmark CS check categories from Table 2 and saved per-query counts. Med means Medium. Query-change rows are counts. Evaluator exceptions count as failing every standard check. This table is independent of the sidebar strategy/difficulty; sidebar proposal filters select cohorts, whose complete observed trajectories remain available below.')
    if _population_guard(queries, selected, shown):
        table(metrics.cs_report_pivot(summaries, queries, selected, shown), 'CS comparison table')
    reporting.warnings([available[s] for s in selected])
    with st.expander('CS metric sources and definitions'):
        table(metrics.cs_reporting_sources(), 'CS metric sources')
        st.write({s: str(data.test_folder(available[s])) for s in selected})
        st.caption('The >85% criterion is strict and reuses the established threshold count/share. If standard check counts vary, the requested threshold comparison is Unavailable rather than relabelled.')

    st.subheader('Final CS failures by constraint family')
    st.caption('Exact saved CS failure-check labels; no inferred schedule/travel grouping. No full CS family helper exists upstream. Failure rate uses attributable nonexception plans as its denominator. Exception or missing-label cases are excluded from attribution, never counted as passes; the main table still counts evaluator exceptions as failing every check.')
    failure_difficulty = st.selectbox('Failure difficulty', ['All'] + difficulties,
                                    index=(['All'] + difficulties).index(difficulty) if difficulty in difficulties else 0,
                                    key='cs_failure_difficulty')
    frames, coverage = [], []
    for strategy in selected:
        q = metrics.difficulty_queries(queries[strategy], failure_difficulty)
        frame, evidence = metrics.cs_failure_families(q, strategy, failure_difficulty)
        if not frame.empty:
            frames.append(frame)
        coverage.append(evidence)
    failures = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not failures.empty:
        families = sorted(failures['CS family'].unique())
        selected_families = st.multiselect('CS families', families, default=families, key='cs_failure_families')
        failures = failures[failures['CS family'].isin(selected_families)]
    table(failures, 'Final CS failures by constraint family')
    with st.expander('CS failure attribution coverage'):
        table(pd.DataFrame(coverage), 'CS failure attribution coverage')
    st.markdown('**Top remaining CS failures**')
    # Individual per-strategy summaries do not rank incompatible cohort counts.
    top = failures.groupby('Strategy', sort=False).head(3) if not failures.empty else failures
    table(top, 'Top remaining CS failures')

    st.subheader('CS outcomes by repair round')
    st.caption('Loop-verifier diagnostics. Histories log error messages, not a CS check denominator or check-level pass/fail vectors. Requested check pass/fix metrics therefore stay Unavailable. The additional message rows describe accepted error-message counts and set changes, not benchmark checks. Rejected candidates never advance accepted state.')
    controls = st.columns(2)
    with controls[0]:
        strategy = st.selectbox('Round strategy', selected, key='cs_round_strategy')
    with controls[1]:
        round_difficulty = st.selectbox('Round difficulty', ['All'] + difficulties, key='cs_round_difficulty')
    q = metrics.difficulty_queries(queries[strategy], round_difficulty)
    detail = metrics.cs_round_table(q, attempts[strategy], data.checkpoints(available[strategy]))
    table(detail, 'CS outcomes by repair round')

    st.subheader('Round-wise strategy comparison')
    st.caption('Loop-verifier diagnostics. Numerical cells are authoritative; the supplementary chart uses the same Initial / observed round / Final cells. Still active means a later proposal is observed, not proof of scheduler status. Initial/Final event metrics are Unavailable.')
    controls = st.columns(2)
    with controls[0]:
        metric = st.selectbox('Metric', list(metrics.CS_ROUND_COMPARISONS),
                              index=list(metrics.CS_ROUND_COMPARISONS).index('Mean CS error messages'),
                              key='cs_round_compare_metric')
    with controls[1]:
        compare_difficulty = st.selectbox('Comparison difficulty', ['All'] + difficulties,
                                        key='cs_round_compare_difficulty')
    if _population_guard(queries, selected, [compare_difficulty]):
        tables = {s: metrics.cs_round_table(metrics.difficulty_queries(queries[s], compare_difficulty),
                                            attempts[s], data.checkpoints(available[s])) for s in selected}
        comparison, points = metrics.cs_round_comparison(tables, metric)
        table(comparison, 'CS round strategy comparison')
        if not points.empty and points.Value.notna().any():
            st.plotly_chart(reporting.round_chart(points, metric, metrics.CS_ROUND_COMPARISONS[metric], endpoints=True),
                            width='stretch')
        else:
            st.info('The selected check-level metric is Unavailable from loop error-message logs. Select an explicitly named message diagnostic or observed activity.')
