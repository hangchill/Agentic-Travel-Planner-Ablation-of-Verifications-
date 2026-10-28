"""Cached, read-only adapters. TEST metrics come from the team's saved TEST tables."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / 'results/analysis/repair_strategies'
TEST_TABLES = ROOT / 'test_result_analysis'
STRATEGIES = ('R0', 'R1', 'R2', 'R3', 'R4')
TEST_FILES = ('per_query', 'table1_pc', 'table1b_pc_failure_by_kind', 'table2_cs',
              'table3_repair_process', 'table4_eval_exp')


@dataclass(frozen=True)
class Run:
    path: str
    partition: str
    strategy: str
    run_id: str

    @property
    def label(self):
        return f'{self.partition} {self.strategy} · {self.run_id}'


def stamp(path):
    p = Path(path)
    return (p.stat().st_mtime_ns, p.stat().st_size) if p.is_file() else None


@st.cache_data(show_spinner=False)
def _json(path, version):
    p = Path(path)
    return json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}


def read_json(path):
    return _json(str(path), stamp(path))


@st.cache_data(show_spinner=False)
def _csv(path, version):
    if not Path(path).is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def read_csv(path):
    return _csv(str(path), stamp(path))


@st.cache_data(show_spinner=False)
def _jsonl(path, version):
    if not Path(path).exists():
        return []
    rows = []
    with Path(path).open(encoding='utf-8') as stream:
        for n, line in enumerate(stream, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError as exc:
                    raise ValueError(f'{path}:{n}: invalid JSON') from exc
    return rows


def attempts(run):
    p = Path(run.path) / 'attempts.jsonl'
    return _jsonl(str(p), stamp(p))


def identify_partition(manifest, name=''):
    """Explicit manifest split wins; a conflicting folder split is rejected."""
    def split(text):
        matches = re.findall(r'(?:^|[_-])(train|test)(?:$|[_-])', str(text).lower())
        return matches[0].upper() if len(set(matches)) == 1 else None
    declarations = {v for k in ('partition', 'split_query_source', 'split')
                    if (v := split(manifest.get(k, '')))}
    if len(declarations) > 1:
        raise ValueError('Conflicting partition metadata')
    declared = next(iter(declarations), None)
    folder = split(name)
    if declared and folder and declared != folder:
        raise ValueError(f'Partition mismatch: {name} vs manifest')
    return declared or folder or 'UNKNOWN'


def discover_runs(root=None):
    """Discover immediate manifest-backed runs regardless of directory naming.

    Nested archive trees are not traversed. Valid populations, known partitions,
    supported strategies and persisted run artifacts are required.
    """
    root = Path(root) if root is not None else ROOT
    found = []
    for manifest_path in sorted((root / 'experiments').glob('*/run_manifest.json')):
        p = manifest_path.parent
        try:
            m = read_json(manifest_path)
            partition = identify_partition(m, p.name)
            ids = m.get('query_uids')
            strategies = m.get('repair_strategies_requested', m.get('repair_strategies', []))
            if (partition not in ('TRAIN', 'TEST') or not isinstance(m.get('run_id'), str)
                    or not m['run_id'] or not isinstance(ids, list) or not ids
                    or any(not isinstance(uid, str) or not uid for uid in ids)
                    or len(ids) != len(set(ids)) or not isinstance(strategies, list)):
                continue
            if not any((p / name).exists() for name in ('attempts.jsonl', 'queries', 'summaries.csv')):
                continue
            for strategy in strategies:
                if strategy in STRATEGIES:
                    found.append(Run(str(p.resolve()), partition, strategy, m['run_id']))
        except (ValueError, TypeError, OSError, AttributeError):
            continue  # Malformed/incomplete manifests do not become available runs.
    return found


def analysis_folder(run, analysis_root=None):
    """Prefer partitioned diagnostics; legacy folders must pass identical binding."""
    root = Path(analysis_root) if analysis_root is not None else ANALYSIS
    candidates = [root / run.partition.lower() / run.strategy, root / run.strategy]
    for p in candidates:
        prov = read_json(p / 'provenance.json')
        source = Path(prov.get('source_run_path', ''))
        source = source if source.is_absolute() else ROOT / source
        if source.resolve() != Path(run.path).resolve() or prov.get('manifest_run_id') != run.run_id:
            continue
        expected = prov.get('source_checksums', {}).get('attempts.jsonl')
        stream = Path(run.path) / 'attempts.jsonl'
        if expected and (not stream.is_file() or digest(stream) != expected):
            continue
        return p
    return None


@st.cache_data(show_spinner=False)
def _digest(path, version):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(path):
    return _digest(str(path), stamp(path))


def analysis_table(run, name):
    folder = analysis_folder(run)
    return read_csv(folder / f'{name}.csv') if folder else pd.DataFrame()


def reporting_binding(run, table_root=None):
    """Require generated README identity/path, exact population and complete outputs.

    A partial builder invocation replaces the root README; omitted runs remain
    unavailable until included in a combined regeneration. Never bypass that check.
    """
    root = Path(table_root) if table_root is not None else TEST_TABLES
    if run.partition != 'TEST':
        return None, 'Common reporting requires a TEST run.'
    notes = root / 'README.md'
    if not notes.is_file():
        return None, 'Generated reporting README is unavailable.'
    text = notes.read_text(encoding='utf-8')
    sections = re.findall(rf'^###[ \t]+{re.escape(run.strategy)}[ \t]*\r?\n(.*?)(?=^###[ \t]|\Z)', text, re.M | re.S)
    if len(sections) != 1:
        return None, 'Strategy is absent or ambiguous in the generated README. Regenerate all reporting runs together.'
    section = sections[0]
    identity = re.search(r'run_id `([^`]+)`', section)
    source = re.search(r'Source run: `([^`]+)`', section)
    if not identity or identity[1] != run.run_id or not source:
        return None, 'Generated README does not bind to this run ID/source.'
    source_path = Path(source[1])
    source_path = source_path if source_path.is_absolute() else ROOT / source_path
    if source_path.resolve() != Path(run.path).resolve():
        return None, 'Generated reporting source path differs from the selected run.'
    p = root / run.strategy
    if any(not (p / f'{name}.csv').is_file() for name in TEST_FILES):
        return None, 'Required common TEST reporting files are unavailable.'
    q = read_csv(p / 'per_query.csv')
    m = read_json(Path(run.path) / 'run_manifest.json')
    ids = m.get('query_uids', [])
    if (not {'query_uid', 'repair_strategy'} <= set(q.columns) or q.empty
            or q.query_uid.duplicated().any() or len(ids) != len(set(ids))
            or len(q) != len(ids) or set(q.query_uid) != set(ids)
            or set(q.repair_strategy) != {run.strategy}):
        return None, 'Generated reporting query population/strategy differs from the selected manifest.'
    return p, 'Identity and population match; source freshness is a separate check.'


def test_folder(run, table_root=None):
    return reporting_binding(run, table_root)[0]


def test_table(run, name):
    folder = test_folder(run)
    return read_csv(folder / f'{name}.csv') if folder else pd.DataFrame()


def query_artifacts(run, uid):
    """Nested R4 trials stay independent of post-hoc selected exports."""
    queries = Path(run.path) / 'queries'
    directories = [p.parent for p in queries.glob('*/initial_state.json')
                   if read_json(p).get('query_uid') == uid]
    if not directories:
        directories = [p for p in queries.glob('*') if p.is_dir()
                       and any(read_json(f).get('query_uid') == uid for f in p.glob('*.json'))]
    if not directories:
        return {'checkpoints': [], 'initial': {}, 'selected': {}}
    d = directories[0]
    paths = sorted(list(d.glob(f'{run.strategy}-*.json')) + list((d / 'trials').glob('*.json')))
    pairs = [(p, read_json(p)) for p in paths]
    pairs = [(p, c) for p, c in pairs if c.get('query_uid') == uid and 'final_verification' in c]
    cps = [c for _, c in pairs]
    return {'checkpoints': cps, 'initial': read_json(d / 'initial_state.json'),
            'selected': read_json(d / 'final_state.json'),
            'checkpoint_paths': [str(p) for p, _ in pairs],
            'reference': read_json(d / 'reference/query.json')}


@st.cache_data(show_spinner=False, hash_funcs={Run: lambda r: (r.path, r.partition, r.strategy, r.run_id)})
def _checkpoint_bundle(run, versions):
    ids = read_json(Path(run.path) / 'run_manifest.json').get('query_uids', [])
    return {uid: query_artifacts(run, uid) for uid in ids}


def checkpoints(run):
    files = sorted((Path(run.path) / 'queries').rglob('*.json'))
    return _checkpoint_bundle(run, (stamp(Path(run.path) / 'run_manifest.json'),
                                    tuple((str(p), stamp(p)) for p in files)))


def matrix_table(run):
    """Load saved cell table; never reconstruct a matrix from attempt events."""
    frame = analysis_table(run, 'matrix_summary')
    if not frame.empty:
        return frame[frame.scope == 'all'].copy()
    return read_csv(Path(run.path) / 'regression_matrix/regression_matrix_long.csv')


def benchmark_query(run, uid):
    """Expose persisted benchmark rows without evaluating any plan."""
    folders = sorted((Path(run.path) / 'benchmark_eval').glob(f'{run.strategy}-*'))
    if len(folders) != 1:
        return {}
    result = {}
    for name in ('logical_py', 'commonsense', 'schema'):
        frame = read_csv(folders[0] / f'{name}.csv')
        identity = next((c for c in ('data_id', 'query_uid', 'uid') if c in frame), None)
        if identity:
            result[name] = frame[frame[identity].astype(str) == str(uid)]
    return result


def source_freshness(run, provenance):
    """Check only recorded source hashes, never infer freshness from identity."""
    hashes = provenance.get('source_checksums') or {}
    if not hashes:
        return 'Source freshness cannot be cryptographically verified.'
    root = Path(run.path).resolve()
    for relative, expected in hashes.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or digest(path) != expected:
            return 'Recorded source checksums do not match. Regenerate analysis before interpreting these diagnostics.'
    return 'Recorded source checksums match (listed files only).'


def provenance_rows(run):
    """Expose generation timestamps only when upstream provenance records them."""
    manifest = read_json(Path(run.path) / 'run_manifest.json')
    reporting, reason = reporting_binding(run)
    diagnostics = analysis_folder(run)
    rows = []
    for kind, folder in [('Common TEST reporting', reporting), ('Strategy diagnostics', diagnostics)]:
        prov = read_json(folder / 'provenance.json') if folder else {}
        rows.append({'artifact': kind, 'partition': run.partition, 'source run path': run.path,
                     'run ID': run.run_id, 'generated table path': str(folder) if folder else None,
                     'generation timestamp': prov.get('analysis_timestamp') or prov.get('generation_timestamp'),
                     'query population/count': len(manifest.get('query_uids', [])),
                     'binding': reason if kind == 'Common TEST reporting' else ('Matched' if folder else 'Unavailable'),
                     'source freshness': source_freshness(run, prov)})
    return pd.DataFrame(rows)


def available_reporting_runs(runs):
    """Canonical reporting binding selects the source; never substitute TRAIN."""
    return {strategy: run for strategy in STRATEGIES for run in runs
            if run.strategy == strategy and run.partition == 'TEST' and test_folder(run) is not None}


def available_pc_runs(runs):
    """Backward-compatible PC entry point for shared reporting discovery."""
    return available_reporting_runs(runs)


def pc_references(run):
    folders = sorted((Path(run.path) / 'benchmark_eval').glob(f'{run.strategy}-*'))
    return read_json(folders[0] / 'evaluation_population.json').get('queries', {}) if len(folders) == 1 else {}


def comparison_bundle(identifier):
    """Read CLI-generated comparisons; fail closed on stale inputs or edited outputs.

    No analysis helper, evaluator or subprocess runs on a Streamlit rerun.
    """
    from scripts.result_analysis.ablation_comparisons import COMPARISONS
    if identifier not in COMPARISONS:
        raise ValueError('Unknown comparison')
    folder = ROOT / 'results/analysis/ablation_comparisons' / identifier
    required = [folder / name for name in ('summary.csv','mechanism.csv','validity.json','metadata.json')]
    if any(not p.is_file() for p in required):
        return {'ready': False, 'reason': 'Generated comparison outputs are unavailable. Run the standalone comparison builder.', 'folder': str(folder)}
    try:
        metadata = read_json(folder / 'metadata.json')
        validity = read_json(folder / 'validity.json')
        if metadata.get('schema_version') != 1 or metadata.get('comparison_id') != identifier:
            raise ValueError('Comparison output identity/schema mismatch')
        if set(metadata.get('output_checksums', {})) != {'summary.csv','mechanism.csv','validity.json'} or not metadata.get('analysis_code_checksums'):
            raise ValueError('Required output/code provenance is missing')
        changed = []
        for source in ('source_checksums','analysis_code_checksums'):
            for name, expected in metadata.get(source, {}).items():
                p = Path(name)
                if not p.is_file() or digest(p) != expected:
                    changed.append(name)
        for name, expected in metadata.get('output_checksums', {}).items():
            p = folder / name
            if not p.is_file() or digest(p) != expected:
                changed.append(str(p))
        if changed:
            return {'ready': False, 'reason': 'Comparison outputs are stale or changed. Regenerate analysis before displaying values or deltas.',
                    'changed': changed, 'folder': str(folder)}
        return {'ready': True, 'metadata': metadata, 'validity': validity,
                'summary': read_csv(folder / 'summary.csv'), 'mechanism': read_csv(folder / 'mechanism.csv'),
                'folder': str(folder)}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {'ready': False, 'reason': 'Comparison outputs cannot be verified: ' + str(exc), 'folder': str(folder)}
