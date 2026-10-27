import pandas as pd
import streamlit as st
from dashboard import data_loader as data
from dashboard.metrics import trajectory, guidance_status, guidance_support, family_map, state_counts
from dashboard.utils import compact_verification, itinerary_rows
from dashboard.components.common import table, cards


def state(label, verification):
    st.markdown(f'**{label}**')
    cards(state_counts(verification))
    with st.expander(f'{label}: failed constraints and verification details'):
        st.json(compact_verification(verification), expanded=1)


def render(run, uid, filters):
    bundle = data.query_artifacts(run, uid)
    cps = bundle['checkpoints']
    if not cps:
        st.info('Checkpoint unavailable. The logged proposal evidence, if any, remains available on Strategy-Specific.')
        return
    cp = cps[0]
    if len(cps) > 1:
        index = st.selectbox('Independent trial', range(len(cps)),
                             format_func=lambda i: cps[i].get('repair_strategy', str(i)))
        cp = cps[index]
    t = trajectory(cp)
    state('Initial state — loop verifier', t['initial'])
    st.caption('CS here counts loop error messages; benchmark CS check pass rates are on TEST set. Rejected candidates never advance the accepted trajectory.')
    for r in t['rounds']:
        attempt = r['attempt']
        allowed = filters.get('allowed_steps')
        if allowed is not None and (uid, r['step'], cp.get('repair_strategy')) not in allowed:
            continue
        if filters['round'] != 'All' and r['step'] != int(filters['round']):
            continue
        if filters['phase'] != 'All' and r['phase'] != filters['phase'].lower():
            continue
        with st.expander(f'Round {r["step"]} · {r["phase"]} · {r["scope"]} · {"Accepted" if r["accepted"] else "Rejected"}'):
            meta = attempt.get('repair_metadata') or {}
            st.write({'target indices': attempt.get('target_constraint_indices'),
                      'target labels': attempt.get('target_constraint_labels'),
                      'target families': [family_map(attempt.get('constraint_descriptors')).get(i, 'unmapped') for i in attempt.get('target_constraint_indices', [])],
                      'CS targets': attempt.get('target_commonsense_errors'),
                      'candidate fixed indices': attempt.get('fixed'),
                      'candidate new violations': attempt.get('newly_violated'),
                      'failure reason': meta.get('failure_reason'),
                      'decision reason': attempt.get('decision_reason') or meta.get('decision_reason'),
                      'changed (team definition)': r['changed_team_definition'],
                      'tokens': r['tokens'], 'repair time (s)': r['repair time (s)']})
            cols = st.columns(3)
            for col, label, v in zip(cols, ['Before', 'Candidate', 'Accepted after'], [r['before'], r['candidate'], r['after']]):
                with col:
                    state(label, v)
            if run.strategy == 'R4':
                st.write({'matrix guidance': guidance_status(meta), 'support': guidance_support(meta),
                          'structural guard': meta.get('proposal_rejected_reason'),
                          'matrix path': meta.get('risk_matrix_path'),
                          'post-hoc selected round': (bundle['selected'].get('selected_step') == r['step']
                              and bundle['selected'].get('selected_source') == cp.get('repair_strategy'))})
            compact = {k: v for k, v in meta.items() if k in (
                'editable_slots', 'failure_reason', 'decision_reason', 'protected_constraint_indices',
                'rolled_back_constraint_indices', 'escalation_reason', 'risk_target_ranking',
                'commonsense_source_risks', 'proposal_rejected_reason', 'parse_failed')}
            if compact:
                with st.expander('Strategy metadata'):
                    st.json(compact, expanded=1)
    state('Final accepted trial state', cp.get('final_verification') or t['final'])
    plan = cp.get('final_accepted_plan')
    rows = itinerary_rows(plan)
    if rows:
        table(pd.DataFrame(rows), 'Final accepted itinerary')
    elif plan is not None:
        st.download_button('Download final itinerary', __import__('json').dumps(plan, ensure_ascii=False, indent=2), file_name=f'{uid}_plan.json')
    selected = bundle['selected']
    if selected:
        st.subheader('Post-hoc selected outcome — separate from TEST reporting')
        st.write({k: selected.get(k) for k in ('selected_source', 'selected_step', 'selection_score', 'selection_rule')})
        state('Post-hoc selected state', selected.get('final_verification') or {})
    q = data.test_table(run, 'per_query')
    table(q[q.query_uid == uid] if not q.empty else q, 'Query benchmark reporting outcome')

    if q.empty:
        st.caption('Raw persisted benchmark rows — reporting tables are not generated for this run.')
        for name, frame in data.benchmark_query(run, uid).items():
            table(frame, f'Query raw benchmark {name}')
