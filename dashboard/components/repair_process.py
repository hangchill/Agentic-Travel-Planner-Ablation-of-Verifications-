"""Table 3 reporting plus separately labelled persisted process diagnostics."""
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import data_loader as data, metrics
from dashboard.components import reporting
from dashboard.components.common import table


def _cohorts(ctx, runs):
    return reporting.cohorts(ctx, runs, 'process', 'table3_repair_process')


def render(ctx):
    st.subheader('Repair Process / Efficiency — comparison table')
    available = data.available_reporting_runs(ctx['runs'])
    if not available:
        st.info('Common TEST process reporting is Unavailable for the discovered runs.')
        return
    queries, attempts, summaries = _cohorts(ctx, available)
    difficulty, selected, difficulties = reporting.controls(queries, available, 'process')
    if not selected:
        st.info('Select at least one strategy.')
        return
    shown = difficulties + ['All'] if difficulty == 'All difficulties' else [difficulty]
    if reporting.population_guard(queries, selected, shown):
        table(metrics.process_report_pivot(summaries, queries, selected, shown), 'Table 3 process comparison')
    st.caption('Source: existing table3_repair_process.csv / table_process(). Avg tokens/query excludes queries with any missing token delta. “Avg tokens, all queries (lower bound)” averages only recorded usage; missing round counts add zero to that lower bound, not proof of zero cost or a complete estimate of consumption.')
    coverage = [metrics.process_cost_detail(queries, summaries, selected, d) for d in shown]
    low = [f'{d} {row["Strategy"]}' for d, frame in zip(shown, coverage)
           for row in frame.to_dict('records') if pd.notna(row['Token completeness (%)']) and row['Token completeness (%)'] < 80]
    if low:
        st.warning('Low token completeness (below 80% of queries): ' + ', '.join(low) + '. Complete-data means cover a subset; lower bounds omit unrecorded usage.')
    st.caption('Δ PC passed: positive improves, negative deteriorates. Δ CS errors: negative improves, positive deteriorates. Each query’s changed-round average is computed first, then averaged over queries with a changed round. Candidate verification is compared with the preceding accepted state, including rejected R2 candidates. UNKNOWN→True contributes to the PC True-count delta.')
    reporting.warnings([available[s] for s in selected])
    with st.expander('Process metric sources and definitions'):
        table(metrics.process_reporting_sources(), 'Process metric sources')
        st.write({s: str(data.test_folder(available[s])) for s in selected})

    st.subheader('Repair round outcomes')
    cols = st.columns(2)
    with cols[0]:
        strategy = st.selectbox('Outcome strategy', selected, key='process_outcome_strategy')
    with cols[1]:
        outcome_difficulty = st.selectbox('Outcome difficulty', ['All'] + difficulties, key='process_outcome_difficulty')
    q = metrics.difficulty_queries(queries[strategy], outcome_difficulty)
    events = metrics.process_round_events(q, attempts[strategy], data.checkpoints(available[strategy]))
    outcomes = metrics.process_outcomes(q, events)
    table(outcomes, 'Repair round outcomes')
    st.caption('Plan changed / unchanged cache / unchanged new request form the existing exhaustive, exclusive split. Model-call failure is a separate overlapping flag and is not added to that partition. Missing failure-counter coverage makes its whole-cohort count/rate Unavailable.')
    st.caption('Cache means an exact repeated request (messages and call options) reused an earlier reply without calling the underlying model for that matching request. A cache-hit round can still contain other model/verifier calls. No round-level cost saving is inferred. “Unchanged: new request” is the reporting helper’s residual unchanged_other category, including absent cache markers; it does not itself prove a new request or a model dispatch.')
    if outcomes['% of rounds'].notna().any():
        st.plotly_chart(px.bar(outcomes, x='Outcome', y='% of rounds', title='Round outcomes — failure flag may overlap'), width='stretch')

    st.subheader('Cost and runtime')
    cost_difficulty = st.selectbox('Cost difficulty', ['All'] + difficulties, key='process_cost_difficulty')
    if reporting.population_guard(queries, selected, [cost_difficulty]):
        costs = metrics.process_cost_detail(queries, summaries, selected, cost_difficulty)
        table(costs, 'Cost and runtime')
        for field, title in [('Avg tokens/query (complete)', 'Tokens/query — complete-token subset'),
                             ('Avg repair time/query (s)', 'Repair time/query (seconds)')]:
            if not costs.empty and costs[field].notna().any():
                st.plotly_chart(px.bar(costs, x='Strategy', y=field, title=title), width='stretch')

    st.subheader('Repair process by round')
    cols = st.columns(2)
    with cols[0]:
        round_strategy = st.selectbox('Round strategy', selected, key='process_round_strategy')
    with cols[1]:
        round_difficulty = st.selectbox('Round difficulty', ['All'] + difficulties, key='process_round_difficulty')
    q = metrics.difficulty_queries(queries[round_strategy], round_difficulty)
    observed = metrics.process_round_events(q, attempts[round_strategy], data.checkpoints(available[round_strategy]))
    table(metrics.process_round_table(observed), 'Repair process by round')
    st.caption('Loop/process diagnostics. Reaching/active means a persisted proposal in that round, not inferred scheduler state. Tokens average known deltas only; missing counts and evidence N are shown. Per-round changed effects average changed proposals observed at that step. Missing translated verification leaves classification/effects Unavailable. Model-call failure flags use failed_model_calls >0, including any logged transport retry/verification failures; they are not exclusive repair outcomes.')

    st.subheader('Round-wise strategy comparison')
    cols = st.columns(2)
    with cols[0]:
        metric = st.selectbox('Metric', list(metrics.PROCESS_ROUND_COMPARISONS), key='process_round_compare_metric')
    with cols[1]:
        compare_difficulty = st.selectbox('Comparison difficulty', ['All'] + difficulties, key='process_round_compare_difficulty')
    if reporting.population_guard(queries, selected, [compare_difficulty]):
        tables = {}
        for s in selected:
            q = metrics.difficulty_queries(queries[s], compare_difficulty)
            records = metrics.process_round_events(q, attempts[s], data.checkpoints(available[s]))
            tables[s] = metrics.process_round_table(records)
        comparison, points = metrics.process_round_comparison(tables, metric)
        table(comparison, 'Process round strategy comparison')
        if not points.empty:
            st.plotly_chart(reporting.round_chart(points, metric, metrics.PROCESS_ROUND_COMPARISONS[metric]), width='stretch')
        else:
            st.info('Selected round metric is Unavailable from the persisted evidence.')

    st.subheader('Additional process diagnostics')
    extra_difficulty = st.selectbox('Diagnostics difficulty', ['All'] + difficulties, key='process_extra_difficulty')
    extras = []
    for s in selected:
        q = metrics.difficulty_queries(queries[s], extra_difficulty)
        if q.empty:
            continue
        diagnostic = metrics.process_additional_diagnostics(q, attempts[s])
        diagnostic.insert(0, 'Strategy', s)
        extras.append(diagnostic)
    table(pd.concat(extras, ignore_index=True) if extras else pd.DataFrame(), 'Additional process diagnostics')
    st.caption('Repair-only counters require complete proposal coverage; zero is used only for proven zero-round queries. Budget exhaustion uses the exact logged stop reason, even for early stops. Changed-slot events can repeat across rounds. Accepted PC fixes/regressions and CS message changes remain in the PC/CS tabs rather than being relabelled as generic violation metrics.')
