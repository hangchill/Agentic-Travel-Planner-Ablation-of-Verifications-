"""Bound, read-only adapters for TEST tables and existing analysis helpers."""
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

from scripts import analyze_repair_strategies as analysis

TABLES = ('per_query', 'table1_pc', 'table2_cs', 'table3_repair_process', 'table4_eval_exp')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).is_file() else {}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def partition(manifest, name=''):
    values = []
    for text in [manifest.get(k, '') for k in ('partition','split','split_query_source')] + [name]:
        matched = set(re.findall(r'(?:^|[_-])(train|test)(?:$|[_-])', str(text).lower()))
        values.extend(matched)
    return next(iter(set(values))).upper() if len(set(values)) == 1 else 'UNKNOWN'


@dataclass
class Evidence:
    key: str
    path: Path
    manifest: dict = field(default_factory=dict)
    population: list = field(default_factory=list)
    q: pd.DataFrame = field(default_factory=pd.DataFrame)
    tables: dict = field(default_factory=dict)
    attempts: pd.DataFrame = field(default_factory=pd.DataFrame)
    query_analysis: pd.DataFrame = field(default_factory=pd.DataFrame)
    raw: object = None
    initial_hashes: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    error: str = ''

    @property
    def strategy(self):
        return 'R4' if self.key == 'R4-no-matrix' else self.key


def reporting(evidence, root, repository):
    """Same source-path/run-ID/population contract as the TEST dashboard loader."""
    root = Path(root)
    readme = root / 'README.md'
    text = readme.read_text(encoding='utf-8') if readme.is_file() else ''
    sections = re.findall(rf'^###[ \t]+{re.escape(evidence.strategy)}[ \t]*\r?\n(.*?)(?=^###[ \t]|\Z)',text,re.M|re.S)
    if len(sections) != 1:
        raise ValueError('Reporting README missing or ambiguous for strategy')
    source = re.search(r'Source run: `([^`]+)`',sections[0])
    run_id = re.search(r'run_id `([^`]+)`',sections[0])
    if not source or not run_id:
        raise ValueError('Reporting source identity missing')
    path = Path(source[1]); path = path if path.is_absolute() else repository/path
    if path.resolve() != evidence.path or run_id[1] != evidence.manifest['run_id']:
        raise ValueError('Reporting source path/run ID differs from requested run')
    folder = root/evidence.strategy
    files = [folder/f'{name}.csv' for name in (*TABLES,'table1b_pc_failure_by_kind')]
    if any(not p.is_file() for p in files):
        raise ValueError('Required TEST tables missing')
    tables = {p.stem:pd.read_csv(p) for p in files}
    q = tables['per_query']
    if (not {'query_uid','repair_strategy','group'} <= set(q) or q.query_uid.duplicated().any() or
        set(q.query_uid) != set(evidence.population) or len(q) != len(evidence.population) or
        set(q.repair_strategy) != {evidence.strategy} or not set(q.group) <= {'easy','medium','human'}):
        raise ValueError('Reporting population, difficulty or strategy does not match manifest')
    evidence.q, evidence.tables = q, tables
    for p in [readme,*files]:
        evidence.inputs[str(p.resolve())] = digest(p)


def load_evidence(key, path, reporting_root, analysis_root, repository):
    if not path:
        return None
    e = Evidence(key,Path(path).resolve())
    try:
        e.manifest = read_json(e.path/'run_manifest.json')
        ids = e.manifest.get('query_uids')
        strategies = e.manifest.get('repair_strategies_requested',e.manifest.get('repair_strategies',[]))
        if partition(e.manifest,e.path.name) != 'TEST' or strategies != [e.strategy]:
            raise ValueError('Required TEST run with exactly the intended strategy is unavailable')
        if not e.manifest.get('run_id') or not isinstance(ids,list) or not ids or len(set(ids)) != len(ids) or any(not isinstance(uid,str) for uid in ids):
            raise ValueError('Invalid manifest identity/population')
        e.population = sorted(ids)
        # The authoritative adapter validates attempt events and accepted trajectories.
        e.raw = analysis.load_run(e.strategy,e.path)
        e.attempts,e.query_analysis,_ = analysis.build_tables(e.raw)
        if e.strategy == 'R4' and e.raw.extra.get('selections'):
            try:
                e.raw.extra['_comparison_tables'] = analysis.r4_analysis.build_tables(e.raw,e.attempts)
            except (KeyError,ValueError,TypeError) as exc:
                e.notes.append('R4 selection helper unavailable: '+str(exc))
        e.inputs.update({str((e.path/p).resolve()):h for p,h in e.raw.checksums.items()})
        if e.strategy == 'R4' and e.raw.extra.get('metadata'):
            try:
                audit=analysis.r4_analysis.audit_matrix(e.path,e.raw.extra['metadata'],repo=repository)
                e.raw.extra['_comparison_matrix_audit']=audit
                for artifact in audit.get('artifacts',[]):
                    resolved=artifact.get('resolved_path')
                    p=repository/resolved if resolved else None
                    if p and p.is_file():
                        e.inputs[str(p.resolve())]=digest(p)
            except (ValueError,OSError,KeyError,TypeError) as exc:
                e.notes.append('TRAIN matrix provenance unavailable: '+str(exc))
        for uid in e.population:
            # Top-level hash records identity; analyzer.initial_states stores only state.
            files = [p for p in (e.path/'queries').glob('*/initial_state.json') if read_json(p).get('query_uid') == uid]
            e.initial_hashes[uid] = read_json(files[0]).get('initial_plan_hash') if len(files)==1 else None
        try:
            reporting(e,reporting_root,repository)
        except (ValueError,OSError,KeyError) as exc:
            e.notes.append('Common TEST reporting unavailable: '+str(exc))
        # Prefer bound generated diagnostic cells, otherwise retain the original pure helper's result.
        for folder in [Path(analysis_root)/e.strategy,Path(analysis_root)/'test'/e.strategy]:
            prov = read_json(folder/'provenance.json')
            source = Path(prov.get('source_run_path',''));source=source if source.is_absolute() else repository/source
            if source.resolve()!=e.path or prov.get('manifest_run_id')!=e.manifest['run_id']:
                continue
            expected=prov.get('source_checksums',{}).get('attempts.jsonl')
            if expected and (not (e.path/'attempts.jsonl').is_file() or digest(e.path/'attempts.jsonl')!=expected):
                continue
            e.notes.append('Bound generated diagnostics available at '+str(folder)+'; proposal definitions reuse analyze_repair_strategies.build_tables/hooks.')
            e.inputs[str((folder/'provenance.json').resolve())]=digest(folder/'provenance.json')
            break
    except (ValueError,OSError,KeyError,TypeError) as exc:
        e.error=str(exc)
    return e
