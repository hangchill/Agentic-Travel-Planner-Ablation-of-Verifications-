from pathlib import Path
import pandas as pd
import streamlit as st
from dashboard import data_loader as data
from dashboard.metrics import pool_saved_cells, eligible_matrix_attempts, matrix_support_limit
from dashboard.components import matrix
from dashboard.components.common import table


def render(ctx):
    st.title('TRAIN set')
    st.caption('Development evidence only — R0–R3 TRAIN. Observed repair-regression relationships are not causal effects.')
    runs = [r for r in ctx['runs'] if r.partition == 'TRAIN' and r.strategy in ('R0', 'R1', 'R2', 'R3')]
    if not runs:
        st.info('TRAIN R0–R3 development evidence: Unavailable.')
        return
    available = sorted({r.strategy for r in runs})
    strategies = st.multiselect('Source strategies', available, default=available, key='train_strategies')
    perspective = st.radio('Matrix perspective', ['candidate', 'accepted_trajectory'], horizontal=True, key='train_perspective')
    frames, coverage = [], []
    for run in runs:
        if run.partition != 'TRAIN' or run.strategy not in strategies:
            continue
        m = data.matrix_table(run)
        if not m.empty:
            frames.append(m[m.perspective == perspective])
        c = data.read_json(Path(run.path) / 'regression_matrix/matrix_coverage.json')
        coverage.append({'strategy': run.strategy, 'repair attempts used': c.get('total_repair_attempts'),
                         'single-target attempts (construction stage)': c.get('single_target_attempts'),
                         'eligible single-target PC attempts (observed destination)': eligible_matrix_attempts(data.read_csv(Path(run.path) / 'regression_matrix/matrix_contributions.csv'), perspective),
                         'missing descriptors': c.get('attempts_missing_descriptors'),
                         'missing target mapping': (c.get('target_mapping') or {}).get('unmapped'),
                         'eligible relationship contributions': c.get('candidate_eligible_contributions' if perspective == 'candidate' else 'accepted_eligible_contributions')})
    table(pd.DataFrame(coverage), 'Persisted matrix construction coverage')
    st.caption('The saved single-target count is a construction-stage count; eligible relationship contributions have a different denominator. No dashboard eligibility rule is substituted. Matrix controls apply to persisted aggregate cells; query/round/phase/outcome filters do not rebuild this matrix.')
    m = pool_saved_cells(frames)
    families = sorted(set(m.source_family) | set(m.destination_family)) if not m.empty else []
    source = st.selectbox('Repaired family', ['All'] + families, key='train_repaired_family')
    destination = st.selectbox('Regressed family', ['All'] + families, key='train_regressed_family')
    maximum = matrix_support_limit([m])
    minimum = st.slider('Minimum matrix support', 0, max(1, maximum), min(5, maximum),
                        disabled=maximum == 0, key='train_matrix_support')
    st.caption('Matrix support filters affect saved matrices only.')
    if not m.empty:
        if source != 'All':
            m = m[m.source_family == source]
        if destination != 'All':
            m = m[m.destination_family == destination]
    matrix.render(m, minimum)
