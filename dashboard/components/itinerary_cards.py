"""Generic activity cards and conservative raw-plan alignment.

Reuse only pure formatting helpers from frontend.presentation; no replay fixture,
planner, history discovery, curated mappings or metrics are imported.
"""
from collections import Counter
from html import escape
import json

import pandas as pd
import streamlit as st

from frontend.presentation import activity_title, format_money, transport_description
from dashboard.query_presentation import raw_plan, safe_evidence


CSS = '''<style>
.qe-activity {border:1px solid #bbc6c8;border-left:4px solid #648d83;border-radius:9px;padding:14px;margin:9px 0;overflow-wrap:anywhere;}
.qe-activity.qe-focus {outline:3px solid #d79531;outline-offset:2px;}
.qe-activity .qe-muted {opacity:.75;font-size:.86rem;margin:5px 0;}
.qe-activity .qe-title {font-weight:650;}
</style>'''


def days(plan):
    value = raw_plan(plan)
    return value if value is not None else []


def _identity(activity):
    for key in ('activity_id', 'slot_id', 'id', 'slot'):
        if activity.get(key) is not None:
            return (key, str(activity[key]))
    return None


def _anchor(activity):
    keys = ('type', 'position', 'TrainID', 'FlightID', 'start', 'end')
    if not any(activity.get(k) for k in keys[1:]):
        return None
    return tuple(str(activity.get(k, '')) for k in keys)


def _flatten(value, prefix=''):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            result.update(_flatten(item, f'{prefix}.{key}' if prefix else str(key)))
        return result
    return {prefix: value}


def _fields(left, right):
    a, b = _flatten(left), _flatten(right)
    return [(k, a.get(k), b.get(k)) for k in sorted(a.keys() | b.keys())
            if (k in a) != (k in b) or a.get(k) != b.get(k)]


def align_diff(before, after):
    """Pair unique stable IDs, then unique unchanged place/route identities.

    No positional pairing. A changed venue without a stable ID stays unmatched.
    Duplicate or absent identities never produce an invented field transition.
    """
    left, right = raw_plan(before), raw_plan(after)
    if left is None or right is None:
        return {'status': 'Unavailable: plan not recorded', 'changes': [], 'changed activities': None}
    rows, changed = [], set()
    complete = True
    def day_key(day, count):
        return str(day['day']) if day.get('day') is not None else 'single day' if count == 1 else None
    lk, rk = [day_key(d, len(left)) for d in left], [day_key(d, len(right)) for d in right]
    if None in lk + rk or len(set(lk)) != len(lk) or len(set(rk)) != len(rk):
        return {'status': 'Unavailable: ambiguous day identity', 'changes': [], 'changed activities': None}
    for day in dict.fromkeys(lk + rk):
        a = left[lk.index(day)].get('activities', []) if day in lk else []
        b = right[rk.index(day)].get('activities', []) if day in rk else []
        if not isinstance(a, list) or not isinstance(b, list) or any(not isinstance(x, dict) for x in a + b):
            complete = False
            continue
        ai, bi = [_identity(x) for x in a], [_identity(x) for x in b]
        ac, bc = Counter(ai), Counter(bi)
        pairs, used_a, used_b = [], set(), set()
        for i, ident in enumerate(ai):
            if ident is not None and ac[ident] == bc[ident] == 1:
                j = bi.index(ident)
                pairs.append((i, j, 'recorded activity/slot ID')); used_a.add(i); used_b.add(j)
        aa, ba = [_anchor(x) for x in a], [_anchor(x) for x in b]
        for i, anchor in enumerate(aa):
            if i in used_a or ai[i] is not None or anchor is None:
                continue
            if aa.count(anchor) == ba.count(anchor) == 1:
                j = ba.index(anchor)
                if j not in used_b and bi[j] is None:
                    pairs.append((i, j, 'unique place/route identity')); used_a.add(i); used_b.add(j)
        for i, j, basis in pairs:
            fields = _fields(a[i], b[j])
            if i != j:
                fields.append(('activity order (1-based)', i + 1, j + 1))
            for field, old, new in fields:
                rows.append({'Day': day, 'Activity': activity_title(b[j]), 'Alignment': basis,
                             'Field': field, 'Before': old, 'After': new})
                changed.add((day, i, j))
        stable = all(x is not None and ac[x] == 1 for x in ai) and all(x is not None and bc[x] == 1 for x in bi)
        for side, values, used in [('before', a, used_a), ('after', b, used_b)]:
            for i, activity in enumerate(values):
                if i in used:
                    continue
                complete &= stable
                field = ('Removed activity' if side == 'before' else 'Added activity') if stable else f'Unmatched {side} activity (alignment unavailable)'
                rows.append({'Day': day, 'Activity': activity_title(activity), 'Alignment': 'recorded ID' if stable else 'Unavailable',
                             'Field': field, 'Before': activity if side == 'before' else None,
                             'After': activity if side == 'after' else None})
                changed.add((day, side, i))
    return {'status': 'Aligned' if complete else 'Partial: unmatched activities; no positional pairing',
            'changes': rows, 'changed activities': len(changed) if complete else None}


def recorded_focus(plan, metadata):
    """Only explicit zero-based editable slot records with known artifact keys."""
    choices = {}
    for slot in metadata.get('editable_slots') or []:
        if not isinstance(slot, dict):
            continue
        day, activity = slot.get('day'), slot.get('activity_index')
        if (type(day) is int and type(activity) is int and 0 <= day < len(days(plan))
                and isinstance(days(plan)[day].get('activities'), list)
                and 0 <= activity < len(days(plan)[day]['activities'])):
            choices[f'Recorded editable location: day index {day}, activity index {activity}'] = (day, activity)
    return choices


def render(plan, label, focus=None):
    st.markdown(f'**{label}**')
    value = raw_plan(plan)
    if value is None:
        st.info('Itinerary unavailable — no recorded plan for this state.')
        return
    if not value:
        st.caption('Recorded itinerary is empty.')
    for di, day in enumerate(value):
        if not isinstance(day, dict):
            st.caption('Day structure unavailable.')
            continue
        with st.expander(f"Day {day.get('day', di + 1)} · {label}", expanded=len(value) <= 2):
            for si, activity in enumerate(day.get('activities') or []):
                if not isinstance(activity, dict):
                    st.caption('Activity structure unavailable.'); continue
                e = lambda x: escape(str(x))
                timing = ' – '.join(str(activity.get(k) or '?') for k in ('start_time', 'end_time'))
                money = format_money(activity.get('cost'))
                transfer = transport_description(activity.get('transports'))
                body = f'<div class="qe-activity{" qe-focus" if focus == (di, si) else ""}"><div class="qe-muted">{e(timing)} · Activity {si + 1}</div>'
                body += f'<div class="qe-title">{e(activity_title(activity))}</div>'
                if money:
                    body += f'<div>{e(money)}</div>'
                if transfer:
                    body += f'<div class="qe-muted">Inbound transfer: {e(transfer)}</div>'
                for key in ('type', 'duration', 'location', 'notes', 'details'):
                    if activity.get(key) is not None:
                        body += f'<div class="qe-muted">{e(key.title())}: {e(activity[key])}</div>'
                st.markdown(body + '</div>', unsafe_allow_html=True)
                with st.expander(f'Recorded activity fields · {label} · day {di + 1} · activity {si + 1}'):
                    st.json(safe_evidence(activity), expanded=False)


def diff_frame(diff):
    rows = []
    for row in safe_evidence(diff['changes']):
        rows.append({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else
                     'Not recorded' if v is None else str(v) for k, v in row.items()})
    return pd.DataFrame(rows)
