"""Shared presentation/filtering for benchmark and repair-process reporting."""
from pathlib import Path

import plotly.express as px
import streamlit as st

from dashboard import data_loader as data, metrics


def cohorts(ctx, runs, kind, filename, filtered_summary=None):
    queries, attempts, summaries = {}, {}, {}
    for strategy, run in runs.items():
        full = data.test_table(run, 'per_query')
        all_attempts = metrics.attempt_frame(data.attempts(run), data.analysis_table(run, 'attempt_level'))
        matching = metrics.filter_attempts(all_attempts, ctx['filters'])
        q = metrics.filter_queries(full, matching, ctx['filters'])
        queries[strategy] = q
        attempts[strategy] = all_attempts[all_attempts.query_uid.isin(q.query_uid)] if not all_attempts.empty else all_attempts
        summaries[strategy] = (data.test_table(run, filename) if set(q.query_uid) == set(full.query_uid)
                               else (filtered_summary(q) if filtered_summary else metrics.team_table(q, kind)))
    return queries, attempts, summaries


def controls(queries, available, prefix):
    difficulties = metrics.reporting_difficulties(queries)
    cols = st.columns(2)
    with cols[0]:
        difficulty = st.selectbox('Difficulty', ['All difficulties'] + difficulties, key=f'{prefix}_report_difficulty')
    with cols[1]:
        selected = st.multiselect('Strategies', list(available), default=list(available), key=f'{prefix}_report_strategies')
    return difficulty, selected, difficulties


def warnings(runs):
    if len(runs) < 2:
        return
    manifests = [data.read_json(Path(r.path) / 'run_manifest.json') for r in runs]
    hashes = [{uid: b['initial'].get('initial_plan_hash') for uid, b in data.checkpoints(run).items()}
              for run in runs]
    issues = metrics.comparison_issues(runs, manifests, hashes)
    if issues:
        st.warning('Descriptive comparison only: these runs do not meet all controlled-comparison checks.')
        with st.expander('Comparison compatibility details'):
            for issue in issues:
                st.write(issue)


def round_chart(points, metric, field, endpoints=False):
    x = 'Stage' if endpoints else 'Round'
    figure = px.line(points, x=x, y='Value', color='Strategy', markers=True,
                     labels={'Value': field}, title=metric)
    if endpoints:
        stages = list(dict.fromkeys(points.Stage))
        figure.update_xaxes(type='category', categoryorder='array', categoryarray=stages)
    else:
        steps = sorted(points.Round.unique())
        figure.update_xaxes(tickmode='array', tickvals=steps)
        for trace in figure.data:
            group = points[points.Strategy == trace.name].set_index('Round').reindex(steps)
            trace.x, trace.y = steps, group.Value.to_list()
    figure.update_traces(connectgaps=False)
    return figure


def population_guard(queries, strategies, difficulties):
    incompatible = metrics.incompatible_populations(queries, strategies, difficulties)
    if incompatible:
        st.warning('Comparison unavailable: selected runs have different query populations for ' +
                   ', '.join(incompatible) + '. Select matching runs or inspect one strategy.')
    return not incompatible
