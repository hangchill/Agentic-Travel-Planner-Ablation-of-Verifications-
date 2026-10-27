"""Canonical examples with fixed source bindings and evidence-based defaults."""
import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard import data_loader as data
from dashboard.example_selection import EMPTY, TITLES, find_examples, markdown


def recorded_hash_matches(path, expected):
    if not expected or not path.is_file():
        return False
    raw = path.read_bytes()
    # Windows-produced frozen inputs can be checked out with LF on macOS.
    # Only line terminators may differ; never ignore arbitrary content changes.
    lf = raw.replace(b'\r\n', b'\n')
    return expected in {hashlib.sha256(value).hexdigest() for value in (raw, lf, lf.replace(b'\n', b'\r\n'))}


def bound_train_matrix(run, checkpoint):
    """Read the trial's frozen matrix only when hashes and TRAIN provenance agree."""
    matrix = checkpoint.get('matrix') or {}
    relative = matrix.get('path')
    if not relative:
        return pd.DataFrame()
    root = Path(run.path).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return pd.DataFrame()
    manifest_path = path.with_name(path.stem + '_manifest.json')
    manifest = data.read_json(manifest_path)
    if not recorded_hash_matches(path, matrix.get('sha256')) or manifest.get('output_sha256') != matrix.get('sha256'):
        return pd.DataFrame()
    if matrix.get('manifest_sha256') and not recorded_hash_matches(manifest_path, matrix['manifest_sha256']):
        return pd.DataFrame()
    sources = manifest.get('input_matrices') or []
    if not sources:
        return pd.DataFrame()
    for source in sources:
        directory = str(source.get('directory') or '').replace('\\', '/')
        parts = [part for part in directory.split('/') if part]
        parent = parts[-2] if len(parts) >= 2 else ''
        try:
            partition = data.identify_partition({}, parent)
        except ValueError:
            return pd.DataFrame()
        if partition != 'TRAIN' or source.get('strategy') not in ('R0','R1','R2','R3'):
            return pd.DataFrame()
    return data.read_csv(path)


def collect(runs):
    result = {key: [] for key in TITLES}
    for run in runs:
        if not ((run.partition == 'TRAIN' and run.strategy in ('R0','R1','R2','R3')) or
                (run.partition == 'TEST' and run.strategy in ('R2','R3','R4'))):
            continue
        bundles = data.checkpoints(run)
        q = data.test_table(run, 'per_query')
        difficulties = q.set_index('query_uid').group.to_dict() if {'query_uid','group'} <= set(q) else {}
        contributions = data.read_csv(Path(run.path) / 'regression_matrix/matrix_contributions.csv') if run.partition == 'TRAIN' else None
        matrix = data.matrix_table(run) if run.partition == 'TRAIN' else None
        # Resolve each independent R4 trial's matrix; do not pool trials or inputs.
        for uid, bundle in bundles.items():
            for cp in bundle.get('checkpoints', []):
                evidence = bound_train_matrix(run, cp) if run.strategy == 'R4' else None
                examples = find_examples(run, {uid: dict(bundle, checkpoints=[cp], trial_identities=bundle.get('checkpoints', []))}, matrix, contributions, evidence, difficulties)
                for key in result:
                    result[key].extend(examples[key])
    for examples in result.values():
        examples.sort(key=lambda e: (e['rank'],e['run'].run_id,e['uid'],str(e['trial']),-e['step']), reverse=True)
    return result


def section(category, examples):
    st.subheader(TITLES[category])
    if not examples:
        st.info(EMPTY)
        return
    st.caption(f'{len(examples)} qualifying examples. The default prioritizes clear logged evidence; these are mechanism illustrations.')
    selected = st.selectbox('Selected representative example', range(len(examples)),
        format_func=lambda i: f'{examples[i]["run"].strategy} · {examples[i]["uid"]} · {examples[i]["trial"]} · attempt {examples[i]["step"]} · {examples[i]["run"].run_id}',
        key=f'canonical_example_{category}')
    summary = markdown(examples[selected], category)
    # The section heading already supplies the exported title.
    st.markdown(summary.split('\n', 2)[2])
    st.download_button('Export example Markdown', summary, file_name=f'{category}_example.md', mime='text/markdown', key=f'canonical_export_{category}')


def render(runs):
    examples = collect(runs)
    for category in ('cascade','r2','r3','r4'):
        section(category, examples[category])
        if category == 'r4':
            section('contrast', examples['contrast'])
