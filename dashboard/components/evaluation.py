"""Final ChinaTravel benchmark reporting; no round-level evaluation or scoring."""
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import data_loader as data, metrics
from dashboard.components import reporting
from dashboard.components.common import table


def _cohorts(ctx, runs):
    return reporting.cohorts(ctx, runs, 'benchmark', 'table4_eval_exp',
                             filtered_summary=metrics.evaluation_summary)


def percentage_bar(frame, x, title):
    figure = px.bar(frame, x=x, y='Score (%)', title=title, labels={'Score (%)': 'Score (%)'})
    known = frame['Score (%)'].dropna()
    if known.between(0, 100).all():
        figure.update_yaxes(range=[0, 100], ticksuffix='%')
    else:
        st.warning('Source percentage values fall outside 0–100; retaining them without clipping or rescaling.')
    return figure


def render(ctx):
    st.subheader('ChinaTravel Evaluation — comparison table')
    available = data.available_reporting_runs(ctx['runs'])
    if not available:
        st.info('Final TEST evaluation reporting is Unavailable for the discovered runs.')
        return
    queries, _, summaries = _cohorts(ctx, available)
    difficulty, selected, difficulties = reporting.controls(queries, available, 'evaluation')
    if not selected:
        st.info('Select at least one strategy.')
        return
    shown = difficulties + ['All'] if difficulty == 'All difficulties' else [difficulty]
    if reporting.population_guard(queries, selected, shown):
        table(metrics.evaluation_pivot(summaries, queries, selected, shown), 'Table 4 ChinaTravel evaluation', precision=2)
    st.caption('Final benchmark percentages, already on the 0–100 scale. Source: table4_eval_exp.csv; filtered cohorts reuse the unchanged table_eval_exp helper over saved benchmark rows. No loop-trajectory scores are substituted.')
    st.caption(metrics.EVALUATION_MICRO_FOOTNOTE)
    reporting.warnings([available[s] for s in selected])
    with st.expander('How are these metrics defined?'):
        table(metrics.evaluation_definitions(), 'ChinaTravel metric definitions')
        st.caption('Logical evaluates the same reference hard_logic_py personal constraints as Table 1 benchmark scoring. Its micro score pools constraints rather than averaging query pass shares. All-pass additionally requires schema and CS success. Table 2 uses corrected standard-check exception handling; Table 4 preserves raw evaluator behavior.')
        st.write({s: str(data.test_folder(available[s])) for s in selected})

    st.subheader('Metric comparison')
    cols = st.columns(2)
    with cols[0]:
        metric = st.selectbox('Metric', metrics.EVALUATION_METRICS, key='evaluation_metric')
    with cols[1]:
        compare_difficulty = st.selectbox('Comparison difficulty', ['All'] + difficulties, key='evaluation_compare_difficulty')
    if reporting.population_guard(queries, selected, [compare_difficulty]):
        scores = metrics.evaluation_scores(summaries, queries, selected, compare_difficulty, metric)
        if not scores.empty and scores['Score (%)'].notna().any():
            st.plotly_chart(percentage_bar(scores, 'Strategy', metric), width='stretch')
        else:
            st.info('Selected benchmark metric is Unavailable from the generated reporting table.')

    st.subheader('Strategy evaluation profile')
    cols = st.columns(2)
    with cols[0]:
        strategy = st.selectbox('Profile strategy', selected, key='evaluation_profile_strategy')
    with cols[1]:
        profile_difficulty = st.selectbox('Profile difficulty', ['All'] + difficulties, key='evaluation_profile_difficulty')
    table(metrics.evaluation_strategy_profile(summaries, queries, strategy, profile_difficulty),
          'Strategy evaluation profile', precision=2)

    st.subheader('Performance by difficulty')
    cols = st.columns(2)
    with cols[0]:
        metric = st.selectbox('Metric', metrics.EVALUATION_METRICS, key='evaluation_difficulty_metric')
    with cols[1]:
        strategy = st.selectbox('Strategy', selected, key='evaluation_difficulty_strategy')
    profile = metrics.evaluation_difficulty_profile(summaries, queries, strategy, metric)
    table(profile, 'Performance by difficulty', precision=2)
    st.caption('All is the aggregate query cohort, not an additional difficulty category or independent sample.')
    if not profile.empty and profile['Score (%)'].notna().any():
        st.plotly_chart(percentage_bar(profile, 'Difficulty', metric), width='stretch')

    with st.expander('Query-level evaluation'):
        detail = pd.concat([metrics.evaluation_query_detail(queries[s], s,
                            difficulty if difficulty != 'All difficulties' else 'All') for s in selected], ignore_index=True)
        table(detail, 'Query-level evaluation')
        st.caption('Saved raw CS cell counts, PC counts, schema result and All-pass only. Zero-failure flags use the original helper criteria. Missing fields stay Unavailable; no per-query results are inferred from aggregate percentages.')
