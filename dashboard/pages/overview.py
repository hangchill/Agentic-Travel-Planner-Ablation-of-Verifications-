from pathlib import Path
import pandas as pd
import streamlit as st
from dashboard import data_loader as data
from dashboard.components.common import cards, table, freshness
from dashboard.metrics import inventory_row, availability_summary


def render(ctx):
    st.title('Overview')
    st.caption('Available TRAIN development evidence and TEST benchmark reporting')
    if not ctx['runs']:
        st.info('No valid manifest-backed runs found in experiments/.')
        return
    st.write('Read-only exploration of Personal Constraints (PC), Commonsense Constraints (CS), repair trajectories, and development evidence.')
    rows, statuses = [], {}
    for run in ctx['runs']:
        manifest = data.read_json(Path(run.path) / 'run_manifest.json')
        raw = data.attempts(run)
        reporting = bool(data.test_folder(run))
        diagnostics = bool(data.analysis_folder(run))
        statuses[run] = {'reporting': reporting, 'diagnostics': diagnostics,
                         'queries': len(manifest.get('query_uids', []))}
        rows.append(inventory_row(run, manifest, raw, reporting, diagnostics))
    coverage = pd.DataFrame(rows)
    table(availability_summary(ctx['runs'], statuses), 'Strategy availability')
    table(coverage, 'Available run coverage')
    cards({k: int(coverage[k].sum()) for k in ['queries', 'proposals', 'personal attempts', 'commonsense attempts']})
    st.info('TRAIN = development and matrix construction. TEST = held-out evaluation. Availability above reflects discovered manifests and matching generated artifacts.')
    with st.expander('Run provenance'):
        provenance_run = st.selectbox('Run to inspect', ctx['runs'], format_func=lambda r: r.label, key='overview_provenance_run')
        freshness(provenance_run)
    st.write('Use the page navigation for Overview, Query Explorer, TRAIN set, TEST set, Strategy-Specific, and Examples.')
