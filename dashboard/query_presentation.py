"""Read-only presentation adapters; numerical trajectory definitions stay in metrics.

Raw plans are never replaced with translated plans. Missing accepted artifacts stay
unknown; verification state advancement is delegated to the existing trajectory.
"""
import json

from dashboard.metrics import trajectory, family_map


def raw_plan(value):
    if isinstance(value, list):
        return value if all(isinstance(day, dict) for day in value) else None
    if isinstance(value, dict) and isinstance(value.get('itinerary'), list):
        return raw_plan(value['itinerary'])
    return None


def same_plan(left, right):
    a, b = raw_plan(left), raw_plan(right)
    return left == right if a is not None and b is not None else None


def presentation_trajectory(cp):
    """Attach recorded raw plans to established verification trajectory rows."""
    t = trajectory(cp)
    history = cp.get('repair_history') or []
    current = cp.get('initial_raw_plan')
    rows = []
    for ordinal, (entry, r) in enumerate(zip(history[1:], t['rounds']), 1):
        a = r['attempt']
        candidate = entry.get('candidate_plan', a.get('candidate_plan'))
        # Do not fall back to the last candidate when an accepted plan is absent.
        if 'accepted_plan_after' in a:
            after = a['accepted_plan_after']
        elif entry.get('accepted') is True:
            after = candidate
        elif entry.get('accepted') is False:
            after = current
        else:
            after = None
        rows.append(dict(r, step=entry.get('step', a.get('step')), ordinal=ordinal,
                         before_plan=current, candidate_plan=candidate, after_plan=after,
                         retention=same_plan(current, a.get('accepted_plan_after'))
                         if 'accepted_plan_after' in a else None))
        current = after
    return dict(t, rounds=rows, initial_plan=cp.get('initial_raw_plan'),
                final_plan=cp.get('final_accepted_plan'))


def visible_rounds(rows, uid, trial, filters):
    out = []
    for r in rows:
        allowed = filters.get('allowed_steps')
        if allowed is not None and (uid, r['step'], trial) not in allowed:
            continue
        if filters.get('round', 'All') != 'All' and str(r['step']) != str(filters['round']):
            continue
        if filters.get('phase', 'All') != 'All' and r['phase'] != filters['phase'].lower():
            continue
        out.append(r)
    return out


def attempt_label(r):
    return f"Attempt {r['step']}" if r['step'] is not None else f"Attempt (step unavailable; record {r['ordinal']})"


def message_delta(before, candidate):
    left, right = before.get('commonsense_errors'), candidate.get('commonsense_errors')
    if not isinstance(left, list) or not isinstance(right, list):
        return {'removed messages': None, 'introduced messages': None}
    return {'removed messages': sorted(set(left) - set(right)),
            'introduced messages': sorted(set(right) - set(left))}


def constraint_history(t):
    states = [('Initial', t['initial'])] + [
        (f"{attempt_label(r)} · record {r['ordinal']} (candidate)", r['candidate']) for r in t['rounds']]
    states.append(('Final accepted', t['final']))
    descriptors = {}
    for r in t['rounds']:
        for d in r['attempt'].get('constraint_descriptors') or []:
            descriptors[d.get('constraint_index')] = d
    count = max((len(v.get('personal_constraints', [])) for _, v in states
                 if isinstance(v.get('personal_constraints'), list)), default=0)
    pc = []
    for i in range(count):
        d = descriptors.get(i + 1, {})
        row = {'Constraint': d.get('hard_logic_nl') or d.get('label') or f'PC {i + 1}',
               'Family': family_map([d]).get(i + 1, 'unmapped') if d else 'unmapped'}
        for label, v in states:
            vector = v.get('personal_constraints')
            value = vector[i] if isinstance(vector, list) and i < len(vector) else None
            row[label] = 'True' if value is True else 'False' if value is False else 'Unknown'
        pc.append(row)
    cs = [{'State': label, 'Loop CS message count': len(v['commonsense_errors'])
           if isinstance(v.get('commonsense_errors'), list) else None,
           'Saved messages': v.get('commonsense_errors')} for label, v in states]
    return pc, cs


def safe_evidence(value):
    """Redact credential fields in downloadable and displayed raw evidence."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = str(key).lower().replace('-', '_')
            secret = any(s in name for s in ('api_key', 'apikey', 'secret', 'password', 'authorization', 'access_token', 'refresh_token'))
            result[key] = '[redacted]' if secret or name in ('env', 'environment', 'credentials') else safe_evidence(item)
        return result
    if isinstance(value, list):
        return [safe_evidence(x) for x in value]
    return value


def json_evidence(value):
    return json.dumps(safe_evidence(value), ensure_ascii=False, indent=2, default=str)
