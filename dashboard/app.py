"""Launch from repository root: streamlit run dashboard/app.py."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from dashboard import data_loader as data
from dashboard.metrics import attempt_frame, filter_attempts, filter_queries, observed_rounds, matrix_support_limit
from chinatravel.evaluation.constraint_families import CONSTRAINT_FAMILIES
from dashboard.pages import (overview, train_interdependencies, test_results,
                             strategy_details, query_explorer, representative_examples)


def main():
    st.set_page_config(page_title='Repair-analysis explorer', page_icon='📊', layout='wide')
    pages = [st.Page(lambda module=module: module.render(ctx), title=title, url_path=module.__name__.rsplit('.', 1)[-1], default=i == 0)
             for i, (module, title) in enumerate([
                 (overview, 'Overview'), (train_interdependencies, 'TRAIN Interdependencies'),
                 (test_results, 'TEST Results'), (strategy_details, 'Strategy Details'),
                 (query_explorer, 'Query Explorer'), (representative_examples, 'Representative Examples')])]
    navigation = st.navigation(pages)
    with st.sidebar:
        if st.button('Refresh local data', key='refresh_data'):
            st.cache_data.clear()
            st.rerun()
    runs = data.discover_runs()
    if not runs:
        st.error('No valid manifest-backed runs found in experiments/.')
        return
    with st.sidebar:
        st.title('Repair-analysis explorer')
        partition = st.selectbox('Dataset', ['TRAIN', 'TEST'], key='dataset')
        strategy = st.selectbox('Strategy', ['R0', 'R1', 'R2', 'R3', 'R4'], key='strategy')
        matches = [r for r in runs if r.partition == partition and r.strategy == strategy]
        if not matches:
            st.warning(f'{strategy} {partition}: run unavailable. No partition substitution is performed.')
            st.stop()
        run = matches[0] if len(matches) == 1 else st.selectbox('Run', matches, format_func=lambda r: r.run_id)
        raw = data.attempts(run)
        a_full = attempt_frame(raw, data.analysis_table(run, 'attempt_level'))
        histories = []
        if a_full.empty:
            histories = [cp.get('repair_history', []) for bundle in data.checkpoints(run).values()
                         for cp in bundle['checkpoints']]
        rounds = ['All'] + [str(step) for step in observed_rounds(a_full, histories)]
        support_frames = [data.matrix_table(r) for r in runs if r.partition == 'TRAIN']
        if run.partition != 'TRAIN':
            support_frames.append(data.matrix_table(run))
        maximum_support = matrix_support_limit(support_frames, a_full.get('guidance_support', []))
        families = sorted(set(CONSTRAINT_FAMILIES) | {family for row in a_full.get('target_families', []) for family in row})
        filters = {'phase': st.selectbox('Repair phase', ['All', 'Personal', 'Commonsense']),
                   'round': st.selectbox('Round', rounds),
                   'uid': st.text_input('Query UID search', placeholder='UID or substring'),
                   'family': st.selectbox('Constraint family', ['All', 'commonsense_repair'] + [f for f in families if f != 'commonsense_repair']),
                   'outcome': st.selectbox('Outcome', ['All', 'Fixed', 'Regression', 'Unchanged', 'Rejected', 'Accepted']),
                   'minimum': st.slider('Minimum matrix support', 0, max(1, maximum_support),
                                        min(5, maximum_support), disabled=maximum_support == 0)}
        difficulty_enabled = partition == 'TEST' and data.test_folder(run) is not None
        difficulty = st.selectbox('TEST difficulty group', ['All', 'easy', 'medium', 'human'], disabled=not difficulty_enabled)
        if not difficulty_enabled:
            difficulty = 'All'
        st.caption('Fixed/Regression refer to candidate PC transitions. Unchanged uses the explicit no-progress marker. Matrix support filters affect saved matrices only.')
    a = filter_attempts(a_full, filters)
    test_q = data.test_table(run, 'per_query')
    test_q = filter_queries(test_q, a, filters)
    if difficulty != 'All':
        if not test_q.empty:
            test_q = test_q[test_q.group == difficulty]
        a = a[a.query_uid.isin(test_q.query_uid)] if not test_q.empty else a.iloc[:0]
    q = data.analysis_table(run, 'query_level')
    if q.empty:
        ids = data.read_json(Path(run.path) / 'run_manifest.json').get('query_uids', [])
        q = pd.DataFrame({'query_uid': ids})
    q = filter_queries(q, a, filters)
    if partition == 'TEST' and difficulty != 'All':
        q = q[q.query_uid.isin(test_q.query_uid)]
    ctx = {'runs': runs, 'run': run, 'filters': filters, 'a': a, 'a_full': a_full,
           'q': q, 'test_q': test_q}
    navigation.run()


if __name__ == '__main__':
    main()
