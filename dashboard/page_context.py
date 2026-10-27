"""Page-scoped run selection. No analytical state is shared between pages."""
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard import data_loader as data, metrics


def unfiltered(runs, partition):
    return {'runs': [r for r in runs if r.partition == partition], 'filters': {}}


def select_run(runs, partition, prefix):
    available = [r for r in runs if r.partition == partition]
    if not available:
        st.info(f'{partition} runs: Unavailable. No partition substitution is performed.')
        return None
    strategies = sorted({r.strategy for r in available})
    strategy = st.selectbox('Strategy', strategies, key=f'{prefix}_strategy')
    matches = [r for r in available if r.strategy == strategy]
    if len(matches) == 1:
        return matches[0]
    return st.selectbox('Run', matches, format_func=lambda r: r.run_id, key=f'{prefix}_run')


def local_partition(runs, prefix):
    # Keep TEST first even when unavailable; never silently fall back to TRAIN.
    return st.selectbox('Partition', ['TEST', 'TRAIN'], key=f'{prefix}_partition')


def diagnostics(runs, partition, prefix):
    run = select_run(runs, partition, prefix)
    if run is None:
        return None
    st.caption(f'{partition} · {run.label}')
    full = metrics.attempt_frame(data.attempts(run), data.analysis_table(run, 'attempt_level'))
    q = data.analysis_table(run, 'query_level')
    if q.empty:
        q = pd.DataFrame({'query_uid': data.read_json(Path(run.path) / 'run_manifest.json').get('query_uids', [])})
    histories = [cp.get('repair_history', []) for bundle in data.checkpoints(run).values()
                 for cp in bundle['checkpoints']] if full.empty else []
    families = sorted({f for fs in full.get('target_families', []) for f in fs})
    with st.expander('Filter diagnostic evidence'):
        reporting = data.test_table(run, 'per_query')
        groups = metrics.reporting_difficulties({run.strategy: reporting})
        difficulty = st.selectbox('Difficulty', ['All'] + groups, key=f'{prefix}_difficulty') if groups else 'All'
        filters = {
            'phase': st.selectbox('Repair phase', ['All', 'Personal', 'Commonsense'], key=f'{prefix}_phase'),
            'round': st.selectbox('Round', ['All'] + [str(x) for x in metrics.observed_rounds(full, histories)], key=f'{prefix}_round'),
            'uid': st.text_input('Query UID search', key=f'{prefix}_uid_search'),
            'family': st.selectbox('Constraint family', ['All'] + families, key=f'{prefix}_family'),
            'outcome': st.selectbox('Outcome', ['All', 'Fixed', 'Regression', 'Unchanged', 'Rejected', 'Accepted'], key=f'{prefix}_outcome')}
        st.caption('Fixed/Regression refer to candidate PC transitions. Unchanged uses the explicit no-progress marker.')
    a = metrics.filter_attempts(full, filters)
    q = metrics.filter_queries(q, a, filters)
    if difficulty != 'All':
        group = difficulty.lower()
        allowed = reporting.loc[reporting.group.str.lower() == group, 'query_uid']
        q = q[q.query_uid.isin(allowed)]
        a = a[a.query_uid.isin(allowed)]
    return {'run': run, 'a': a, 'q': q, 'filters': filters}
