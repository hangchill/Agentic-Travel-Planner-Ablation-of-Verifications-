"""Documented display derivations over persisted evidence; no scoring or matrix building.

TEST cohort tables call the team's table_* functions on saved per_query records.
Additional derivations (rates, process summaries, scopes, guidance, trajectories)
are described in README.md. Candidate and accepted outcomes remain distinct.
"""
import json

import pandas as pd
import streamlit as st



def records(frame):
    """Restore CSV blanks to None, as expected by the authoritative table helpers."""
    return frame.astype(object).where(pd.notna(frame), None).to_dict('records')


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: lambda f: f.to_json()})
def team_table(frame, kind, references=None):
    from scripts.result_analysis import build_test_result_tables as team
    functions = {'pc': team.table_pc, 'cs': team.table_cs, 'process': team.table_process,
                 'benchmark': team.table_eval_exp}
    rows = records(frame)
    # Text blanks are empty strings in the builder's per-query contract.
    for r in rows:
        for k in ('pc_failed_kinds_final', 'cs_failed_checks_final'):
            r[k] = r.get(k) or ''
    if kind == 'pc_kinds':
        return pd.DataFrame(team.table_pc_kinds(rows, references))
    return pd.DataFrame(functions[kind](rows))


def family_map(descriptors):
    from chinatravel.evaluation.constraint_families import classify_constraint
    return {d.get('constraint_index'): classify_constraint(d).get('family') or 'unmapped'
            for d in descriptors or []}


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: lambda f: f.to_json()})
def attempt_frame(raw, generated):
    """Prefer generated columns; fill missing diagnostics using shared attempt metrics."""
    from chinatravel.evaluation.repair_metrics import compute_attempt_metrics
    lookup = {(r.get('query_uid'), r.get('step'), r.get('repair_strategy')): r
              for r in records(generated)} if not generated.empty else {}
    out = []
    for source in raw:
        r = dict(source)
        metadata = r.get('repair_metadata') or {}
        key = (r.get('query_uid'), r.get('step'), r.get('repair_strategy'))
        saved = lookup.get(key)
        if saved:
            r.update(saved)
        else:
            payload = {k: v for k, v in source.items() if k not in ('run_id', 'matrix_run_id')}
            r.update(compute_attempt_metrics(payload))
        for k in ('failure_reason', 'decision_reason', 'repair_phase', 'editable_scope'):
            if r.get(k) is None:
                r[k] = metadata.get(k)
        r['accepted'] = source.get('accepted') is True
        r['rejected'] = not r['accepted']
        before = source.get('before_personal_constraints')
        candidate = source.get('after_personal_constraints')
        r['accepted_personal_constraints_after'] = candidate if source.get('accepted') else before
        families = family_map(source.get('constraint_descriptors'))
        r['target_families'] = sorted({families.get(i, 'unmapped')
                                      for i in source.get('target_constraint_indices', [])})
        r['target_family'] = ', '.join(r['target_families']) or ('commonsense_repair'
                              if r.get('repair_phase') == 'commonsense' else 'unmapped')
        protected = source.get('protected_constraint_indices')
        r['protected_regression_count'] = (len(set(protected) & set(source.get('newly_violated', [])))
                                            if protected is not None else None)
        r['unchanged_confirmed'] = r.get('decision_reason') == 'no_progress_unchanged'
        r['structural_guard_failure'] = bool(metadata.get('proposal_rejected_reason'))
        r['guidance'] = guidance_status(metadata)
        r['guidance_support'] = guidance_support(metadata)
        r['localisation_failure'] = 'localiz' in str(r.get('failure_reason') or '').lower()
        # A logged editable location proves localisation; a one-slot fix is a different metric.
        r['localisation_success'] = (bool(metadata.get('editable_slots')) and
                                     not r['localisation_failure']) if 'editable_slots' in metadata else None
        out.append(r)
    return pd.DataFrame(out)


def guidance_cells(metadata):
    cells = list(metadata.get('commonsense_source_risks') or [])
    for ranked in metadata.get('risk_target_ranking') or []:
        cells.extend(ranked.get('destination_risks') or [])
    return [c for c in cells if isinstance(c, dict)]


def guidance_support(metadata):
    return [c['support_count'] for c in guidance_cells(metadata) if c.get('support_count') is not None]


def guidance_status(metadata):
    cells = guidance_cells(metadata)
    if not cells:
        return 'no logged relationship'
    return 'supported' if any((c.get('support_count') or 0) > 0 for c in cells) else 'unsupported'


def filter_attempts(frame, filters):
    if frame.empty:
        return frame
    a = frame.copy()
    if filters.get('phase', 'All') != 'All':
        a = a[a.repair_phase == filters['phase'].lower()]
    if filters.get('round', 'All') != 'All':
        a = a[a.step == int(filters['round'])]
    if filters.get('uid'):
        a = a[a.query_uid.str.contains(filters['uid'], case=False, regex=False)]
    if filters.get('family', 'All') != 'All':
        a = a[a.target_families.map(lambda xs: filters['family'] in xs)
              | (a.target_family == filters['family'])]
    outcome = filters.get('outcome', 'All')
    masks = {'Fixed': a.fixed_count > 0, 'Regression': a.newly_violated_count > 0,
             'Unchanged': a.unchanged_confirmed, 'Rejected': a.rejected.eq(True), 'Accepted': a.accepted.eq(True)}
    return a[masks[outcome]] if outcome != 'All' else a


def filter_queries(q, a, filters):
    if q.empty:
        return q
    out = q.copy()
    if filters.get('uid'):
        out = out[out.query_uid.str.contains(filters['uid'], case=False, regex=False)]
    if any(filters.get(k, 'All') != 'All' for k in ('phase', 'round', 'family', 'outcome')):
        out = out[out.query_uid.isin(a.query_uid if not a.empty else [])]
    return out


def matrix_coverage(frame):
    """Count off-diagonal PC-family cells; support=0 remains undefined, not rate=0."""
    if frame.empty:
        return {}
    m = frame[(frame.source_family != 'commonsense_repair') &
              (frame.source_family != frame.destination_family)].copy()
    supported = m[m.support_count > 0]
    return {'supported cells': len(supported), 'possible cells': len(m),
            'coverage': len(supported) / len(m) if len(m) else None,
            'median support (supported)': supported.support_count.median(),
            'max support': m.support_count.max(),
            'regressions (relationship events)': m.regression_count.sum()}


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: lambda f: f.to_json()})
def pool_saved_cells(frames):
    """Pool existing counts/support only; never classify events or rebuild eligibility."""
    m = pd.concat([f for f in frames if not f.empty], ignore_index=True) if any(not f.empty for f in frames) else pd.DataFrame()
    if m.empty:
        return m
    keys = ['perspective', 'source_family', 'destination_family']
    m = m.groupby(keys, as_index=False)[['support_count', 'regression_count']].sum(min_count=1)
    m['regression_rate'] = m.regression_count / m.support_count.where(m.support_count > 0)
    return m


def pc_cs_extras(q, kind):
    """Missing presentation rows only; reuse saved benchmark counts, never rescore."""
    if q.empty:
        return pd.DataFrame()
    prefix = 'pc' if kind == 'pc' else 'cs'
    total = q[f'{prefix}_total']
    initial = q[f'{prefix}_passed_initial']
    final = q[f'{prefix}_passed_final']
    rows = []
    def add(label, value, n=len(q)):
        rows.append({'metric': label, 'value': value, 'valid N': n})
    # PC averages and final bins already come from team_table; only percentages missing there.
    for label, mask in [('improved', final > initial), ('unchanged', final == initial),
                        ('decreased', final < initial), ('passing all', final == total)]:
        add(f'{prefix.upper()} queries {label} (%)', 100 * mask.mean())
    if kind == 'pc':
        add('All PC except named place (%)', 100 * (q.pc_passed_final_excl_named == q.pc_total_excl_named).mean())
    else:
        valid = total > 0
        for stage in ('initial', 'final'):
            add(f'Avg CS passed {stage}', q[f'cs_passed_{stage}'].mean())
            add(f'Avg CS pass % {stage}', (100 * q.loc[valid, f'cs_passed_{stage}'] / total[valid]).mean(), int(valid.sum()))
        add('Final plans with 2+ failed CS', int(((total - final) >= 2).sum()))
        add('Final plans with >85% CS passed (%)', 100 * (final[valid] / total[valid] > .85).mean(), int(valid.sum()))
    return pd.DataFrame(rows)


def process_summary(q):
    """Additional mean/median process statistics; missing costs never become zero."""
    rows = []
    for name in ('rounds', 'tokens_spent', 'repair_time_s'):
        if name in q:
            s = q[name].dropna()
            rows.append({'metric': name, 'mean': s.mean(), 'median': s.median(), 'valid N': len(s)})
    if 'stop_reason' in q:
        valid = q.stop_reason.notna()
        s = q.loc[valid, 'stop_reason'].eq('repair_budget_exhausted')
        rows.append({'metric': 'Logged budget exhausted', 'count': int(s.sum()),
                     'percent': 100 * s.mean(), 'valid N': int(valid.sum())})
    return pd.DataFrame(rows)


def trajectory(checkpoint):
    """Accepted state advances only on accepted rounds; candidate stays visible.

    Changed classification calls team.round_data on history prefixes, preserving its
    translated-plan definition exactly. CS message counts here are loop diagnostics,
    never benchmark check pass rates.
    """
    from scripts.result_analysis.build_test_result_tables import round_data
    history = checkpoint.get('repair_history') or []
    initial = (history[0].get('verification') if history else None) or checkpoint.get('initial_verification') or {}
    current = initial
    out = []
    last_changed = 0
    for i, entry in enumerate(history[1:], 1):
        candidate = entry.get('verification') or {}
        attempt = entry.get('repair_attempt') or {}
        accepted = entry.get('accepted')
        after = candidate if accepted else current
        prefix = round_data({'repair_history': history[:i + 1]})
        changed = prefix['changed'] > last_changed
        last_changed = prefix['changed']
        before_pc, after_pc = current.get('personal_constraints'), after.get('personal_constraints')
        pairs = list(zip(before_pc, after_pc)) if isinstance(before_pc, list) and isinstance(after_pc, list) else None
        before_cs, after_cs = current.get('commonsense_errors'), after.get('commonsense_errors')
        cs_known = isinstance(before_cs, list) and isinstance(after_cs, list)
        row = {'query_uid': checkpoint.get('query_uid'), 'trial_id': checkpoint.get('repair_strategy'),
               'step': entry.get('step', i), 'phase': attempt.get('repair_phase'),
               'scope': attempt.get('editable_scope'), 'before': current, 'candidate': candidate,
               'after': after, 'accepted': accepted, 'changed_team_definition': changed,
               'PC fixed (accepted)': sum(x is False and y is True for x, y in pairs) if pairs is not None else None,
               'PC new (accepted)': sum(x is True and y is False for x, y in pairs) if pairs is not None else None,
               'PC pass rate (accepted)': state_rate(after_pc),
               'CS errors (accepted)': len(after_cs) if isinstance(after_cs, list) else None,
               'CS messages removed': len(set(before_cs) - set(after_cs)) if cs_known else None,
               'CS messages introduced': len(set(after_cs) - set(before_cs)) if cs_known else None,
               'tokens': attempt.get('total_tokens_delta'), 'repair time (s)': attempt.get('repair_time_seconds'),
               'attempt': attempt}
        out.append(row)
        current = after
    return {'initial': initial, 'rounds': out, 'final': current}


def state_rate(states):
    if not isinstance(states, list):
        return None
    known = sum(type(x) is bool for x in states)
    return sum(x is True for x in states) / known if known else None


def round_summary(rows, cohort_size):
    """Observed accepted rounds only; active-after requires an observed later round.

    Missing later steps are not forward-filled. CS changes are message-set changes,
    not benchmark category fixes. Denominators are shown per observed round.
    """
    if not rows:
        return pd.DataFrame()
    a = pd.DataFrame(rows)
    output = []
    for step, group in a.groupby('step'):
        r = {'round': step, 'observed query/trials': len(group),
             'PC pass rate (accepted)': group['PC pass rate (accepted)'].mean(),
             'CS errors (accepted)': group['CS errors (accepted)'].mean(),
             'plan changed (%)': 100 * group.changed_team_definition.mean(),
             'plan unchanged (%)': 100 * (~group.changed_team_definition).mean(),
             'avg tokens': group.tokens.mean(), 'avg repair time (s)': group['repair time (s)'].mean(),
             'observed active after (%)': 100 * a.loc[a.step > step, 'query_uid'].nunique() / cohort_size if cohort_size else None}
        for label in ('PC fixed (accepted)', 'PC new (accepted)', 'CS messages removed', 'CS messages introduced'):
            s = group[label].dropna()
            r[f'avg {label}'] = s.mean()
            r[f'{label} >=1 (%)'] = 100 * (s > 0).mean()
        r['PC net change (accepted)'] = r['avg PC fixed (accepted)'] - r['avg PC new (accepted)']
        output.append(r)
    return pd.DataFrame(output)


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: lambda f: f.to_json()})
def localisation_summary(a):
    if a.empty:
        return pd.DataFrame()
    rows = []
    for step, g in a.groupby('step'):
        s = g.localisation_success.dropna()
        rows.append({'round': step, 'proposals': len(g), 'explicit failures': int(g.localisation_failure.sum()),
                     'queries with failure': g.loc[g.localisation_failure, 'query_uid'].nunique(),
                     'logged successes': int(s.sum()), 'success evidence N': len(s),
                     'success rate among logged locations (%)': 100 * s.mean() if len(s) else None,
                     'failure rate (%)': 100 * g.localisation_failure.mean()})
    return pd.DataFrame(rows)


def protection_summary(a):
    """Harmful = candidate regressed >=1 explicitly protected PC (R2 persisted logic)."""
    known = a[a.protected_regression_count.notna()] if not a.empty else a
    harmful = known[known.protected_regression_count > 0] if not known.empty else known
    blocked = harmful[harmful.rejected] if not harmful.empty else harmful
    return pd.DataFrame([{'all candidates': len(a), 'protection evidence N': len(known),
                          'harmful candidates': len(harmful), 'rejected harmful candidates': len(blocked),
                          'harmful candidates accepted': len(harmful) - len(blocked),
                          'harmful rejection rate (%)': 100 * len(blocked) / len(harmful) if len(harmful) else None,
                          'queries with preserved PC vector': blocked.query_uid.nunique() if len(blocked) else 0}])


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: lambda f: f.to_json()})
def scope_summary(a, cohort_size=None):
    """Observed scope reaches and transitions, without inferring why widening occurred."""
    if a.empty:
        return pd.DataFrame(), pd.DataFrame()
    ordered = a.sort_values(['query_uid', 'repair_strategy', 'step'])
    rows = []
    level = {'slot': 1, 'day': 2, 'plan': 3}
    for uid, g in ordered.groupby('query_uid'):
        scopes = g.editable_scope.tolist()
        pairs = [(x, y) for x, y, sx, sy in zip(scopes, scopes[1:], g.step, g.step.iloc[1:]) if sy == sx + 1]
        known = [s for s in scopes if s in level]
        rows.append({'query_uid': uid, 'highest scope': max(known, key=level.get) if known else None,
                     'successful repair scopes': ', '.join(sorted(set(g.loc[g.targeted_fixed_count > 0, 'editable_scope'].dropna()))),
                     'escalations': sum(level.get(y, 0) > level.get(x, 4) for x, y in pairs),
                     'slot → day': pairs.count(('slot', 'day')), 'day → plan': pairs.count(('day', 'plan'))})
    cohort = []
    successes = a[a.targeted_fixed_count > 0]
    for scope in level:
        reached = a.loc[a.editable_scope == scope, 'query_uid'].nunique()
        cohort.append({'scope': scope, 'queries reaching': reached,
                       'queries reaching (%)': 100 * reached / (cohort_size or a.query_uid.nunique()),
                       'successful target repairs': int((successes.editable_scope == scope).sum()),
                       'share of successful target repairs (%)': 100 * (successes.editable_scope == scope).mean() if len(successes) else None})
    return pd.DataFrame(rows), pd.DataFrame(cohort)


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: lambda f: f.to_json()})
def guidance_summary(a):
    if a.empty:
        return pd.DataFrame()
    return a.groupby(['step', 'guidance'], as_index=False).agg(
        proposals=('query_uid', 'size'), queries=('query_uid', 'nunique'),
        structural_guard_failures=('structural_guard_failure', 'sum'))


def comparison_issues(runs, manifests, initial_hashes):
    """Conservative gate: same TEST partition, population, settings, budget and inputs."""
    issues = []
    if len(runs) < 2:
        return ['Select at least two runs.']
    if len({r.partition for r in runs}) != 1:
        issues.append('These runs use different dataset partitions and should not be interpreted as a controlled performance comparison.')
    if any(r.partition != 'TEST' for r in runs):
        issues.append('Controlled comparison requires TEST runs.')
    for key in ('query_uids', 'model_identifier', 'sampling_settings', 'max_steps', 'language',
                'oracle_translation', 'seed', 'implementation_hash'):
        values = [m.get(key) for m in manifests]
        if key == 'query_uids':
            values = [sorted(v) if v is not None else None for v in values]
        if any(v is None for v in values) and key not in ('seed',):
            issues.append(f'Comparison metadata unavailable: {key}.')
        elif len({json.dumps(v, sort_keys=True) for v in values}) != 1:
            issues.append(f'Runs differ in {key}.')
    if any(not h or any(v is None for v in h.values()) for h in initial_hashes):
        issues.append('Initial-plan compatibility is unavailable.')
    elif any(h != initial_hashes[0] for h in initial_hashes[1:]):
        issues.append('Initial plans differ across runs.')
    return issues


def candidate_examples(a, category, selections=None, preservation=None):
    """Find narrative candidates; never claim statistical representativeness."""
    if a.empty:
        return a
    if category == 'Cascading regression':
        return a[(a.targeted_fixed_count > 0) & (a.newly_violated_count > 0)]
    if category == 'R2 protection':
        if preservation is None or preservation.empty:
            return a.iloc[:0]
        verified = preservation[preservation['prior accepted plan preserved'].eq(True)]
        return a[(a.protected_regression_count > 0) & a.rejected].merge(
            verified[['query_uid', 'step']].drop_duplicates(), on=['query_uid', 'step'])
    if category == 'R3 widening':
        ids = []
        for uid, g in a.sort_values('step').groupby('query_uid'):
            prior = g[(g.editable_scope == 'slot') & (((g.targeted_failed_before_count > 0) & (g.targeted_fixed_count == 0)) | g.unchanged_confirmed)]
            later = g[g.editable_scope.isin(['day', 'plan']) & (g.targeted_fixed_count > 0)]
            if len(prior) and len(later) and prior.step.min() < later.step.max():
                ids.append(uid)
        return a[a.query_uid.isin(ids)]
    if category == 'R4 guidance':
        ids = set(selections.loc[selections.selected_source != 'initial', 'query_uid']) if selections is not None and not selections.empty else set()
        return a[(a.guidance == 'supported') & a.query_uid.isin(ids)]
    if category == 'R4 limitation':
        ids = set(selections.loc[selections.selected_source == 'initial', 'query_uid']) if selections is not None and not selections.empty else set()
        return a[(a.guidance != 'supported') | a.structural_guard_failure | a.unchanged_confirmed | a.query_uid.isin(ids)]
    return a


def example_markdown(run, row):
    keys = ('query_uid', 'step', 'repair_phase', 'target_family', 'editable_scope', 'accepted',
            'targeted_fixed_count', 'newly_violated_count', 'decision_reason', 'guidance', 'guidance_support')
    return '\n'.join([f'# Candidate example — {run.label}', '',
                      'Manually review before using in a presentation.', '', f'Source: `{run.path}`', ''] +
                     [f'- {k}: {row.get(k)}' for k in keys])


def eligible_matrix_attempts(contributions, perspective):
    """Count unique attempts with saved eligible single-target personal contributions.

    Eligibility is taken verbatim from matrix_contributions.csv, not recomputed.
    An attempt with no eligible destination does not contribute to this count.
    """
    required = {'perspective', 'eligible', 'is_single_target', 'source_family', 'query_uid', 'step'}
    if not required <= set(contributions.columns):
        return None
    c = contributions[(contributions.perspective == perspective) & contributions.eligible.eq(True)
                      & contributions.is_single_target.eq(True)
                      & contributions.source_family.ne('commonsense_repair')]
    return len(c[['query_uid', 'step']].drop_duplicates())


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: lambda f: f.to_json()})
def round_counters(a, q=None):
    """Extra complete per-query counters over the displayed proposal subset."""
    cols = ['model_calls', 'verification_count', 'repair_time_seconds', 'total_tokens_delta',
            'changed_slot_count', 'unchanged_confirmed']
    cols = [c for c in cols if c in a]
    if a.empty:
        return pd.DataFrame()
    result = a.groupby('query_uid')[cols].agg(
        lambda s: s.sum() if s.notna().all() else float('nan')).reset_index()
    if q is not None and 'rounds' in q:
        result = q[['query_uid', 'rounds']].merge(result, on='query_uid', how='left')
        result.loc[result['rounds'].eq(0), cols] = 0
        result = result.drop(columns='rounds')
    return result


def rollback_preservation(bundles):
    """Verify raw accepted-plan equality after rejection against prior accepted plan."""
    rows = []
    for uid, bundle in bundles.items():
        for cp in bundle['checkpoints']:
            current_plan = cp.get('initial_raw_plan')
            for entry in (cp.get('repair_history') or [])[1:]:
                a = entry.get('repair_attempt') or {}
                after = a.get('accepted_plan_after')
                rows.append({'query_uid': uid, 'step': entry.get('step'),
                             'rejected': entry.get('accepted') is False,
                             'prior accepted plan preserved': after == current_plan
                             if after is not None and current_plan is not None else None})
                if entry.get('accepted') and after is not None:
                    current_plan = after
    return pd.DataFrame(rows)


def scope_round_summary(a):
    """Escalation after round N requires a logged next scope in that same trial."""
    rows = []
    if a.empty:
        return pd.DataFrame()
    levels = {'slot': 1, 'day': 2, 'plan': 3}
    for _, g in a.sort_values('step').groupby(['query_uid', 'repair_strategy']):
        entries = list(g.to_dict('records'))
        for before, after in zip(entries, entries[1:]):
            if after['step'] != before['step'] + 1:
                continue
            x, y = levels.get(before['editable_scope']), levels.get(after['editable_scope'])
            if x is not None and y is not None:
                rows.append({'round': before['step'], 'query_uid': before['query_uid'], 'escalated': y > x})
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    return frame.groupby('round', as_index=False).agg(
        queries_with_next_scope=('query_uid', 'nunique'), escalating_queries=('escalated', 'sum'),
        escalating_percent=('escalated', lambda s: 100 * s.mean()))


def accepted_event_summary(a, q):
    """Aggregate shared accepted transition metrics per reporting query.

    These are event totals over the displayed proposals, not benchmark endpoint
    constraint fixes. Zero is assigned only to a proven zero-round query.
    """
    fields = ['accepted_fixed_count', 'accepted_newly_violated_count', 'accepted_net_repair_gain']
    if a.empty or not set(fields) <= set(a):
        return pd.DataFrame()
    grouped = a.groupby('query_uid')[fields].agg(lambda s: s.sum() if s.notna().all() else float('nan'))
    result = q[['query_uid', 'rounds']].merge(grouped, on='query_uid', how='left')
    for field in fields:
        result.loc[result['rounds'].eq(0), field] = 0
    return result


def inventory_row(run, manifest, raw, has_test, has_analysis):
    return {'partition': run.partition, 'strategy': run.strategy,
            'queries': len(manifest.get('query_uids', [])), 'proposals': len(raw),
            'personal attempts': sum(r.get('repair_phase') == 'personal' for r in raw),
            'commonsense attempts': sum(r.get('repair_phase') == 'commonsense' for r in raw),
            'model': manifest.get('model_identifier', 'Unavailable'),
            'settings': str(manifest.get('sampling_settings', 'Unavailable')),
            'budget': manifest.get('max_steps'), 'source path': run.path,
            'TEST tables': has_test, 'strategy analysis': has_analysis}


def state_counts(verification):
    pc, cs = verification.get('personal_constraints'), verification.get('commonsense_errors')
    return {'PC passed': sum(x is True for x in pc) if isinstance(pc, list) else None,
            'PC failed': sum(x is False for x in pc) if isinstance(pc, list) else None,
            'PC unknown': sum(x is None for x in pc) if isinstance(pc, list) else None,
            'CS error messages': len(cs) if isinstance(cs, list) else None}


def cohort_counter_stats(frame, exclude=('query_uid', 'rounds')):
    columns = [c for c in frame if c not in exclude]
    return frame[columns].agg(['mean', 'median', 'count']).T.reset_index(names='metric') if len(frame) else pd.DataFrame()


def proposal_counter_stats(a):
    rows = []
    for key in ['model_calls', 'verification_count', 'changed_slot_rate', 'unchanged_confirmed', 'new_violation_rate', 'accepted_new_violation_rate']:
        if key in a:
            s = a[key].dropna()
            rows.append({'metric': key, 'mean per observed proposal': s.mean(), 'valid N': len(s)})
    return pd.DataFrame(rows)


def localisation_cohort(a):
    return {'Queries with logged localisation': a.loc[a.localisation_success.eq(True), 'query_uid'].nunique(),
            'Queries with localisation failure': a.loc[a.localisation_failure.eq(True), 'query_uid'].nunique(),
            'Localisation evidence N': int(a.localisation_success.notna().sum()),
            'Recorded failures': int(a.localisation_failure.sum())}


def localisation_reasons(a):
    return a.loc[a.localisation_failure.eq(True), 'failure_reason'].value_counts().rename_axis('reason').reset_index(name='count')


def protection_round_summary(a):
    return a[a.protected_regression_count > 0].groupby('step', as_index=False).agg(
        generated=('query_uid', 'size'), rejected=('rejected', 'sum'))


def rollback_cohort(preservation, cohort_size):
    rejected = preservation[preservation.rejected]
    known = rejected[rejected['prior accepted plan preserved'].notna()]
    count = known.loc[known['prior accepted plan preserved'].eq(True), 'query_uid'].nunique()
    return {'Queries with verified plan rollback': count,
            'Queries with verified plan rollback (%)': 100 * count / cohort_size if cohort_size else None,
            'Rejected rounds with equality evidence': len(known)}


def scope_round_usage(a):
    return a.groupby(['step', 'editable_scope'], as_index=False).size()


def guidance_cohort(a):
    return {'Supported queries': a.loc[a.guidance == 'supported', 'query_uid'].nunique(),
            'Unsupported queries': a.loc[a.guidance == 'unsupported', 'query_uid'].nunique(),
            'No-relationship queries': a.loc[a.guidance == 'no logged relationship', 'query_uid'].nunique(),
            'Structural-guard failures': int(a.structural_guard_failure.sum())}


def support_rows(a):
    return a[['query_uid', 'step', 'guidance_support']].explode('guidance_support').dropna()


def value_distribution(frame, key):
    return frame[key].value_counts().sort_index()


def selection_cohort(selections):
    return {'Initial plans selected': int(selections.selected_source.eq('initial').sum()),
            'Repaired outcomes selected': int(selections.selected_source.ne('initial').sum()),
            'Avg outcomes considered (incl. initial)': selections.considered_outcomes.mean()}


def matched_comparison_rows(runs, tables):
    return pd.DataFrame([{'strategy': run.strategy, 'final PC pass rate': q.pc_share_final.mean(),
                          'final CS pass rate': (q.cs_passed_final / q.cs_total).mean(),
                          'avg attempts': q['rounds'].mean(), 'avg tokens': q.tokens_spent.mean(),
                          'avg repair time (s)': q.repair_time_s.mean()}
                         for run, q in zip(runs, tables)])


def observed_rounds(frame, histories=()):
    """Round controls list persisted positive step IDs, never a nominal budget."""
    values = list(frame['step']) if 'step' in frame else []
    values.extend(entry.get('step') for history in histories for entry in history if entry.get('step', 0) != 0)
    numeric = pd.to_numeric(pd.Series(values, dtype=object), errors='coerce').dropna()
    return sorted({int(v) for v in numeric if v > 0 and float(v).is_integer()})


def matrix_support_limit(frames, proposal_support=()):
    """Include pooled saved-cell supports so a multi-strategy view is not capped."""
    pooled = pool_saved_cells(frames)
    values = list(pooled.support_count) if not pooled.empty else []
    values.extend(v for supports in proposal_support for v in supports)
    numeric = pd.to_numeric(pd.Series(values, dtype=object), errors='coerce').dropna()
    return max(0, int(numeric.max())) if len(numeric) else 0


def availability_summary(runs, statuses):
    """Availability derives from bound outputs; diagnostics remain partition-specific.

    Multiple runs stay separate in the detailed coverage table. Summary flags mean
    at least one available matching run, rather than adding overlapping populations.
    """
    rows = []
    for strategy in ('R0', 'R1', 'R2', 'R3', 'R4'):
        train = [r for r in runs if r.strategy == strategy and r.partition == 'TRAIN']
        test = [r for r in runs if r.strategy == strategy and r.partition == 'TEST']
        row = {'strategy': strategy, 'TRAIN run available': bool(train), 'TEST run available': bool(test),
               'common TEST reporting available': any(statuses[r]['reporting'] for r in test),
               'TRAIN generated diagnostics available': any(statuses[r]['diagnostics'] for r in train),
               'TEST generated diagnostics available': any(statuses[r]['diagnostics'] for r in test)}
        for partition, selected in [('TRAIN', train), ('TEST', test)]:
            row[f'{partition} query counts by run'] = ', '.join(
                f'{r.run_id}: {statuses[r]["queries"]}' for r in selected) or 'Unavailable'
        rows.append(row)
    return pd.DataFrame(rows)


# Presentation aliases only: values remain the team's generated table1_pc rows.
PC_REPORT_ROWS = {
    'Avg PC per query': 'Avg personal constraints per query',
    'Avg PC failed: initial': 'Avg PC failed per query - initial plan',
    'Avg PC failed: final': 'Avg PC failed per query - final plan',
    'Avg PC passed: initial': 'Avg PC passed per query - initial plan',
    'Avg PC passed: final': 'Avg PC passed per query - final plan',
    'Avg PC passed: change': 'Avg PC passed per query - change (final - initial)',
    'Avg % PC passed: initial': 'Avg % PC passed per query - initial plan',
    'Avg % PC passed: final': 'Avg % PC passed per query - final plan',
    'Avg % PC passed: change (pts)': 'Avg % PC passed per query - change (percentage points)',
    'Queries: % PC passed increased': 'Queries where % PC passed increased',
    'Queries: % PC same': 'Queries where % PC passed remained the same',
    'Queries: % PC decreased': 'Queries where % PC passed decreased',
    'Queries: all PC pass at start': None,
    'Final plans: 0 failed PC': 'Final plans with 0 failed PC',
    'Final plans: 1 failed PC': 'Final plans with 1 failed PC',
    'Final plans: 2+ failed PC': 'Final plans with 2+ failed PC',
    'All PC passed, excl. named-place': 'Final plans passing all PC, excluding named-place constraints',
    'Avg % PC final, excl. named-place': 'Avg % PC passed per query - final plan, excluding named-place constraints',
}
PC_DIFFICULTIES = {'Easy': 'easy', 'Medium': 'medium', 'Human': 'human'}
PC_ROUND_COMPARISONS = {
    'Mean PC pass rate': 'Mean PC pass rate (%)',
    'Avg # PCs fixed': 'Avg # PCs fixed',
    'New-violation rate': 'New-violation rate (%)',
    'Avg # new PC violations': 'Avg # new PC violations',
    'Avg net PC change': 'Avg net PC change',
    'Queries still active': '# queries still active (observed)',
}


def reporting_difficulties(queries):
    groups = set().union(*(set(q['group'].dropna()) for q in queries.values() if 'group' in q))
    return [label for label, group in PC_DIFFICULTIES.items() if group in groups]


def difficulty_queries(q, difficulty):
    return q[q.group == PC_DIFFICULTIES[difficulty]].copy() if difficulty in PC_DIFFICULTIES else q.copy()


def pc_available_difficulties(queries):
    return reporting_difficulties(queries)


def pc_difficulty_queries(q, difficulty):
    return difficulty_queries(q, difficulty)


def reporting_pivot(summaries, queries, strategies, difficulties, rows):
    """Metric × difficulty/strategy without recomputing any saved numerical cell.

    Empty difficulty populations are omitted. Missing exact metric rows stay NaN.
    The initially-perfect-and-unchanged subset is deliberately not relabelled as
    all initially-perfect queries.
    """
    result = pd.DataFrame({'Metric': list(rows)})
    for difficulty in difficulties:
        column = 'All' if difficulty == 'All' else difficulty
        display = 'Med' if difficulty == 'Medium' else difficulty
        for strategy in strategies:
            q, summary = queries.get(strategy, pd.DataFrame()), summaries.get(strategy, pd.DataFrame())
            if q.empty or pc_difficulty_queries(q, difficulty).empty:
                continue
            values = summary.drop_duplicates('metric').set_index('metric') if 'metric' in summary else pd.DataFrame()
            result[f'{display} {strategy}'] = [
                values.loc[source, column] if source and source in values.index and column in values else float('nan')
                for source in rows.values()]
    return result


def pc_report_pivot(summaries, queries, strategies, difficulties):
    return reporting_pivot(summaries, queries, strategies, difficulties, PC_REPORT_ROWS)


def pc_reporting_sources():
    return pd.DataFrame([{'Displayed metric': label, 'Source file': 'table1_pc.csv' if source else 'Unavailable',
                          'Exact reporting row': source or 'No equivalent row; the initially-perfect-and-unchanged subset is narrower.'}
                         for label, source in PC_REPORT_ROWS.items()])


def pc_failure_table(kinds, strategy, difficulty):
    """Rename the team's kind table; no taxonomy or rate definition changes."""
    required = {'kind', 'failed', 'total', 'failure_rate_pct'}
    if not required <= set(kinds):
        return pd.DataFrame()
    result = kinds.rename(columns={'kind': 'PC family', 'failed': 'Failure count',
                                   'total': 'Total constraints', 'failure_rate_pct': 'Failure rate (%)'}).copy()
    result.insert(0, 'Difficulty', difficulty)
    result.insert(0, 'Strategy', strategy)
    return result


def pc_round_table(q, attempts, bundles):
    """Accepted loop-state diagnostics using shared attempt metrics and saved vectors.

    Endpoints use checkpoint verification, never benchmark shares. Round means
    use only observed proposals; no forward fill. Missing/ambiguous query-step
    evidence is excluded. Active-after means a later observed proposal among the
    selected cohort, and is not proof of scheduler activity. Event metrics have
    no Initial/Final values. Existing accepted_new_violation_rate is kept distinct
    from the fraction of rounds introducing any new violation.
    """
    labels = ['Mean PC pass rate (%)', 'Mean # PC passed', 'Mean # PC failed',
              '% rounds fixing >=1 PC', 'Avg # PCs fixed',
              '% rounds introducing >=1 new PC violation', 'Avg # new PC violations',
              'Avg net PC change', 'New-violation rate (%)',
              '# queries still active (observed)', '% queries still active (observed)',
              'Observed queries (N)']
    if q.empty:
        return pd.DataFrame({'Metric': labels})
    ids = set(q.query_uid)
    a = attempts[attempts.query_uid.isin(ids)].copy() if not attempts.empty else pd.DataFrame()
    if not a.empty:
        a = a[~a.duplicated(['query_uid', 'step'], keep=False)]
    endpoints = {'Initial': [], 'Final': []}
    for uid in ids:
        cps = bundles.get(uid, {}).get('checkpoints', [])
        if len(cps) != 1:
            continue  # Independent trials are not one accepted trajectory.
        cp = cps[0]
        history = cp.get('repair_history') or []
        initial = cp.get('initial_verification') or (history[0].get('verification') if history else {}) or {}
        endpoints['Initial'].append(initial.get('personal_constraints'))
        endpoints['Final'].append((cp.get('final_verification') or {}).get('personal_constraints'))
    from dashboard.utils import parsed
    def states(values):
        vectors = [parsed(v) for v in values]
        vectors = [v for v in vectors if isinstance(v, list)]
        rates = pd.Series([state_rate(v) for v in vectors], dtype=float)
        return {'Mean PC pass rate (%)': 100 * rates.mean(),
                'Mean # PC passed': pd.Series([sum(x is True for x in v) for v in vectors], dtype=float).mean(),
                'Mean # PC failed': pd.Series([sum(x is False for x in v) for v in vectors], dtype=float).mean(),
                'Observed queries (N)': len(vectors)}
    cells = {column: states(vectors) for column, vectors in endpoints.items()}
    if not a.empty:
        cells['Initial']['# queries still active (observed)'] = a.query_uid.nunique()
        cells['Initial']['% queries still active (observed)'] = 100 * a.query_uid.nunique() / len(q)
        for step in observed_rounds(a):
            g = a[a.step == step]
            r = states(g.accepted_personal_constraints_after)
            for metric, field in [('Avg # PCs fixed', 'accepted_fixed_count'),
                                  ('Avg # new PC violations', 'accepted_newly_violated_count'),
                                  ('Avg net PC change', 'accepted_net_repair_gain')]:
                r[metric] = pd.to_numeric(g[field], errors='coerce').mean() if field in g else None
            for metric, field in [('% rounds fixing >=1 PC', 'accepted_fixed_count'),
                                  ('% rounds introducing >=1 new PC violation', 'accepted_newly_violated_count')]:
                known = pd.to_numeric(g[field], errors='coerce').dropna() if field in g else pd.Series(dtype=float)
                r[metric] = 100 * (known > 0).mean()
            r['New-violation rate (%)'] = 100 * pd.to_numeric(g.accepted_new_violation_rate, errors='coerce').mean() if 'accepted_new_violation_rate' in g else None
            active = a.loc[a.step > step, 'query_uid'].nunique()
            r['# queries still active (observed)'] = active
            r['% queries still active (observed)'] = 100 * active / len(q)
            cells[f'Round {step}'] = r
    columns = ['Initial'] + [f'Round {step}' for step in observed_rounds(a)] + ['Final']
    return pd.DataFrame([{'Metric': label, **{c: cells.get(c, {}).get(label) for c in columns}} for label in labels])


def round_comparison(tables, field, endpoints=False, endpoint_columns=True):
    """Align observed step IDs without filling absent strategies/rounds."""
    steps = sorted({int(c.split()[1]) for t in tables.values() for c in t if c.startswith('Round ')})
    columns = (["Initial"] if endpoint_columns else []) + [f'Round {step}' for step in steps] + (["Final"] if endpoint_columns else [])
    rows, points = [], []
    for strategy, t in tables.items():
        if 'Metric' not in t or not t.Metric.eq(field).any():
            continue
        r = t[t.Metric == field].iloc[0]
        rows.append({'Strategy': strategy, **{c: r.get(c) for c in columns}})
        if endpoints:
            points.extend({'Strategy': strategy, 'Stage': c, 'Value': r.get(c)} for c in columns)
        else:
            for step in steps:
                value = r.get(f'Round {step}')
                if pd.notna(value):
                    points.append({'Strategy': strategy, 'Round': step, 'Value': value})
    point_columns = ['Strategy', 'Stage' if endpoints else 'Round', 'Value']
    return pd.DataFrame(rows, columns=['Strategy'] + columns), pd.DataFrame(points, columns=point_columns)


def pc_round_comparison(tables, metric):
    return round_comparison(tables, PC_ROUND_COMPARISONS[metric])


CS_REPORT_ROWS = {
    'Avg CS per query': 'Avg CS per query',
    'Avg CS failed: initial': 'Avg CS checks failed per query - initial plan',
    'Avg CS failed: final': 'Avg CS checks failed per query - final plan',
    'Avg CS passed: initial': 'Avg CS passed: initial',
    'Avg CS passed: final': 'Avg CS passed: final',
    'Avg CS passed: change': 'Avg CS passed: change',
    'Avg % CS passed: initial': 'Avg % CS passed: initial',
    'Avg % CS passed: final': 'Avg % CS passed: final',
    'Avg % CS passed: change (pts)': 'Avg % CS passed: change (pts)',
    'Queries: % CS passed increased': 'Queries where failed CS checks decreased (improved)',
    'Queries: % CS same': 'Queries where failed CS checks stayed the same',
    'Queries: % CS decreased': 'Queries where failed CS checks increased (got worse)',
    'Final plans: 0 failed CS': 'Final plans with 0 failed CS checks',
    'Final plans: 1 failed CS': 'Final plans with 1 failed CS check',
    'Final plans: 2+ failed CS': 'Final plans: 2+ failed CS',
    'Final plans with >85% CS passed': 'Final plans with >85% CS passed',
    '% final plans with >85% CS passed': '% final plans with >85% CS passed',
}
CS_ROUND_COMPARISONS = {
    'Mean CS pass rate': 'Mean CS pass rate (%)',
    'Avg # CS fixed': 'Avg # CS fixed',
    'New CS violation rate': 'New CS violation rate (%)',
    'Avg # new CS violations': 'Avg # new CS violations',
    'Avg net CS change': 'Avg net CS change',
    'Queries still active': '# queries still active (observed)',
    'Mean CS error messages': 'Mean # CS error messages',
    'Avg CS messages removed': 'Avg # CS messages removed',
    'Rounds introducing CS messages (%)': '% rounds introducing >=1 CS message',
    'Avg CS messages introduced': 'Avg # CS messages introduced',
    'Avg net CS message reduction': 'Avg net CS message reduction',
}


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: lambda f: f.to_json()})
def cs_reporting_summary(q, summary):
    """Augment Table 2 with display summaries of its saved per_query counts.

    Existing direct Table 2 cells remain unchanged. Passed means/rates, 2+ bins and
    strict threshold percentages reuse pc_cs_extras. Change-of-passed is the
    negative of the existing change-of-failed row. No scoring is performed.
    """
    from scripts.result_analysis import build_test_result_tables as team
    import re
    result = summary.copy()
    derived = {label: {'metric': label} for label in CS_REPORT_ROWS.values() if label not in set(result.get('metric', []))}
    needed = {'cs_total', 'cs_passed_initial', 'cs_passed_final'}
    groups = list(PC_DIFFICULTIES) + ['All']
    change_source = 'Avg CS checks failed per query - change (final - initial; negative = fewer failures)'
    source = result.set_index('metric') if 'metric' in result else pd.DataFrame()
    thresholds = [label for label in source.index if 'more than 85% of the' in str(label)]
    for group in groups:
        frame = difficulty_queries(q, group)
        values = {}
        if not frame.empty and needed <= set(frame):
            counts = frame[list(needed)].apply(pd.to_numeric, errors='coerce')
            complete = counts.notna().all().all() and (counts.cs_total > 0).all()
            if complete:
                extra = pc_cs_extras(frame, 'cs').set_index('metric').value
                values.update({
                    'Avg CS per query': counts.cs_total.mean(),
                    'Avg CS passed: initial': extra.get('Avg CS passed initial'),
                    'Avg CS passed: final': extra.get('Avg CS passed final'),
                    'Avg % CS passed: initial': extra.get('Avg CS pass % initial'),
                    'Avg % CS passed: final': extra.get('Avg CS pass % final'),
                    'Avg % CS passed: change (pts)': extra.get('Avg CS pass % final') - extra.get('Avg CS pass % initial'),
                    'Final plans: 2+ failed CS': extra.get('Final plans with 2+ failed CS'),
                })
                match = re.search(r'more than 85% of the (\d+) checks passed', str(thresholds[0])) if len(thresholds) == 1 else None
                constant = q.cs_total.nunique() == 1 and counts.cs_total.nunique() == 1
                if constant and team.CS_PASS_THRESHOLD == .85 and match and int(match[1]) == counts.cs_total.iloc[0]:
                    values['Final plans with >85% CS passed'] = source.loc[thresholds[0], group] if group in source else None
                    values['% final plans with >85% CS passed'] = extra.get('Final plans with >85% CS passed (%)')
        if change_source in source.index and group in source:
            value = pd.to_numeric(source.loc[change_source, group], errors='coerce')
            values['Avg CS passed: change'] = -value
        for label, row in derived.items():
            row[group] = values.get(label)
            row['source'] = 'Saved per_query.csv / existing pc_cs_extras; see CS_REPORTING.md'
    return pd.concat([result, pd.DataFrame(derived.values())], ignore_index=True)


def cs_report_pivot(summaries, queries, strategies, difficulties):
    augmented = {s: cs_reporting_summary(queries[s], t) for s, t in summaries.items()}
    result = reporting_pivot(augmented, queries, strategies, difficulties, CS_REPORT_ROWS)
    for column in result.columns[1:]:
        result[column] = pd.to_numeric(result[column], errors='coerce')
    return result


def incompatible_populations(queries, strategies, difficulties):
    """Fail closed for numerical comparisons across different selected UID cohorts."""
    differences = []
    for difficulty in difficulties:
        populations = [frozenset(difficulty_queries(queries[s], difficulty).query_uid) for s in strategies]
        populations = [ids for ids in populations if ids]
        if len(set(populations)) > 1:
            differences.append(difficulty)
    return differences


def cs_failure_families(q, strategy, difficulty):
    """Exact saved failure-check labels, without inferred categories or exceptions.

    No full CS family helper exists upstream. Rates therefore explicitly use plans
    with attributable labels (known nonexception evaluations); exception cases and
    missing/inconsistent label evidence are excluded, never counted as passes.
    Empty labels with zero failed checks are a known passing observation.
    """
    from collections import Counter
    counts = Counter()
    valid, totals = 0, []
    required = {'cs_failed_checks_final', 'cs_evaluator_exception_final', 'cs_total', 'cs_passed_final'}
    if required <= set(q):
        for r in records(q):
            exception = r['cs_evaluator_exception_final']
            if exception is None or exception not in (True, False) or exception:
                continue
            total, passed = r['cs_total'], r['cs_passed_final']
            if total is None or passed is None or not 0 <= passed <= total or total <= 0:
                continue
            labels = r['cs_failed_checks_final'] or ''
            labels = set(labels.split('; ')) if isinstance(labels, str) and labels else set()
            if len(labels) != total - passed:
                continue
            valid += 1
            totals.append(total)
            counts.update(labels)
    rows = [{'Strategy': strategy, 'Difficulty': difficulty, 'CS family': family,
             'Failure count': count, 'Attributable plans (N)': valid,
             'Failure rate (%)': 100 * count / valid if valid and len(set(totals)) == 1 else None}
            for family, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
    columns = ['Strategy', 'Difficulty', 'CS family', 'Failure count', 'Attributable plans (N)', 'Failure rate (%)']
    coverage = {'Strategy': strategy, 'Difficulty': difficulty, 'Queries': len(q),
                'Attributable plans': valid, 'Excluded unattributable plans': len(q) - valid}
    return pd.DataFrame(rows, columns=columns), coverage


def cs_round_table(q, attempts, bundles):
    """Loop error-message diagnostics; never treat messages as benchmark checks.

    Reuses accepted trajectory reconstruction and its persisted message-set changes.
    Requested check-level rates/fixes stay unavailable without a check denominator
    and check-level outcome transitions. Activity reuses the PC round definition.
    """
    labels = ['Mean CS pass rate (%)', 'Mean # CS passed', 'Mean # CS failed',
              '% rounds fixing >=1 CS', 'Avg # CS fixed',
              '% rounds introducing >=1 new CS violation', 'Avg # new CS violations',
              'Avg net CS change', 'New CS violation rate (%)',
              '# queries still active (observed)', '% queries still active (observed)',
              'Mean # CS error messages', '% rounds removing >=1 CS message',
              'Avg # CS messages removed', '% rounds introducing >=1 CS message',
              'Avg # CS messages introduced', 'Avg net CS message reduction', 'Observed CS states (N)']
    activity = pc_round_table(q, attempts, bundles).set_index('Metric')
    columns = list(activity.columns)
    cells = {column: {} for column in columns}
    for label in ('# queries still active (observed)', '% queries still active (observed)'):
        if label in activity.index:
            for column in columns:
                cells[column][label] = activity.loc[label, column]
    ids = set(q.query_uid) if not q.empty else set()
    allowed = set(zip(attempts.query_uid, attempts.step)) if not attempts.empty else set()
    observed = []
    endpoints = {'Initial': [], 'Final': []}
    for uid in ids:
        cps = bundles.get(uid, {}).get('checkpoints', [])
        if len(cps) != 1:
            continue
        cp = cps[0]
        reconstructed = trajectory(cp)
        endpoints['Initial'].append(reconstructed['initial'].get('commonsense_errors'))
        endpoints['Final'].append((cp.get('final_verification') or {}).get('commonsense_errors'))
        observed.extend(r for r in reconstructed['rounds'] if (uid, r['step']) in allowed)
    for stage, values in endpoints.items():
        if stage in cells:
            known = [len(v) for v in values if isinstance(v, list)]
            cells[stage]['Mean # CS error messages'] = pd.Series(known, dtype=float).mean()
            cells[stage]['Observed CS states (N)'] = len(known)
    if observed:
        a = pd.DataFrame(observed)
        a = a[~a.duplicated(['query_uid', 'step'], keep=False)]
        for step, g in a.groupby('step'):
            column = f'Round {step}'
            if column not in cells:
                continue
            known = g['CS errors (accepted)'].dropna()
            r = cells[column]
            r['Mean # CS error messages'] = known.mean()
            r['Observed CS states (N)'] = len(known)
            for label, field, percentage in [
                ('Avg # CS messages removed', 'CS messages removed', '% rounds removing >=1 CS message'),
                ('Avg # CS messages introduced', 'CS messages introduced', '% rounds introducing >=1 CS message')]:
                values = g[field].dropna()
                r[label], r[percentage] = values.mean(), 100 * (values > 0).mean()
            r['Avg net CS message reduction'] = r['Avg # CS messages removed'] - r['Avg # CS messages introduced']
    return pd.DataFrame([{'Metric': label, **{c: cells[c].get(label) for c in columns}} for label in labels])


def cs_round_comparison(tables, metric):
    return round_comparison(tables, CS_ROUND_COMPARISONS[metric], endpoints=True)


def cs_reporting_sources():
    sources = []
    for label, source in CS_REPORT_ROWS.items():
        if source == label:
            origin = 'per_query.csv / pc_cs_extras() display summaries'
            definition = {
                'Avg CS per query': 'Mean cs_total',
                'Avg CS passed: initial': 'Mean cs_passed_initial',
                'Avg CS passed: final': 'Mean cs_passed_final',
                'Avg CS passed: change': 'Negative of Table 2 mean failed-check change',
                'Avg % CS passed: initial': 'Mean 100 * cs_passed_initial / cs_total',
                'Avg % CS passed: final': 'Mean 100 * cs_passed_final / cs_total',
                'Avg % CS passed: change (pts)': 'Final mean pass percentage minus initial mean pass percentage',
                'Final plans: 2+ failed CS': 'Existing pc_cs_extras 2+ bin',
                'Final plans with >85% CS passed': 'Existing table_cs dynamic threshold count; constant check count required',
                '% final plans with >85% CS passed': 'Existing pc_cs_extras strict >85% share; constant check count required',
            }[label]
        else:
            origin, definition = 'table2_cs.csv / table_cs()', source
        if label == 'Avg CS passed: change':
            origin = 'table2_cs.csv / table_cs() mean failed-check change, sign reversed'
        elif label == 'Final plans with >85% CS passed':
            origin = 'table2_cs.csv / table_cs() dynamic threshold row'
        sources.append({'Displayed metric': label, 'Source file/helper': origin,
                        'Definition / exact source row': definition, 'Evidence': 'Benchmark'})
    return pd.DataFrame(sources)


PROCESS_REPORT_ROWS = {
    'Queries with complete token data': '[per query] Queries with token data',
    'Avg tokens per query (complete token data)': '[per query] Avg tokens spent per query (queries with complete token data)',
    'Rounds with no token count': '[per query] Rounds with no recorded token count',
    'Avg tokens, all queries (lower bound)': '[per query] Avg tokens spent per query - all queries, failed requests counted as 0 (lower bound)',
    'Avg repair time per query (s)': '[per query] Avg repair time per query (s)',
    'Queries with >=1 round making changes': '[per query] Queries with at least one round that changed the plan',
    'Δ PC passed per changed round': '[per query] Avg change in PC passed per changed round (loop verifier)',
    'Δ CS errors per changed round': '[per query] Avg change in CS errors per changed round (loop verifier; negative = fewer errors)',
    'Rounds in total': '[round-wise] Repair rounds in total',
    '% rounds: model call failed': None,
    '% rounds: plan changed': '[round-wise] % of rounds where the plan changed',
    '% rounds: unchanged, from cache': '[round-wise] % of rounds unchanged - answered from cache (exact repeat of an earlier request)',
    '% rounds: unchanged, new request': '[round-wise] % of rounds unchanged - from a different request (model called)',
}
PROCESS_ROUND_COMPARISONS = {
    'Queries active': '# queries reaching round',
    'Model call failure rate': '% model call failures',
    'Plan-change rate': '% plan changed',
    'Cache-unchanged rate': '% unchanged from cache',
    'New-request-unchanged rate': '% unchanged from new request',
    'Avg tokens': 'Avg tokens (known counts only)',
    'Avg repair time': 'Avg repair time (s)',
    'Δ PC passed per changed round': 'Δ PC passed per changed round',
    'Δ CS errors per changed round': 'Δ CS errors per changed round',
}


def process_report_pivot(summaries, queries, strategies, difficulties):
    # Upstream renamed this row without changing its tokens_spent_known mean.
    # Preserve the older generated tables as well as future regenerated outputs.
    summaries = {strategy: frame.assign(metric=frame.metric.replace({
        '[per query] Avg tokens spent per query - known values only, all queries (lower bound)':
        PROCESS_REPORT_ROWS['Avg tokens, all queries (lower bound)']}))
        if 'metric' in frame else frame for strategy, frame in summaries.items()}
    result = reporting_pivot(summaries, queries, strategies, difficulties, PROCESS_REPORT_ROWS)
    for column in result.columns[1:]:
        result[column] = pd.to_numeric(result[column], errors='coerce')
    return result


def process_cost_detail(queries, summaries, strategies, difficulty):
    """Cost values are exact Table 3 cells, not reaggregated rounded query totals."""
    rows = []
    fields = {'Complete-token queries': 'Queries with complete token data',
              'Avg tokens/query (complete)': 'Avg tokens per query (complete token data)',
              'Avg tokens/query lower bound': 'Avg tokens, all queries (lower bound)',
              'Missing-token rounds': 'Rounds with no token count',
              'Avg repair time/query (s)': 'Avg repair time per query (s)'}
    pivot = process_report_pivot(summaries, queries, strategies, [difficulty]).set_index('Metric')
    prefix = 'Med' if difficulty == 'Medium' else difficulty
    for strategy in strategies:
        q = difficulty_queries(queries[strategy], difficulty)
        if q.empty:
            continue
        column = f'{prefix} {strategy}'
        r = {'Strategy': strategy, 'Queries': len(q)}
        for label, metric in fields.items():
            r[label] = pivot.loc[metric, column] if column in pivot else None
        r['Token completeness (%)'] = 100 * r['Complete-token queries'] / len(q) if pd.notna(r['Complete-token queries']) else None
        rows.append(r)
    columns = ['Strategy', 'Queries', 'Complete-token queries', 'Token completeness (%)',
               'Avg tokens/query (complete)', 'Avg tokens/query lower bound',
               'Missing-token rounds', 'Avg repair time/query (s)']
    return pd.DataFrame(rows, columns=columns)


def process_round_events(q, attempts, bundles):
    """One persisted proposal per query/step, classified by the unchanged team helper.

    A two-entry history supplies the exact preceding accepted verification and
    the candidate. This preserves candidate deltas even for rejected proposals.
    Missing translated verification evidence stays unavailable in this diagnostic
    adapter rather than fabricating a changed/unchanged classification.
    """
    from scripts.result_analysis.build_test_result_tables import round_data
    rows, seen = [], set()
    ids = set(q.query_uid) if not q.empty else set()
    for uid in ids:
        cps = bundles.get(uid, {}).get('checkpoints', [])
        if len(cps) != 1:
            continue
        cp = cps[0]
        history = cp.get('repair_history') or []
        reconstructed = trajectory(cp)['rounds']
        for entry, state in zip(history[1:], reconstructed):
            step = entry.get('step')
            if not isinstance(step, int) or step <= 0:
                continue
            seen.add((uid, step))
            a = entry.get('repair_attempt') or {}
            before, candidate = state['before'], state['candidate']
            known = before.get('translated_plan') is not None and candidate.get('translated_plan') is not None
            metric = round_data({'repair_history': [{'verification': before}, entry]}) if known else {}
            rows.append({'query_uid': uid, 'step': step,
                         'plan changed': metric.get('changed'), 'unchanged cache': metric.get('unchanged_cache'),
                         'unchanged new request': metric.get('unchanged_other'),
                         'PC delta changed': metric.get('dpc_per_changed') if isinstance(before.get('personal_constraints'), list) and isinstance(candidate.get('personal_constraints'), list) else None,
                         'CS delta changed': metric.get('dcs_per_changed') if isinstance(before.get('commonsense_errors'), list) and isinstance(candidate.get('commonsense_errors'), list) else None,
                         'tokens': a.get('total_tokens_delta'), 'repair time': a.get('repair_time_seconds'),
                         'failed model calls': a.get('failed_model_calls')})
    # An identity-only stream observation proves a reached round, not its outcome/cost.
    if not attempts.empty:
        for r in attempts[attempts.query_uid.isin(ids)].to_dict('records'):
            key = (r['query_uid'], r['step'])
            if key not in seen:
                rows.append({'query_uid': key[0], 'step': key[1]})
    columns = ['query_uid', 'step', 'plan changed', 'unchanged cache', 'unchanged new request',
               'PC delta changed', 'CS delta changed', 'tokens', 'repair time', 'failed model calls']
    frame = pd.DataFrame(rows, columns=columns)
    return frame[~frame.duplicated(['query_uid', 'step'], keep=False)]


def process_outcomes(q, events):
    """The three team outcomes are exclusive; failure flags overlap all three."""
    def complete_sum(key):
        return q[key].sum(min_count=len(q)) if len(q) and key in q else float('nan')
    total = complete_sum('rounds')
    rows = []
    for label, key in [('Plan changed', 'changed'), ('Unchanged: cache', 'unchanged_cache'),
                       ('Unchanged: new request', 'unchanged_other')]:
        n = complete_sum(key)
        rows.append({'Outcome': label, 'Count': n, '% of rounds': 100 * n / total if total > 0 else None,
                     'Evidence rounds (N)': total})
    known = events['failed model calls'].dropna() if 'failed model calls' in events else pd.Series(dtype=float)
    complete = pd.notna(total) and len(events) == total and len(known) == total
    failures = int((known > 0).sum()) if complete else None
    rows.append({'Outcome': 'Model call failed (overlapping)', 'Count': failures,
                 '% of rounds': 100 * failures / total if complete and total > 0 else None,
                 'Evidence rounds (N)': len(known)})
    return pd.DataFrame(rows)


def process_round_table(events):
    labels = ['# queries reaching round', '# model call failures', '% model call failures',
              '# plan changed', '% plan changed', '# unchanged from cache', '% unchanged from cache',
              '# unchanged from new request', '% unchanged from new request',
              'Avg tokens (known counts only)', 'Missing token counts', 'Avg repair time (s)',
              'Δ PC passed per changed round', 'Δ CS errors per changed round',
              'Classification evidence (N)', 'Failure counter evidence (N)', 'Token evidence (N)']
    columns = observed_rounds(events)
    cells = {}
    for step in columns:
        g = events[events.step == step]
        r = {'# queries reaching round': g.query_uid.nunique()}
        for label, key in [('plan changed', 'plan changed'), ('unchanged from cache', 'unchanged cache'),
                           ('unchanged from new request', 'unchanged new request')]:
            values = g[key].dropna()
            count = values.sum() if len(values) == len(g) else None
            r[f'# {label}'] = count
            r[f'% {label}'] = 100 * count / len(g) if count is not None else None
        failures = g['failed model calls'].dropna()
        n = int((failures > 0).sum()) if len(failures) == len(g) else None
        r.update({'# model call failures': n, '% model call failures': 100 * n / len(g) if n is not None else None,
                  'Avg tokens (known counts only)': g.tokens.mean(), 'Missing token counts': int(g.tokens.isna().sum()),
                  'Avg repair time (s)': g['repair time'].mean(),
                  'Δ PC passed per changed round': g['PC delta changed'].mean(),
                  'Δ CS errors per changed round': g['CS delta changed'].mean(),
                  'Classification evidence (N)': int(g['plan changed'].notna().sum()),
                  'Failure counter evidence (N)': len(failures), 'Token evidence (N)': int(g.tokens.notna().sum())})
        cells[f'Round {step}'] = r
    return pd.DataFrame([{'Metric': label, **{c: r.get(label) for c, r in cells.items()}} for label in labels])


def process_round_comparison(tables, metric):
    return round_comparison(tables, PROCESS_ROUND_COMPARISONS[metric], endpoint_columns=False)


def process_additional_diagnostics(q, attempts):
    """Secondary persisted-counter diagnostics, with explicit valid-query N."""
    rows = []
    for operation in ('mean', 'median'):
        values = q['rounds'].dropna() if 'rounds' in q else pd.Series(dtype=float)
        rows.append({'Metric': f'{operation.title()} observed proposals/query',
                     'Value': getattr(values, operation)(), 'Valid query N': len(values)})
    counters = round_counters(attempts, q)
    if counters.empty:
        counters = q[['query_uid', 'rounds']].copy()
        for field in ('model_calls', 'verification_count', 'changed_slot_count'):
            counters[field] = [0 if n == 0 else float('nan') for n in counters['rounds']]
    elif not attempts.empty:
        observed = attempts.groupby('query_uid').size()
        expected = q.set_index('query_uid')['rounds']
        complete = counters.query_uid.map(lambda uid: observed.get(uid, 0) == expected.get(uid))
        for field in counters.columns.difference(['query_uid']):
            counters.loc[~complete, field] = float('nan')
    for field, label in [('model_calls', 'Mean recorded model calls/query'),
                         ('verification_count', 'Mean repair verifier calls/query'),
                         ('changed_slot_count', 'Mean total changed-slot events/query')]:
        values = counters[field].dropna() if field in counters else pd.Series(dtype=float)
        rows.append({'Metric': label, 'Value': values.mean(), 'Valid query N': len(values)})
    known = q.stop_reason.notna() if 'stop_reason' in q else pd.Series(dtype=bool)
    rate = 100 * q.loc[known, 'stop_reason'].eq('repair_budget_exhausted').mean() if known.any() else None
    rows.append({'Metric': 'Queries with logged repair budget exhaustion (%)', 'Value': rate, 'Valid query N': int(known.sum())})
    return pd.DataFrame(rows)


def process_reporting_sources():
    return pd.DataFrame([{'Displayed metric': label, 'Source': 'table3_repair_process.csv / table_process()' if source else 'Unavailable',
                          'Exact source row': source or 'No established Table 3 failure-percentage row; logged failures are separate diagnostics.'}
                         for label, source in PROCESS_REPORT_ROWS.items()])


EVALUATION_REPORT_ROWS = {
    'Commonsense micro*': 'Commonsense micro (%) - share of all (plan, check) pairs passed',
    'Commonsense macro': 'Commonsense macro (%) - plans passing every CS check',
    'Logical micro': 'Logical micro (%) - share of all personal constraints passed (pooled)',
    'Logical macro': 'Logical macro (%) - plans passing every personal constraint',
    'All-pass ratio': 'All-pass ratio (%) - schema + CS + PC all passed',
}
EVALUATION_METRICS = ['Commonsense micro', 'Commonsense macro', 'Logical micro', 'Logical macro', 'All-pass ratio']
EVALUATION_MICRO_FOOTNOTE = (
    '* Commonsense micro retains the raw evaluator matrix, including its evaluator-exception column. '
    'A checker crash can leave ordinary checks unmarked; the reporting documentation warns this can inflate micro. '
    'Table 2 instead counts evaluator exceptions as failing every standard check. No correction is applied to Table 4.'
)


def evaluation_summary(q):
    """Reuse the original table_eval_exp for filtered saved benchmark rows only.

    Incomplete raw evaluator fields cannot be reconstructed from aggregate results.
    Fail closed for the filtered table rather than inferring missing results.
    """
    required = {'cs_total_raw_final', 'cs_failed_raw_final', 'pc_total', 'pc_passed_final',
                'pc_failed_final', 'all_pass_final', 'group', 'query_uid'}
    if required <= set(q) and q[list(required)].notna().all().all():
        return team_table(q, 'benchmark')
    return pd.DataFrame([{'metric': source, 'Easy': None, 'Medium': None, 'Human': None, 'All': None,
                          'source': 'Unavailable: incomplete saved per-query evaluator fields'}
                         for source in EVALUATION_REPORT_ROWS.values()])


def evaluation_pivot(summaries, queries, strategies, difficulties):
    """Source percentages are already 0–100. Never multiply or recompute them."""
    result = reporting_pivot(summaries, queries, strategies, difficulties, EVALUATION_REPORT_ROWS)
    result = result.rename(columns={'Metric': 'Metric (%)'})
    for column in result.columns[1:]:
        result[column] = pd.to_numeric(result[column], errors='coerce')
    return result


def evaluation_scores(summaries, queries, strategies, difficulty, metric):
    display = metric + '*' if metric == 'Commonsense micro' else metric
    pivot = evaluation_pivot(summaries, queries, strategies, [difficulty]).set_index('Metric (%)')
    prefix = 'Med' if difficulty == 'Medium' else difficulty
    return pd.DataFrame([{'Strategy': s, 'Score (%)': pivot.loc[display, f'{prefix} {s}']}
                         for s in strategies if f'{prefix} {s}' in pivot], columns=['Strategy', 'Score (%)'])


def evaluation_strategy_profile(summaries, queries, strategy, difficulty):
    frame = evaluation_pivot(summaries, queries, [strategy], [difficulty])
    if len(frame.columns) < 2:
        return pd.DataFrame(columns=['Metric', 'Score (%)'])
    return frame.rename(columns={'Metric (%)': 'Metric', frame.columns[1]: 'Score (%)'})


def evaluation_difficulty_profile(summaries, queries, strategy, metric):
    difficulties = reporting_difficulties({strategy: queries[strategy]}) + ['All']
    rows = []
    for difficulty in difficulties:
        scores = evaluation_scores(summaries, queries, [strategy], difficulty, metric)
        if not scores.empty:
            rows.append({'Difficulty': difficulty, 'Score (%)': scores.iloc[0]['Score (%)']})
    return pd.DataFrame(rows, columns=['Difficulty', 'Score (%)'])


def evaluation_query_detail(q, strategy, difficulty):
    """Expose saved query fields and the helper's zero-failure criteria, not aggregates."""
    q = difficulty_queries(q, difficulty)
    source = {'query_uid': 'Query UID', 'group': 'Difficulty', 'cs_failed_raw_final': 'CS raw failed cells',
              'cs_total_raw_final': 'CS raw check cells', 'pc_passed_final': 'PC passed', 'pc_total': 'PC total',
              'schema_final': 'Schema passed', 'all_pass_final': 'All-pass'}
    result = q.reindex(columns=list(source)).rename(columns=source)
    result.insert(2, 'Strategy', strategy)
    for field, label in [('cs_failed_raw_final', 'CS raw all-checks pass'), ('pc_failed_final', 'All PC pass')]:
        result[label] = q[field].map(lambda v: None if pd.isna(v) else v == 0) if field in q else None
    return result


def evaluation_definitions():
    rows = [
        ('Commonsense micro*', 'commonsense_constraint.py:evaluate_commonsense_constraints',
         'N×C minus the sum of raw failure-marker cells', 'N queries × C raw matrix columns excluding data_id, including any exception column',
         'Pooled cells: 100 × (1 − raw failure-marker sum / (N×C)); table_eval_exp rounds to 2 decimals',
         'Caught evaluator exceptions add a failure column and can leave other checks unmarked; retain raw convention'),
        ('Commonsense macro', 'commonsense_constraint.py:evaluate_commonsense_constraints',
         'Queries completing CS evaluation with raw failure-row sum zero', 'N evaluated queries',
         '100 × successful CS plans / N; table_eval_exp uses cs_failed_raw_final == 0',
         'A caught CS evaluator exception is not a CS success'),
        ('Logical micro', 'hard_constraint.py:evaluate_hard_constraints_v2',
         'True results of all reference hard_logic_py constraints', 'Total actual hard_logic_py constraints across queries, excluding padding columns',
         'Pooled constraints: 100 × passed constraints / total constraints',
         'DSL exceptions return False; all reference PCs, including named-place constraints, remain in denominator'),
        ('Logical macro', 'hard_constraint.py:evaluate_hard_constraints_v2',
         'Queries passing every reference hard_logic_py constraint', 'N evaluated queries',
         '100 × all-PC-pass queries / N; table_eval_exp uses pc_failed_final == 0',
         'No CS/schema gate for ordinary logical macro; separate conditional metrics are not shown'),
        ('All-pass ratio', 'eval_exp.py:evaluate_final_plans',
         'Query IDs in schema_pass ∩ commonsense_pass ∩ logical_pass', 'N evaluated queries',
         '100 × size of the three-way success intersection / N; table_eval_exp uses saved all_pass_final',
         'Schema rejection or failure in either CS/logical evaluation prevents All-pass; not identical to CS macro'),
    ]
    return pd.DataFrame([{'Metric': metric, 'Source CSV/helper': 'table4_eval_exp.csv / table_eval_exp()',
                          'Evaluator': evaluator, 'Numerator': numerator, 'Denominator': denominator,
                          'Aggregation / percentage conversion': aggregate, 'Missing/error handling': missing}
                         for metric, evaluator, numerator, denominator, aggregate, missing in rows])
