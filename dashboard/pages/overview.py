from pathlib import Path
import pandas as pd
import streamlit as st
from dashboard import data_loader as data
from dashboard.components.common import cards, table, freshness
from dashboard.metrics import comparison_issues, inventory_row, matched_comparison_rows, availability_summary


def render(ctx):
    st.title('Repair-analysis explorer')
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
    chosen = coverage[(coverage.partition == ctx['run'].partition) & (coverage.strategy == ctx['run'].strategy)]
    if not chosen.empty:
        cards({k: int(chosen[k].sum()) for k in ['queries', 'proposals', 'personal attempts', 'commonsense attempts']})
    st.info('TRAIN = development and matrix construction. TEST = held-out evaluation. Availability above reflects discovered manifests and matching generated artifacts.')
    freshness(ctx['run'])
    st.write('Use the page navigation for TRAIN Interdependencies, TEST Results, Strategy Details, Query Explorer, and Representative Examples.')
    st.subheader('Comparison safeguards')
    selected = st.multiselect('Runs to check for comparison', ctx['runs'], format_func=lambda r: r.label)
    if len(selected) < 2:
        st.caption('Select at least two runs to inspect compatibility.')
        return
    manifests = [data.read_json(Path(r.path) / 'run_manifest.json') for r in selected]
    hashes = []
    for run in selected:
        hashes.append({uid: b['initial'].get('initial_plan_hash')
                       for uid, b in data.checkpoints(run).items()})
    issues = comparison_issues(selected, manifests, hashes)
    for issue in issues:
        st.warning(issue)
    if issues:
        st.info('Controlled comparison disabled. Inspect each run descriptively on TEST Results.')
    else:
        tables = [data.test_table(run, 'per_query') for run in selected]
        if any(q.empty for q in tables):
            st.info('Comparison unavailable: generate TEST reporting tables for every selected run first.')
        else:
            table(matched_comparison_rows(selected, tables), 'Matched TEST common metrics')
