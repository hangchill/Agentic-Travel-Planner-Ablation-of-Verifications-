"""Generic per-strategy analysis of explicitly selected repair runs.

Multiple --run arguments produce independent strategy folders only.

No experiment, strategy, verifier, benchmark evaluator, or matrix builder is run.
See scripts/REPAIR_ANALYSIS.md for evidence semantics and reproducibility commands.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chinatravel.evaluation.repair_attempt import RepairAttemptRecord
from chinatravel.evaluation.repair_metrics import compute_attempt_metrics

from scripts import repair_analysis_r4 as r4_analysis

STRATEGIES = ('R0', 'R1', 'R2', 'R3', 'R4')
SCRIPT = 'scripts/analyze_repair_strategies.py'
COUNTERS = ('model_calls', 'repair_model_calls', 'verification_model_calls',
            'failed_model_calls', 'input_tokens_delta', 'output_tokens_delta',
            'total_tokens_delta', 'verification_count', 'tool_call_count',
            'repair_time_seconds', 'verification_time_seconds', 'attempt_time_seconds')
SCOPE_LEVEL = {'slot': 1, 'day': 2, 'plan': 3}


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    def clean(item):
        if isinstance(item, dict):
            return {key: clean(v) for key, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(v) for v in item]
        if isinstance(item, np.generic):
            item = item.item()
        if item is pd.NA or (isinstance(item, float) and not np.isfinite(item)):
            return None
        return item
    path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def save_csv(path, rows, columns=()):
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if frame.empty and not len(frame.columns):
        frame = pd.DataFrame(columns=columns)
    for col in frame:
        frame[col] = frame[col].map(
            lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True)
            if isinstance(v, (list, dict)) else v)
    frame.to_csv(path, index=False, float_format='%.15g', lineterminator='\n')


def file_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def parse_runs(values):
    runs = {}
    for entry in values:
        key, sep, path = entry.partition('=')
        if not sep or key not in STRATEGIES or not path:
            raise ValueError('--run must be R0=DIR, R1=DIR, R2=DIR, R3=DIR, or R4=DIR')
        if key in runs:
            raise ValueError(f'Duplicate strategy key: {key}')
        folder = Path(path)
        if not folder.is_dir():
            raise ValueError(f'Run directory does not exist: {folder}')
        runs[key] = folder
    return dict(sorted(runs.items()))


def state_stats(states, prefix):
    names = ('states', 'satisfied', 'failures', 'unknown', 'evaluable',
             'satisfaction', 'all_personal_pass')
    if states is None:
        return {prefix + k: None for k in names}
    if not isinstance(states, list) or any(x is not None and type(x) is not bool for x in states):
        raise ValueError('Personal states must be a list of bool or None')
    t, f = sum(x is True for x in states), sum(x is False for x in states)
    return dict(zip((prefix + k for k in names), (
        states, t, f, sum(x is None for x in states), t + f,
        t / (t + f) if t + f else None,
        all(x is True for x in states) if states else None)))


def accepted_states(records, initial=None):
    """Return accepted trajectory; rejected candidate states never advance it."""
    current = initial if initial is not None else (
        records[0]['before_personal_constraints'] if records else None)
    trajectory = []
    last_step = 0
    for r in records:
        if r['step'] <= last_step or r['before_personal_constraints'] != current:
            raise ValueError(f'Inconsistent accepted trajectory at step {r["step"]}')
        if r['accepted']:
            current = r['after_personal_constraints']
        trajectory.append(list(current))
        last_step = r['step']
    return trajectory


def record_metrics(record):
    # JSONL run identity is an envelope, not part of RepairAttemptRecord.
    payload = {k: v for k, v in record.items() if k not in ('run_id', 'matrix_run_id')}
    return compute_attempt_metrics(payload)


def persisted(record, key):
    value = record.get(key)
    return value if value is not None else (record.get('repair_metadata') or {}).get(key)


@dataclass
class RunData:
    strategy: str
    path: Path
    manifest: dict
    attempts: list
    checkpoints: dict
    initial_states: dict
    summaries: dict
    benchmarks: dict
    query_uids: list
    messages: list
    checksums: dict
    extra: dict = field(default_factory=dict)


def load_run(strategy, path):
    """One input adapter for complete, attempts-only, or partial local runs."""
    path = Path(path)
    manifest = read_json(path/'run_manifest.json') if (path/'run_manifest.json').exists() else {}
    messages = []
    extra = r4_analysis.load_artifacts(path) if strategy == 'R4' else {}
    attempts = []
    stream = path/'attempts.jsonl'
    if stream.exists():
        for line_number, line in enumerate(stream.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                record_metrics(row)  # Validate persisted transitions with the shared contract.
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f'{stream}:{line_number}: {exc}') from exc
            attempts.append(row)
    summaries = {}
    summary_path = path/'summaries.csv'
    if summary_path.exists():
        for row in pd.read_csv(summary_path).to_dict('records'):
            if row.get('repair_strategy') not in (None, strategy):
                messages.append(f'Summary identity differs: {row.get("repair_strategy")}')
            uid = row['query_uid']
            if uid in summaries:
                raise ValueError(f'Duplicate summary for {uid}')
            summaries[uid] = row
    checkpoints, initials = {}, {}
    for p in sorted((path/'queries').glob('*/*.json')):
        if strategy == 'R4' and p.name in ('final_state.json', 'repair_history.json', 'computational_cost.json'):
            continue  # Selected exports are not last-accepted trial checkpoints.
        row = read_json(p)
        uid = row.get('query_uid')
        if not uid:
            continue
        if p.name == 'initial_state.json':
            initials[uid] = row.get('state', {})
        elif 'final_verification' in row or 'execution_status' in row:
            identity = row.get('repair_strategy')
            if identity not in (None, strategy):
                continue
            if uid in checkpoints:
                raise ValueError(f'Multiple {strategy} checkpoints for {uid}')
            checkpoints[uid] = row
    if strategy == 'R4':
        for trial in extra.get('trials', []):
            uid = trial['query_uid']
            if uid in checkpoints:
                extra['independent_trials'] = True
            else:
                checkpoints[uid] = trial
    if not stream.exists():
        checkpoint_items = ([(t['query_uid'],t) for t in extra.get('trials',[])]
                            if strategy == 'R4' and extra.get('trials') else sorted(checkpoints.items()))
        for uid, cp in checkpoint_items:
            records = cp.get('repair_attempts')
            if not isinstance(records, list):
                records = [e['repair_attempt'] for e in cp.get('repair_history', [])
                           if 'repair_attempt' in e]
            for row in records:
                record_metrics(row)
                attempts.append(row)
        if attempts:
            messages.append('attempts.jsonl absent: using persisted checkpoint repair attempts')
    attempts.sort(key=lambda r: (r['query_uid'], r['step']))
    ids = [(r['query_uid'], r['step'],r['repair_strategy'] if strategy == 'R4' else '') for r in attempts]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate query/step proposal identity')
    evidence_ids = set(manifest.get('repair_strategies', [])) | {
        r.get('repair_strategy') for r in attempts}
    compatible_ids = {strategy}
    if strategy == 'R4':
        compatible_ids.update('R4_'+s for s in ('R0','R1','R2','R3'))
    if evidence_ids - compatible_ids:
        messages.append(f'Supplied {strategy} disagrees with persisted identities: {sorted(evidence_ids)}')
        # One differently labelled run is analyzable with an explicit warning;
        # mixed-strategy attempt streams cannot be pooled as one strategy.
        if len({r['repair_strategy'] for r in attempts}) > 1:
            raise ValueError('Multiple persisted strategies in one attempt stream')
    declared = manifest.get('query_uids')
    evidence_uids = set(summaries) | set(checkpoints) | {r['query_uid'] for r in attempts}
    if declared is None:
        messages.append('No declared population; using sorted union of persisted query evidence')
        query_uids = sorted(evidence_uids)
    else:
        if len(set(declared)) != len(declared):
            raise ValueError('Duplicate declared query UIDs')
        query_uids = sorted(declared)
        outside = evidence_uids - set(declared)
        if outside:
            messages.append(f'Ignoring out-of-population evidence: {sorted(outside)}')
            attempts = [r for r in attempts if r['query_uid'] in declared]
    benchmarks = {str(p.relative_to(path)): read_json(p)
                  for p in sorted(path.glob('benchmark_eval/*/benchmark_summary.json'))}
    for message in messages:
        warnings.warn(f'{path}: {message}', stacklevel=2)
    return RunData(strategy, path, manifest, attempts, checkpoints, initials,
                   summaries, benchmarks, query_uids, messages, file_hashes(path), extra)


def complete_sum(rows, key):
    values = [r.get(key) for r in rows]
    return sum(values) if all(v is not None for v in values) else None


def build_tables(run):
    if run.strategy == 'R4' and run.extra.get('independent_trials'):
        return build_independent_trial_tables(run)
    attempt_rows, query_rows, failure_rows = [], [], []
    for uid in run.query_uids:
        rr = [r for r in run.attempts if r['query_uid'] == uid]
        cp, summary = run.checkpoints.get(uid), run.summaries.get(uid)
        initial = rr[0]['before_personal_constraints'] if rr else (
            (cp or {}).get('initial_verification', {}).get('personal_constraints'))
        final_cp = (cp or {}).get('final_verification') or {}
        trajectory = accepted_states(rr, initial)
        current = trajectory[-1] if trajectory else final_cp.get('personal_constraints', initial)
        if rr and final_cp.get('personal_constraints') is not None:
            if current != final_cp['personal_constraints']:
                raise ValueError(f'{run.strategy}/{uid}: final checkpoint disagrees with attempt stream')
        local = []
        cs_introduced, recovered = set(), set()
        recovery_attempts = 0
        for i, (r, after) in enumerate(zip(rr, trajectory)):
            m = record_metrics(r)
            nxt = rr[i+1] if i+1 < len(rr) else None
            row = {k: v for k, v in r.items()
                   if k not in ('candidate_plan', 'accepted_plan_after', 'repair_metadata')}
            row.update(m)
            for key in ('editable_scope', 'scope_level', 'repair_phase', 'escalation_reason',
                        'protected_constraint_indices', 'target_commonsense_errors'):
                row[key] = persisted(r, key)
            phase = row['repair_phase']
            reason = persisted(r, 'decision_reason')
            protected = persisted(r, 'protected_constraint_indices')
            protected_regressed = (sorted(set(protected) & set(r['newly_violated']))
                                   if protected is not None else None)
            level = row['scope_level'] or SCOPE_LEVEL.get(row['editable_scope'])
            next_level = (persisted(nxt, 'scope_level') or
                          SCOPE_LEVEL.get(persisted(nxt, 'editable_scope'))) if nxt else None
            row.update(strategy=run.strategy, accepted=r['accepted'], rejected=not r['accepted'],
                       accepted_personal_constraints_after=after,
                       unchanged_confirmed=reason == 'no_progress_unchanged',
                       failure_reason=persisted(r, 'failure_reason'),
                       decision_reason=reason, scope_level=level,
                       protected_regressed_indices=protected_regressed,
                       protected_regression_count=len(protected_regressed) if protected_regressed is not None else None,
                       next_observed_action=(
                           'phase_switch' if persisted(nxt, 'repair_phase') != phase else 'continued_same_phase'
                       ) if nxt else ('stopped_'+str(cp.get('stop_reason')) if cp and cp.get('stop_reason') else 'end_of_available_stream_terminal_unknown'),
                       next_scope_escalation=(next_level > level) if next_level and level else None,
                       next_scope=persisted(nxt, 'editable_scope') if nxt else None,
                       llm_cache_hits=persisted(r, 'llm_cache_hits'),
                       rolled_back_constraint_indices=persisted(r, 'rolled_back_constraint_indices'),
                       remembered_broken_constraint_indices=persisted(r, 'remembered_broken_constraint_indices'),
                       candidate_plan_sha256=canonical_hash(r['candidate_plan']) if r.get('candidate_plan') is not None else None,
                       accepted_plan_after_sha256=canonical_hash(r['accepted_plan_after']) if r.get('accepted_plan_after') is not None else None,
                       candidate_equals_accepted_plan_after=(r['candidate_plan'] == r['accepted_plan_after']) if r.get('candidate_plan') is not None and r.get('accepted_plan_after') is not None else None)
            schema = None
            if cp:
                entry = next((e for e in cp.get('repair_history', []) if e.get('step') == r['step']), {})
                verification = entry.get('verification') or {}
                if 'schema_errors' in verification:
                    schema = bool(verification['schema_errors'])
            flags = {
                'target_not_fixed': m['targeted_fixed_count'] < m['targeted_failed_before_count'] if m['targeted_failed_before_count'] else None,
                'new_personal_regression': bool(r['newly_violated']),
                'unchanged_confirmed': row['unchanged_confirmed'],
                'unknown_candidate_state': any(v is None for v in r['after_personal_constraints']),
                'commonsense_induced_personal_regression': phase == 'commonsense' and bool(r['newly_violated']),
                'schema_invalid_candidate': schema,
                'execution_exception': bool(r.get('exception')),
                'failed_model_call': bool(r['failed_model_calls']) if r.get('failed_model_calls') is not None else None,
                'failed_tool_call': bool(r['failed_tool_call_count']) if r.get('failed_tool_call_count') is not None else None,
            }
            for mode, value in flags.items():
                failure_rows.append(dict(strategy=run.strategy, query_uid=uid, step=r['step'],
                                         repair_phase=phase, failure_mode=mode, present=value,
                                         evidence_available=value is not None))
            if row['failure_reason']:
                failure_rows.append(dict(strategy=run.strategy, query_uid=uid, step=r['step'],
                                         repair_phase=phase, failure_mode='metadata:'+row['failure_reason'],
                                         present=True, evidence_available=True))
            if phase == 'commonsense' and r['accepted']:
                cs_introduced.update(r['newly_violated'])
            if phase == 'personal' and any(persisted(x, 'repair_phase') == 'commonsense' for x in rr[:i]):
                recovery_attempts += 1
                if r['accepted']:
                    recovered.update(cs_introduced.intersection(r['fixed']))
            attempt_rows.append(row)
            local.append(row)
        def known_scalar(value):
            return value is not None and not pd.isna(value)
        terminal_status = (cp or {}).get('execution_status')
        if not known_scalar(terminal_status):
            terminal_status = (summary or {}).get('execution_status')
        available = bool(rr) or cp is not None or summary is not None
        # A summary-only run may contain unlogged proposals. Do not invent their events.
        known_zero = ((summary or {}).get('attempts') == 0 or
                      (cp is not None and (cp.get('repair_attempts') == [] or
                       (isinstance(cp.get('repair_history'), list) and
                        len(cp['repair_history']) == 1 and cp['repair_history'][0].get('step') == 0))))
        summary_count = (summary or {}).get('attempts')
        n = len(rr) if rr else (summary_count if known_scalar(summary_count) else (0 if known_zero else None))
        event_evidence = bool(rr) or known_zero
        query = dict(strategy=run.strategy, query_uid=uid, evidence_available=available,
                     trajectory_source=('checkpoint+attempt stream' if cp and rr else
                                        'attempt-stream reconstructed trajectory' if rr else
                                        'checkpoint' if cp else 'summary only' if summary else 'no outcome evidence'),
                     terminal_status_known=known_scalar(terminal_status),
                     execution_status=terminal_status if known_scalar(terminal_status) else None,
                     stop_reason=(cp or summary or {}).get('stop_reason'), attempts=n,
                     personal_attempts=sum(r['repair_phase'] == 'personal' for r in local) if event_evidence else None,
                     commonsense_attempts=sum(r['repair_phase'] == 'commonsense' for r in local) if event_evidence else None,
                     unknown_phase_attempts=sum(r['repair_phase'] not in ('personal', 'commonsense') for r in local) if event_evidence else None,
                     phase_sequence=','.join({'personal': 'P', 'commonsense': 'C'}.get(r['repair_phase'], '?') for r in local) if event_evidence else None,
                     scope_sequence=','.join(r['editable_scope'] or '?' for r in local) if event_evidence else None,
                     personal_after_commonsense_attempts=recovery_attempts if event_evidence else None,
                     commonsense_regressed_indices=sorted(cs_introduced) if event_evidence else None,
                     commonsense_regressions_ever_recovered=sorted(recovered) if event_evidence else None,
                     commonsense_regressions_final_failed=sorted(j for j in cs_introduced if current[j-1] is False) if current is not None else None,
                     total_fixed_events=sum(r['fixed_count'] for r in local) if event_evidence else None,
                     total_regression_events=sum(r['newly_violated_count'] for r in local) if event_evidence else None,
                     cumulative_net_gain=sum(r['net_repair_gain'] for r in local) if event_evidence else None,
                     accepted_net_gain=sum(r['accepted_net_repair_gain'] for r in local) if event_evidence else None,
                     unchanged_proposals=sum(r['unchanged_confirmed'] for r in local) if event_evidence else None)
        query.update(state_stats(initial, 'initial_observed_'))
        query.update(state_stats(current, 'final_observed_'))
        if summary is not None and current is None:
            for ours, theirs in [('failures', 'final_failed_count'), ('unknown', 'final_unknown_count'),
                                 ('satisfaction', 'final_personal_constraint_satisfaction_rate'),
                                 ('all_personal_pass', 'final_all_personal_constraints_pass')]:
                query['final_observed_'+ours] = summary.get(theirs)
        measured = [r for r in local if r.get('changed_slot_rate') is not None]
        query['footprint_valid_attempts'] = len(measured) if event_evidence else None
        denom = sum(r['total_comparable_slots'] for r in measured)
        rate = sum(r['changed_slot_count'] for r in measured)/denom if denom else None
        query['measured_subset_changed_slot_rate'] = rate
        query['changed_slot_rate'] = rate if event_evidence and len(measured) == len(local) else None
        for key in COUNTERS:
            query[key] = complete_sum(local, key) if event_evidence else None
        if summary is not None:
            for key, old in [('attempts', 'attempts'), ('total_fixed_events', 'total_fixed'),
                             ('total_regression_events', 'total_newly_violated'),
                             ('final_observed_failures', 'final_failed_count'),
                             ('final_observed_satisfaction', 'final_personal_constraint_satisfaction_rate')]:
                x, y = query.get(key), summary.get(old)
                if x is not None and y is not None and not pd.isna(x) and not pd.isna(y) and not np.isclose(x, y):
                    raise ValueError(f'{run.strategy}/{uid}: {key} disagrees with summaries.csv')
        query_rows.append(query)
    a = pd.DataFrame(attempt_rows)
    if a.empty:
        a = pd.DataFrame(columns=['strategy', 'query_uid', 'step', 'repair_phase', 'editable_scope',
                                 'scope_level', 'accepted', 'rejected', 'fixed_count',
                                 'newly_violated_count', 'net_repair_gain', 'unchanged_confirmed',
                                 'failure_reason', 'changed_slot_count', 'changed_slot_rate',
                                 'next_observed_action', 'next_scope_escalation', 'targeted_fixed_count',
                                 'targeted_failed_before_count', 'passed_before_count', 'failed_before_count',
                                 'targeted_repair_success_rate', 'new_violation_rate', *COUNTERS])
    q = pd.DataFrame(query_rows)
    if q.empty:
        q = pd.DataFrame(columns=['strategy', 'query_uid', 'attempts', 'personal_attempts',
                                  'commonsense_attempts', 'phase_sequence', 'unchanged_proposals',
                                  *state_stats(None, 'initial_observed_'),
                                  *state_stats(None, 'final_observed_')])
        q['evidence_available'] = pd.Series(dtype=bool)
        q['terminal_status_known'] = pd.Series(dtype=bool)
    return a, q, pd.DataFrame(failure_rows, columns=[
        'strategy', 'query_uid', 'step', 'repair_phase', 'failure_mode', 'present', 'evidence_available'])


def build_independent_trial_tables(run):
    """Apply the same shared calculations per independent trial, never concatenate states."""
    all_a, all_q, all_f = [], [], []
    for uid in run.query_uids:
        trials = [t for t in run.extra['trials'] if t['query_uid']==uid]
        if not trials:
            subset=RunData(run.strategy,run.path,run.manifest,[],{},run.initial_states,{},
                           run.benchmarks,[uid],run.messages,run.checksums)
            a,q,f=build_tables(subset)
            all_a.append(a);all_q.append(q);all_f.append(f)
            continue
        aq, qq = [], []
        for trial in sorted(trials,key=lambda t:t['repair_strategy']):
            label=trial['repair_strategy']
            records=[r for r in run.attempts if r['query_uid']==uid and r['repair_strategy']==label]
            subset=RunData(run.strategy,run.path,run.manifest,records,{uid:trial},run.initial_states,{},
                           run.benchmarks,[uid],run.messages,run.checksums)
            a,q,f=build_tables(subset)
            a['trial_id']=label;f['trial_id']=label
            all_a.append(a);all_f.append(f);aq.append(a);qq.append(q.iloc[0].to_dict())
        q=dict(qq[0]);q['trajectory_source']='independent trial trajectories; no single last-accepted endpoint'
        q.update(state_stats(None,'final_observed_'))
        if any(t['initial_observed_states']!=q['initial_observed_states'] for t in qq):
            q.update(state_stats(None,'initial_observed_'))
        keys=['attempts','personal_attempts','commonsense_attempts','unknown_phase_attempts',
              'personal_after_commonsense_attempts','total_fixed_events','total_regression_events',
              'cumulative_net_gain','accepted_net_gain','unchanged_proposals','footprint_valid_attempts',*COUNTERS]
        for key in keys:q[key]=complete_sum(qq,key)
        for key in ['phase_sequence','scope_sequence']:
            q[key]=' | '.join(t['repair_strategy']+':'+str(v[key]) for t,v in zip(sorted(trials,key=lambda t:t['repair_strategy']),qq))
        for key in ['commonsense_regressed_indices','commonsense_regressions_ever_recovered','commonsense_regressions_final_failed']:
            q[key]=None
        q['trial_trajectories']=qq
        q['terminal_status_known']=all(t['terminal_status_known'] for t in qq)
        q['execution_status']='completed' if all(t['execution_status']=='completed' for t in qq) else None
        q['stop_reason']='independent_trial_stops; see trial_trajectories'
        a=pd.concat(aq,ignore_index=True);measured=a[a.changed_slot_rate.notna()]
        denominator=measured.total_comparable_slots.sum() if len(measured) else 0
        rate=measured.changed_slot_count.sum()/denominator if denominator else None
        q['measured_subset_changed_slot_rate']=rate
        q['changed_slot_rate']=rate if len(measured)==len(a) else None
        all_q.append(pd.DataFrame([q]))
    return pd.concat(all_a,ignore_index=True),pd.concat(all_q,ignore_index=True),pd.concat(all_f,ignore_index=True)


def summarize(run, a, q):
    rows = []
    def add(metric, value, n, unit='attempt'):
        rows.append(dict(strategy=run.strategy, metric=metric, value=value, valid_n=n, unit=unit))
    add('declared_queries', len(run.query_uids) if run.manifest.get('query_uids') is not None else None,
        len(run.query_uids), 'query')
    add('represented_queries', a.query_uid.nunique(), len(run.query_uids), 'query')
    for name, mask in [('total_attempts', pd.Series(True, index=a.index)),
                       ('personal_attempts', a.repair_phase == 'personal'),
                       ('commonsense_attempts', a.repair_phase == 'commonsense'),
                       ('accepted', a.accepted == True), ('rejected', a.accepted == False),
                       ('unchanged_confirmed', a.unchanged_confirmed == True)]:
        add(name, int(mask.sum()), len(a))
    for name, values in [('terminal_outcomes', q.terminal_status_known),
                         ('missing_query_outcomes', ~q.evidence_available)]:
        add(name, int(values.sum()), len(q), 'query')
    represented = q[q.query_uid.isin(a.query_uid)]
    for fn in ('mean', 'median'):
        add(fn+'_attempts_per_represented_query', getattr(represented.attempts, fn)(), len(represented), 'query')
    for key in (*COUNTERS, 'changed_slot_count', 'changed_slot_rate'):
        values = pd.to_numeric(a[key], errors='coerce').dropna()
        for fn in ('sum', 'mean', 'median'):
            if fn == 'sum' and key == 'changed_slot_rate':
                continue
            add(key+'_'+fn, getattr(values, fn)() if len(values) else None, len(values))
        if key == 'total_tokens_delta':
            add('total_tokens_delta_complete_total', values.sum() if len(values) == len(a) else None, len(values))
    for key in ('final_observed_satisfaction', 'final_observed_all_personal_pass', 'final_observed_failures'):
        values = pd.to_numeric(q[key], errors='coerce').dropna()
        add(key+'_mean', values.mean() if len(values) else None, len(values), 'query')
    p = a[a.repair_phase == 'personal']
    for key, mask in [('failed_before', p.failed_before_count > 0), ('fix_any', p.fixed_count > 0),
                      ('regression_any', p.newly_violated_count > 0), ('net_positive', p.net_repair_gain > 0),
                      ('net_zero', p.net_repair_gain == 0), ('net_negative', p.net_repair_gain < 0)]:
        add('personal_'+key, int(mask.sum()), len(p))
    for key in ('fixed_count', 'newly_violated_count', 'net_repair_gain',
                'targeted_repair_success_rate', 'new_violation_rate'):
        values = pd.to_numeric(p[key], errors='coerce').dropna()
        for fn in ('sum', 'mean', 'median'):
            if fn == 'sum' and key.endswith('rate'):
                continue
            add('personal_'+key+'_'+fn, getattr(values, fn)() if len(values) else None, len(values))
    for key, numerator, denominator in [
        ('targeted_success', p.targeted_fixed_count.sum(), p.targeted_failed_before_count.sum()),
        ('new_violation_rate', p.newly_violated_count.sum(), p.passed_before_count.sum()),
        ('repair_success', p.fixed_count.sum(), p.failed_before_count.sum())]:
        add('personal_pooled_'+key, numerator/denominator if denominator else None,
            int(denominator), 'constraint-opportunity')
    add('footprint_measurable_rate', a.changed_slot_rate.notna().mean() if len(a) else None, len(a))
    add('queries_without_evaluable_final_personal_states', int(q.final_observed_satisfaction.isna().sum()), len(q), 'query')
    add('repeated_noop_queries', int((q.unchanged_proposals >= 2).sum()), int(q.unchanged_proposals.notna().sum()), 'query')
    for label, mask in [('zero', q.commonsense_attempts == 0), ('one', q.commonsense_attempts == 1),
                        ('multiple', q.commonsense_attempts > 1)]:
        add('queries_'+label+'_commonsense', int(mask.sum()), int(q.commonsense_attempts.notna().sum()), 'query')
    return pd.DataFrame(rows)


def phase_summary(a):
    rows = []
    for phase, g in a.groupby('repair_phase', dropna=False, sort=True):
        noops = g[g.unchanged_confirmed == True]
        rows.append(dict(repair_phase=phase, attempts=len(g), unchanged=len(noops),
                         unchanged_rate=len(noops)/len(g), fixes=int(g.fixed_count.sum()),
                         regressions=int(g.newly_violated_count.sum()),
                         continued=int(noops.next_observed_action.isin(['phase_switch', 'continued_same_phase']).sum()),
                         phase_switch=int((noops.next_observed_action == 'phase_switch').sum()),
                         scope_escalation=int(noops.next_scope_escalation.eq(True).sum()),
                         known_stop=int(noops.next_observed_action.str.startswith('stopped_').sum()),
                         end_of_stream_unknown_terminal=int((noops.next_observed_action == 'end_of_available_stream_terminal_unknown').sum())))
    return pd.DataFrame(rows, columns=['repair_phase', 'attempts', 'unchanged', 'unchanged_rate',
                                       'fixes', 'regressions', 'continued', 'phase_switch',
                                       'scope_escalation', 'known_stop', 'end_of_stream_unknown_terminal'])


def load_matrices(root):
    """Load saved count/support/rate triplets. Never invoke a matrix builder."""
    rows, messages = [], []
    if not root.is_dir():
        return pd.DataFrame(columns=['scope', 'perspective', 'source_family', 'destination_family',
                                     'regression_count', 'support_count', 'regression_rate']), ['Matrices unavailable']
    contribution_path = root/'matrix_contributions.csv'
    contributions = pd.read_csv(contribution_path) if contribution_path.exists() else None
    directories = [root] + (sorted((root/'by_scope').iterdir()) if (root/'by_scope').is_dir() else [])
    for folder in directories:
        if not folder.is_dir():
            continue
        scope = 'all' if folder == root else folder.name
        for prefix, perspective in [('candidate', 'candidate'), ('accepted', 'accepted_trajectory')]:
            paths = [folder/f'{prefix}_regression_{kind}.csv' for kind in ('rate', 'support', 'count')]
            if not all(p.exists() for p in paths):
                if any(p.exists() for p in paths):
                    messages.append(f'Incomplete matrix triplet: {scope}/{prefix}; not reconstructing missing files')
                continue
            rate, support, count = [pd.read_csv(p, index_col=0) for p in paths]
            if not (rate.index.equals(support.index) and rate.index.equals(count.index) and
                    rate.columns.equals(support.columns) and rate.columns.equals(count.columns)):
                raise ValueError('Matrix triplet axes disagree')
            for src in rate.index:
                for dst in rate.columns:
                    n, k, v = support.loc[src, dst], count.loc[src, dst], rate.loc[src, dst]
                    if pd.isna(n) or pd.isna(k) or n != int(n) or k != int(k) or not 0 <= k <= n:
                        raise ValueError('Invalid persisted matrix count/support')
                    if not (pd.isna(v) if n == 0 else np.isclose(v, k/n)):
                        raise ValueError('Persisted matrix rate disagrees with count/support')
                    cq = None
                    if contributions is not None:
                        cc = contributions[(contributions.perspective == perspective) &
                                           (contributions.source_family == src) &
                                           (contributions.destination_family == dst) &
                                           (contributions.eligible == True)]
                        if scope != 'all':
                            cc = cc[cc.editable_scope == scope]
                        if len(cc) != n or int((cc.regression == True).sum()) != k:
                            raise ValueError('Matrix triplet disagrees with saved contributions')
                        cq = cc.query_uid.nunique()
                    rows.append(dict(scope=scope, perspective=perspective, source_family=src,
                                     destination_family=dst, regression_count=int(k),
                                     support_count=int(n), regression_rate=v, support_queries=cq))
    frame = pd.DataFrame(rows, columns=['scope', 'perspective', 'source_family', 'destination_family',
                                       'regression_count', 'support_count', 'regression_rate', 'support_queries'])
    for filename, scoped in [('regression_matrix_long.csv', False), ('regression_matrix_by_scope_long.csv', True)]:
        path = root/filename
        if path.exists() and not frame.empty:
            for r in pd.read_csv(path).to_dict('records'):
                matched = frame[(frame.scope == (r['editable_scope'] if scoped else 'all')) &
                                (frame.perspective == r['perspective']) &
                                (frame.source_family == r['source_family']) &
                                (frame.destination_family == r['destination_family'])]
                if len(matched) != 1 or matched.iloc[0].support_count != r['support_count'] or matched.iloc[0].regression_count != r['regression_count']:
                    raise ValueError('Saved long matrix disagrees with triplets')
                saved_rate = matched.iloc[0].regression_rate
                if not ((pd.isna(saved_rate) and pd.isna(r['regression_rate'])) or
                        np.isclose(saved_rate, r['regression_rate'])):
                    raise ValueError('Saved long matrix rate disagrees with triplets')
    if frame.empty:
        messages.append('No complete saved matrix triplets; counts/support unavailable')
    return frame, messages


def hook_r0(a):
    out = a[['query_uid', 'step', 'repair_phase', 'editable_scope', 'changed_slot_count',
             'changed_slot_rate', 'fixed_count', 'newly_violated_count', 'net_repair_gain']].copy()
    out['declared_target_count'] = a.target_constraint_indices.map(len) if len(a) else []
    return {'global_rewrite': out}, 'Broad-edit behavior is measured, not assumed harmful. C-phase concentration and multi-target counts are descriptive.'


def hook_r1(a):
    out = a[['query_uid', 'step', 'repair_phase', 'failure_reason', 'unchanged_confirmed',
             'changed_slot_count', 'fixed_count', 'newly_violated_count']].copy()
    out['recorded_localization_failure'] = out.failure_reason.fillna('').str.contains('localiz')
    out['successful_local_repair'] = (out.changed_slot_count == 1) & (out.fixed_count > 0)
    return {'localization': out}, 'Localization failure flags use explicit persisted reasons. One-slot fixes and unchanged local repairs are reported separately.'


def hook_r2(a):
    columns = ['query_uid', 'step', 'repair_phase', 'accepted', 'rejected', 'protected_constraint_indices',
               'protected_regressed_indices', 'protected_regression_count', 'targeted_fixed_count',
               'newly_violated_count', 'accepted_newly_violated_count', 'decision_reason',
               'next_observed_action', 'rolled_back_constraint_indices', 'remembered_broken_constraint_indices',
               'candidate_plan_sha256', 'accepted_plan_after_sha256', 'candidate_equals_accepted_plan_after']
    out = a.reindex(columns=columns).copy()
    if len(out):
        out['harmful_candidate_blocked'] = [bool(rejected and n > 0) if pd.notna(n) else None for rejected, n in zip(out.rejected, out.protected_regression_count)]
        out['fixed_target_but_protected_regression_rejected'] = [bool(blocked and fixed > 0) if pd.notna(blocked) else None for blocked, fixed in zip(out.harmful_candidate_blocked, out.targeted_fixed_count)]
        out['rejected_and_continued'] = out.rejected & out.next_observed_action.isin(['phase_switch', 'continued_same_phase'])
    else:
        for k in ('harmful_candidate_blocked', 'fixed_target_but_protected_regression_rejected', 'rejected_and_continued'):
            out[k] = pd.Series(dtype=bool)
    return {'protection_and_rollback': out}, 'R2 rejects known True→False personal regressions; metadata records protected and rolled-back indices. Candidate harm is retained; rejected states never advance accepted trajectories. Other invalid-candidate reasons are not recast as protection rejections.'


def hook_r3(a):
    rows = a.reindex(columns=['query_uid', 'step', 'repair_phase', 'editable_scope', 'scope_level',
                             'escalation_reason', 'next_scope', 'next_scope_escalation',
                             'unchanged_confirmed', 'fixed_count', 'newly_violated_count',
                             'changed_slot_count', 'targeted_repair_success_rate']).copy()
    scope = rows.groupby('editable_scope', dropna=False, sort=True).agg(
        attempts=('step', 'size'), fixing_attempts=('fixed_count', lambda v: int((v > 0).sum())),
        regression_attempts=('newly_violated_count', lambda v: int((v > 0).sum())),
        mean_changed_slots=('changed_slot_count', 'mean'),
        changed_slots_valid_n=('changed_slot_count', 'count'),
        mean_targeted_success=('targeted_repair_success_rate', 'mean'),
        targeted_success_valid_n=('targeted_repair_success_rate', 'count')).reset_index()
    return {'scope_transitions': rows, 'scope_outcomes': scope}, 'Current R3 code uses fixed iteration-based scope widening (slot→day→plan), including C calls. Persisted scope/escalation sequences are evidence; do not describe the mechanism as failure-triggered. Historical runs may differ; consult their implementation hash and recorded reasons.'


HOOKS = {'R0': hook_r0, 'R1': hook_r1, 'R2': hook_r2, 'R3': hook_r3, 'R4': r4_analysis.hook}


def mechanism_summary(strategy, a, hooks):
    rows = []
    def count(name, values):
        known = values.dropna()
        rows.append(dict(metric=name, count=int(known.sum()) if len(known) else None,
                         valid_n=len(known), rate=known.mean() if len(known) else None))
    if strategy == 'R0':
        count('plan_scope_proposals', a.editable_scope.dropna() == 'plan')
        count('four_or_more_measured_changed_slots', a.changed_slot_count.dropna() >= 4)
        if len(a):
            count('multiple_declared_personal_targets', a.target_constraint_indices.map(len) > 1)
        count('commonsense_proposals_regressing_personal', a[a.repair_phase == 'commonsense'].newly_violated_count > 0)
    elif strategy == 'R1':
        h = hooks['localization']
        count('recorded_localization_failure', h.recorded_localization_failure)
        count('recorded_no_localizable_slot', h.failure_reason.fillna('') == 'no_localizable_slot')
        count('successful_measured_one_slot_repair', h[h.changed_slot_count.notna()].successful_local_repair)
        count('confirmed_unchanged_slot_proposal', a[a.editable_scope == 'slot'].unchanged_confirmed)
    elif strategy == 'R2':
        h = hooks['protection_and_rollback']
        for k in ('rejected', 'harmful_candidate_blocked',
                  'fixed_target_but_protected_regression_rejected', 'rejected_and_continued'):
            count(k, h[k])
        count('rejected_plan_differs_from_accepted', h[h.rejected.eq(True) & h.candidate_equals_accepted_plan_after.notna()].candidate_equals_accepted_plan_after == False)
    elif strategy == 'R3':
        h = hooks['scope_transitions']
        count('next_scope_widens', h.next_scope_escalation)
        count('noop_followed_by_widening', h[h.unchanged_confirmed.eq(True)].next_scope_escalation)
        for scope in ('slot', 'day', 'plan'):
            part = h[h.editable_scope == scope]
            count(scope+'_proposal_fixing_any', part.fixed_count > 0)
            count(scope+'_proposal_regressing_any', part.newly_violated_count > 0)
    elif strategy == 'R4':
        count('plan_scope_proposals', a.editable_scope.dropna() == 'plan')
        count('accepted_proposals', a.accepted)
    return pd.DataFrame(rows, columns=['metric', 'count', 'valid_n', 'rate'])


def markdown(frame):
    def fmt(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 'unavailable'
        return (f'{v:.6g}' if isinstance(v, float) else str(v)).replace('|', '\\|').replace('\n', ' ')
    if frame.empty:
        return 'No supported observations available.\n'
    return ('| '+' | '.join(frame.columns)+' |\n| '+' | '.join(['---']*len(frame.columns))+' |\n' +
            '\n'.join('| '+' | '.join(fmt(v) for v in row)+' |'
                      for row in frame.itertuples(index=False, name=None))+'\n')


def failure_summary(a, failures):
    rows = []
    if failures.empty:
        return pd.DataFrame(columns=['failure_mode', 'count', 'valid_n', 'rate', 'queries'])
    for mode, g in failures.groupby('failure_mode', sort=True):
        if mode.startswith('metadata:'):
            known = a
            positives = g
        else:
            known = g[g.evidence_available]
            positives = known[known.present == True]
        rows.append(dict(failure_mode=mode, count=len(positives) if len(known) else None,
                         valid_n=len(known), rate=len(positives)/len(known) if len(known) else None,
                         queries=positives.query_uid.nunique() if len(known) else None))
    return pd.DataFrame(rows)


def footprint_tables(a):
    bins = a.copy()
    bins['edit_size_bin'] = bins.changed_slot_count.map(
        lambda x: 'unavailable' if pd.isna(x) else '0' if x == 0 else '1' if x == 1 else '2-3' if x <= 3 else '4+')
    grouped = bins.groupby(['repair_phase', 'edit_size_bin'], dropna=False, sort=True).agg(
        attempts=('step', 'size'), mean_fixes=('fixed_count', 'mean'),
        mean_regressions=('newly_violated_count', 'mean'), mean_net_gain=('net_repair_gain', 'mean')).reset_index()
    associations = []
    for phase, g in a.groupby('repair_phase', dropna=False, sort=True):
        for outcome in ('fixed_count', 'newly_violated_count', 'net_repair_gain'):
            v = g[['changed_slot_count', outcome]].dropna()
            # Pearson correlation of average ranks = Spearman; no scipy dependency.
            rho = v.rank().corr().iloc[0, 1] if len(v) > 1 and all(v.nunique() > 1) else None
            associations.append(dict(repair_phase=phase, outcome=outcome, valid_n=len(v),
                                     spearman_descriptive_only=rho))
    return grouped, pd.DataFrame(associations, columns=[
        'repair_phase', 'outcome', 'valid_n', 'spearman_descriptive_only'])


def select_cases(run, a, q):
    choices = [('positive personal net gain', a[(a.repair_phase == 'personal') & (a.net_repair_gain > 0)]),
               ('candidate collateral regression', a[a.newly_violated_count > 0]),
               ('recorded no-op/failure', a[(a.unchanged_confirmed == True) & a.failure_reason.notna()]),
               ('rejected candidate', a[a.rejected == True]),
               ('scope escalation', a[a.next_scope_escalation == True])]
    selected, used = [], set()
    for criterion, candidates in choices:
        for r in candidates.sort_values(['query_uid', 'step']).to_dict('records'):
            identity = (r['query_uid'], r['step'])
            case_identity = (*identity,r['repair_strategy']) if run.strategy=='R4' else identity
            if case_identity in used:
                continue
            used.add(case_identity)
            original = next(x for x in run.attempts if (x['query_uid'], x['step']) == identity and x['repair_strategy']==r['repair_strategy'])
            selected.append(dict(selection=criterion, query_uid=identity[0], step=identity[1],
                                 repair_phase=r['repair_phase'], targets=r.get('target_constraint_indices'),
                                 before=r['before_personal_constraints'], candidate_after=r['after_personal_constraints'],
                                 accepted_after=r['accepted_personal_constraints_after'], fixed=r['fixed'],
                                 regressed=r['newly_violated'], accepted=r['accepted'],
                                 changed_slots=original.get('changed_slot_count'),
                                 failure_reason=r.get('failure_reason'),
                                 constraint_descriptors=original.get('constraint_descriptors')))
            if run.strategy=='R4': selected[-1]['trial_id']=r['repair_strategy']
            break
    return selected


def generate_figures(folder, a, q, matrix, hook_tables):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size': 10, 'svg.fonttype': 'none',
                         'axes.spines.top': False, 'axes.spines.right': False})
    def bar(name, values, title, ylabel='Proposals'):
        if not values:
            return
        fig, ax = plt.subplots(figsize=(8, 4.8))
        ax.bar([str(k) for k in values], list(values.values()), color='#32678c')
        ax.set(title=title, ylabel=ylabel)
        plt.setp(ax.get_xticklabels(), rotation=35, ha='right')
        export(fig, name)
    def export(fig, name):
        fig.tight_layout()
        fig.savefig(folder/(name+'.png'), dpi=300, bbox_inches='tight')
        fig.savefig(folder/(name+'.svg'), bbox_inches='tight')
        plt.close(fig)
    bar('attempts_per_query', q.attempts.dropna().value_counts().sort_index().to_dict(), 'Observed proposals per evidenced query', 'Queries')
    bar('phase_counts', a.repair_phase.fillna('unrecorded').value_counts().sort_index().to_dict(), 'Recorded repair phases')
    bar('fixed_regressed', {'candidate fixed': a.fixed_count.sum(), 'candidate regressed': a.newly_violated_count.sum()}, 'Candidate constraint events', 'Constraint events')
    bar('personal_net_gain', a[a.repair_phase == 'personal'].net_repair_gain.value_counts().sort_index().to_dict(), 'Personal proposal net gain')
    measured = a.changed_slot_count.dropna()
    bar('edit_footprint', measured.value_counts().sort_index().to_dict(), f'Measured changed slots (valid N={len(measured)}/{len(a)})')
    bar('noops', {'confirmed unchanged': int(a.unchanged_confirmed.sum()), 'not confirmed unchanged': int((a.unchanged_confirmed == False).sum())}, 'Recorded no-op evidence')
    bar('failure_reasons', a.failure_reason.dropna().value_counts().sort_index().to_dict(), 'Explicit metadata failure reasons')
    if not matrix.empty:
        for (scope, perspective), cells in matrix.groupby(['scope', 'perspective'], sort=True):
            for kind in ('rate', 'support'):
                pivot = cells.pivot(index='source_family', columns='destination_family', values='regression_'+kind if kind == 'rate' else 'support_count')
                fig, ax = plt.subplots(figsize=(12, 8))
                cmap = plt.get_cmap('YlOrRd' if kind == 'rate' else 'Blues').copy()
                cmap.set_bad('#dddddd')
                im = ax.imshow(np.ma.masked_invalid(pivot.to_numpy(float)), cmap=cmap,
                               vmin=0, vmax=1 if kind == 'rate' else None, aspect='auto')
                for r in cells.to_dict('records'):
                    i, j = list(pivot.index).index(r['source_family']), list(pivot.columns).index(r['destination_family'])
                    label = f'{r["regression_count"]}/{r["support_count"]}' if kind == 'rate' and r['support_count'] else ('—' if kind == 'rate' else str(r['support_count']))
                    value = pivot.iloc[i, j]
                    threshold = .5 if kind == 'rate' else float(np.nanmax(pivot.to_numpy(float)))/2
                    ax.text(j, i, label, ha='center', va='center', fontsize=8,
                            color='white' if pd.notna(value) and value > threshold else 'black')
                ax.set(xticks=range(len(pivot.columns)), yticks=range(len(pivot.index)),
                       xticklabels=pivot.columns, yticklabels=pivot.index,
                       title=f'Saved {perspective}: {scope}, {kind}\nCount/support; unobserved rate cells are gray',
                       xlabel='Destination family', ylabel='Source family')
                plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
                fig.colorbar(im, ax=ax)
                export(fig, f'matrix_{scope}_{perspective}_{kind}')
    if 'localization' in hook_tables:
        local = hook_tables['localization']
        bar('localization_failures', local[local.recorded_localization_failure].failure_reason.value_counts().sort_index().to_dict(), 'Recorded R1 localization reasons')
    if 'protection_and_rollback' in hook_tables:
        r = hook_tables['protection_and_rollback']
        bar('acceptance', {'accepted': int(r.accepted.sum()), 'rejected': int(r.rejected.sum())}, 'R2 candidate decisions')
        bar('candidate_accepted_regressions', {'candidate': r.newly_violated_count.sum(), 'accepted': r.accepted_newly_violated_count.sum()}, 'R2 candidate vs accepted regression events', 'Constraint events')
        bar('protected_rejection', {'protected-harm candidates': int((r.protected_regression_count > 0).sum()), 'blocked': int(r.harmful_candidate_blocked.sum()), 'target fixed but blocked': int(r.fixed_target_but_protected_regression_rejected.sum())}, 'R2 protection evidence')
    r4_analysis.figures(folder, hook_tables, export, bar)
    if 'scope_outcomes' in hook_tables:
        r = hook_tables['scope_outcomes'].set_index('editable_scope')
        bar('scope_usage', r.attempts.to_dict(), 'R3 recorded scope usage')
        bar('scope_fixing_attempts', r.fixing_attempts.to_dict(), 'R3 fixing proposals by scope')
        bar('scope_regression_attempts', r.regression_attempts.to_dict(), 'R3 regression proposals by scope')
        transitions = hook_tables['scope_transitions']
        t = transitions[transitions.next_scope.notna()]
        bar('scope_transitions', (t.editable_scope+' → '+t.next_scope).value_counts().sort_index().to_dict(), 'Observed next-proposal scope transitions')


def evidence_table(run, a, q, matrix):
    return pd.DataFrame([
        dict(metric='attempt records', evidence='directly persisted' if len(a) else 'unavailable', valid_n=len(a)),
        dict(metric='terminal execution status', evidence='directly persisted' if q.terminal_status_known.any() else 'unavailable', valid_n=int(q.terminal_status_known.sum())),
        dict(metric='final observed accepted personal states', evidence='reconstructable from attempts or checkpoint' if q.final_observed_states.notna().any() else 'unavailable', valid_n=int(q.final_observed_states.notna().sum())),
        dict(metric='benchmark summaries', evidence='directly persisted' if run.benchmarks else 'unavailable', valid_n=len(run.benchmarks)),
        dict(metric='saved rate/support/count matrix cells', evidence='directly persisted' if len(matrix) else 'unavailable', valid_n=len(matrix)),
        dict(metric='missing-query outcome', evidence='unavailable', valid_n=int((~q.evidence_available).sum())),
        dict(metric='initial generation efficiency', evidence='not reconstructed; outside common repair-only metrics', valid_n=None),
    ])


def analyze(run, output, timestamp, figures=True):
    output.mkdir(parents=True, exist_ok=True)
    a, q, failures = build_tables(run)
    r4_tables, r4_audit = {}, None
    if run.strategy == 'R4':
        r4_tables = r4_analysis.build_tables(run, a)
        r4_audit = r4_analysis.audit_matrix(run.path, run.extra.get('metadata', {}))
        selected = {r['query_uid']:r for r in run.extra.get('selections', [])}
        extra_query = []
        for uid in q.query_uid:
            sel = selected.get(uid, {})
            extra_query.append({'selected_source':sel.get('selected_source'), 'selected_step':sel.get('selected_step'),
                                **state_stats((sel.get('selected_verification') or {}).get('personal_constraints'), 'selected_final_')})
        q = pd.concat([q.reset_index(drop=True),pd.DataFrame(extra_query)],axis=1)
    summary, phase = summarize(run, a, q), phase_summary(a)
    matrix, matrix_messages = load_matrices(run.path/'regression_matrix')
    hooks, mechanism = HOOKS[run.strategy](a)
    footprints, associations = footprint_tables(a)
    tables = {'attempt_level': a, 'query_level': q, 'overall_summary': summary,
              'phase_summary': phase, 'failure_modes': failures, 'matrix_summary': matrix,
              'failure_summary': failure_summary(a, failures), 'footprint_bins': footprints,
              'footprint_associations': associations,
              'evidence_availability': evidence_table(run, a, q, matrix),
              'mechanism_summary': mechanism_summary(run.strategy, a, hooks), **hooks, **r4_tables}
    if r4_audit is not None:
        for name, key in [('r4_matrix_cells','cells'),('r4_matrix_sources','sources'),('r4_provenance_files','artifacts')]:
            if r4_audit[key]: tables[name] = pd.DataFrame(r4_audit[key])
        write_json(output/'r4_matrix_provenance.json', r4_audit)
        write_json(output/'r4_run_metadata_snapshot.json',run.extra.get('metadata',{}))
        tables['evidence_availability'] = pd.concat([tables['evidence_availability'],pd.DataFrame(r4_analysis.evidence_rows(run,r4_audit))],ignore_index=True)
        benchmark_checks = r4_analysis.validate_population(run)
        if benchmark_checks:
            tables['r4_benchmark_plan_audit'] = pd.DataFrame(benchmark_checks)
    for name, table in tables.items():
        save_csv(output/(name+'.csv'), table, columns=['evidence_unavailable'])
    provenance = dict(strategy=run.strategy, source_run_path=str(run.path),
                      manifest_run_id=run.manifest.get('run_id'),
                      implementation_hash=run.manifest.get('implementation_hash'),
                      input_attempt_count=len(run.attempts), query_count=len(run.query_uids),
                      analysis_script=SCRIPT, analysis_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      analysis_timestamp=timestamp, source_checksums=run.checksums,
                      warnings=run.messages+matrix_messages)
    if run.strategy == 'R4':
        helper=Path(r4_analysis.__file__)
        provenance['analysis_helpers_sha256']={'scripts/repair_analysis_r4.py':hashlib.sha256(helper.read_bytes()).hexdigest()}
    write_json(output/'provenance.json', provenance)
    write_json(output/'existing_benchmark_summaries.json', run.benchmarks)
    cases = select_cases(run, a, q)
    write_json(output/'case_studies.json', cases)
    case_text = '# Deterministic case studies\n\nSorted by UID and step within each explicit criterion; not a representative sample.\n\n'
    for case in cases:
        case_text += f'## {case["selection"]}: {case["query_uid"]}, step {case["step"]}\n\n```json\n{json.dumps(case, ensure_ascii=False, indent=2)}\n```\n\n'
    (output/'case_studies.md').write_text(case_text)
    sections = [
        ('Data source and evidence coverage', markdown(tables['evidence_availability'])),
        ('Repair activity', markdown(summary[summary.metric.isin(['declared_queries', 'represented_queries', 'total_attempts', 'personal_attempts', 'commonsense_attempts', 'accepted', 'rejected', 'terminal_outcomes', 'missing_query_outcomes', 'mean_attempts_per_represented_query', 'model_calls_sum', 'total_tokens_delta_sum', 'total_tokens_delta_complete_total', 'repair_time_seconds_sum'])])),
        ('Personal-constraint effectiveness', markdown(summary[summary.metric.str.startswith('personal_')])),
        ('Regression behavior', 'Candidate transitions include rejected proposals; accepted-event metrics exclude their state changes. Fixes are False→True; regressions True→False. UNKNOWN is neither.\n\n'+markdown(phase)),
        ('Edit footprint', markdown(footprints)+'\n'+markdown(associations)),
        ('No-progress / stopping behavior', 'Only persisted no_progress_unchanged confirms a no-op; zero footprint alone does not. A final stream row is not proof of a stop. Phase summaries distinguish continuation, phase switch, scope escalation, known stop and unknown terminal.\n\n'+markdown(summary[summary.metric.isin(['unchanged_confirmed', 'repeated_noop_queries'])])),
        ('Commonsense-phase behavior', 'Use recorded phases; do not assume the strict single-C 5+1 policy. Query CSV preserves exact phase sequences and post-C accepted recovery. Unknown/missing phases remain unclassified.\n\n'+markdown(q.groupby('phase_sequence', dropna=False).size().reset_index(name='queries'))),
        ('Constraint-interdependency matrix', 'Saved matrices only. Missing/NaN rate means zero support; observed zero rate has positive support. Display filter support ≥5 is not a confidence threshold. commonsense_repair source is separate from personal-target rows.\n\n'+markdown(matrix[(matrix.scope == 'all') & (matrix.support_count >= 5)])),
        ('Failure modes', 'Flags overlap and are not additive. Metadata flags count explicit recorded reasons; absence is not semantic success. Missing evidence is unavailable, not zero failures.\n\n'+markdown(tables['failure_summary'])),
        ('Strategy-specific mechanism analysis', mechanism+'\n\n'+markdown(tables['mechanism_summary'])+'\n'+ '\n'.join(f'See `{name}.csv`.' for name in hooks)),
        ('Case studies', 'See [case_studies.md](case_studies.md) for deterministic selection criteria, UIDs, steps, candidate and accepted states.'),
        ('Interpretation', 'Descriptive within-run evidence. Candidate efficacy, accepted trajectory, locality, support, no-ops and available sample sizes must be read together. Existing benchmark results are preserved verbatim in existing_benchmark_summaries.json and are not recomputed or equated with UNKNOWN-excluding personal satisfaction.'),
        ('Limitations', 'Satisfaction is True/(True+False), excluding None. All-UNKNOWN satisfaction is undefined; UNKNOWN prevents all-pass. Event net gain need not equal endpoint failure reduction when UNKNOWN occurs. Partial known token sums are not complete totals; all common usage/time metrics exclude generation/initialization. Footprint statistics exclude unmeasurable proposals. Missing-query outcomes and terminal status are never inferred from absent attempts. Query-level outcomes use queries; repeated proposals/cache hits are not independent trials. No causal conclusions, significance tests or bootstrap estimates.\n\n'+'\n'.join(run.messages+matrix_messages)),
    ]
    if run.strategy == 'R4':
        extra = [body for _,body in r4_analysis.report_sections(run,tables,r4_audit,markdown)]
        core = dict(sections)
        sections = [
            ('Data source and partition',extra[0]+'\n\n'+core['Data source and evidence coverage']),
            ('R4 mechanism',extra[1]),('Matrix provenance',extra[2]),
            ('Repair activity',core['Repair activity']),
            ('Personal-constraint effectiveness',core['Personal-constraint effectiveness']),
            ('Regression behavior',core['Regression behavior']),
            ('Matrix-guided decisions',extra[3]),('Candidate/trial selection',extra[4]),
            ('Scope and targeting',extra[5]+'\n\n'+core['Edit footprint']),
            ('Protection/safety behavior',extra[6]),
            ('Fallback behavior',extra[7]+'\n\n'+core['No-progress / stopping behavior']),
            ('Computational cost',extra[8]),('Commonsense behavior',core['Commonsense-phase behavior']),
            ('Failure modes',core['Failure modes']),('Case studies',core['Case studies']),
            ('Interpretation',extra[9]+'\n\n'+extra[10]+'\n\n'+core['Interpretation']),
            ('Limitations',core['Limitations'])]
    header = (f'# {run.strategy} repair analysis\n\nStrategy: {run.strategy}  \nSource run: `{run.path}`  \n'
              f'Manifest/run ID: `{run.manifest.get("run_id")}`  \nImplementation hash: `{run.manifest.get("implementation_hash")}`  \n'
              f'Input attempts: {len(a)}  \nAnalysis script: `{SCRIPT}`  \nAnalysis timestamp: {timestamp}  \n'
              'Evidence limitations: optional artifacts can be absent; attempt-stream endpoints are final observed, not certified terminal outcomes.\n\n')
    text = header + '\n'.join(f'## {i}. {title}\n\n{body}\n' for i, (title, body) in enumerate(sections, 1))
    (output/'ANALYSIS.md').write_text(text)
    if figures:
        folder = output/'figures'
        folder.mkdir(exist_ok=True)
        generate_figures(folder, a, q, matrix, {**hooks, **r4_tables, **({'r4_matrix_cells':pd.DataFrame(r4_audit['cells'])} if r4_audit and r4_audit['cells'] else {})})
    else:
        (output/'figures').mkdir(exist_ok=True)
    if run.checksums != file_hashes(run.path):
        raise ValueError(f'Source artifacts changed during analysis: {run.path}')
    print(f'{run.strategy}: source={run.path}, declared/evidenced queries={len(run.query_uids)}, '
          f'attempt queries={a.query_uid.nunique()}, proposals={len(a)}, matrix cells={len(matrix)}')
    return a, q, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='append', required=True, metavar='STRATEGY=DIR',
                        help='Repeat to analyze each supplied strategy independently')
    parser.add_argument('--output-dir', type=Path, default=Path('results/analysis/repair_strategies'))
    parser.add_argument('--no-figures', action='store_true', help='Produce tables/reports without importing matplotlib')
    args = parser.parse_args(argv)
    try:
        paths = parse_runs(args.run)
        output = args.output_dir.resolve()
        destinations = [output, *((output/key).resolve() for key in paths)]
        for source in paths.values():
            src = source.resolve()
            for target in destinations:
                if target == src or src in target.parents or target in src.parents:
                    raise ValueError('Output directory must be disjoint from every source run')
        timestamp = datetime.now(timezone.utc).isoformat()
        runs = {s: load_run(s, p) for s, p in paths.items()}
        for strategy, run in runs.items():
            analyze(run, args.output_dir/strategy, timestamp, not args.no_figures)
        for r in runs.values():
            if r.checksums != file_hashes(r.path):
                raise ValueError(f'Source changed: {r.path}')
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
