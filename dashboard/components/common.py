"""Consistent metric cards, tables, and CSV exports."""
import pandas as pd
import streamlit as st
from dashboard.utils import present


def cards(values):
    for col, (label, value) in zip(st.columns(min(len(values), 4)), list(values.items())[:4]):
        with col:
            value = present(value)
            if isinstance(value, float):
                value = f'{value:,.3g}'
            st.metric(label, value)


def table(frame, label, columns=None, precision=3):
    if frame is None or frame.empty:
        st.info(f'{label}: Unavailable — no matching persisted evidence.')
        return
    shown = frame.reindex(columns=[c for c in columns if c in frame]) if columns else frame.copy()
    # Nested plans/metadata are shown only in the trajectory detail panels.
    for c in shown:
        if shown[c].map(lambda v: isinstance(v, (dict, list))).any():
            shown[c] = shown[c].map(str)
    st.dataframe(shown.style.format(precision=precision, na_rep='Unavailable'), hide_index=True, width='stretch')
    st.download_button(f'Download {label} CSV', shown.to_csv(index=False).encode(),
                       file_name=f'{label.replace(" ", "_")}.csv', mime='text/csv',
                       key=f'download_{label}')


def metric_rows(frame, labels):
    if frame.empty:
        return
    values = {label: frame.loc[frame.metric == metric, 'All'].iloc[0]
              for label, metric in labels.items() if (frame.metric == metric).any()}
    if values:
        cards(values)


def summary_chart(frame, terms, title):
    import plotly.express as px
    if frame.empty:
        return
    selected = frame[frame.metric.isin(terms)].copy()
    selected['All'] = pd.to_numeric(selected.All, errors='coerce')
    selected = selected.dropna(subset=['All'])
    if len(selected):
        st.plotly_chart(px.bar(selected, x='metric', y='All', title=title,
                               color_discrete_sequence=['#307b88']), width='stretch')


def freshness(run):
    from dashboard import data_loader as data
    from pathlib import Path
    st.subheader('Provenance and freshness')
    evidence = data.provenance_rows(run)
    table(evidence, 'Selected run provenance')
    if evidence['source freshness'].eq('Source freshness cannot be cryptographically verified.').any():
        st.warning('Source freshness cannot be cryptographically verified.')
    if evidence['source freshness'].str.contains('do not match', regex=False).any():
        st.warning('Recorded source checksums do not match. Regenerate analysis before interpreting these diagnostics.')
    st.caption('Run-ID/population matching establishes identity, not freshness. Generation timestamps are Unavailable when upstream outputs do not record them.')
    with st.expander('Selected manifest query population'):
        manifest = data.read_json(Path(run.path) / 'run_manifest.json')
        table(pd.DataFrame({'query_uid': manifest.get('query_uids', [])}), 'Selected manifest population')
