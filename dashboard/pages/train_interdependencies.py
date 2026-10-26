from pathlib import Path
import pandas as pd
import streamlit as st
from dashboard import data_loader as data
from dashboard.metrics import pool_saved_cells, eligible_matrix_attempts
from dashboard.components import matrix
from dashboard.components.common import table


def render(ctx):
    st.title('TRAIN interdependencies')
    st.caption('Development evidence only — R0–R3 TRAIN. Observed repair-regression relationships are not causal effects.')
    if ctx['run'].partition != 'TRAIN' or ctx['run'].strategy == 'R4':
        st.warning('This page requires TRAIN R0–R3. Change Dataset/Strategy in the sidebar.')
        return
    strategies = st.multiselect('Source strategies', ['R0', 'R1', 'R2', 'R3'], default=[ctx['run'].strategy])
    perspective = st.radio('Matrix perspective', ['candidate', 'accepted_trajectory'], horizontal=True)
    frames, coverage = [], []
    for run in ctx['runs']:
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
    if ctx['filters']['family'] != 'All' and not m.empty:
        family = ctx['filters']['family']
        m = m[(m.source_family == family) | (m.destination_family == family)]
    matrix.render(m, ctx['filters']['minimum'])
