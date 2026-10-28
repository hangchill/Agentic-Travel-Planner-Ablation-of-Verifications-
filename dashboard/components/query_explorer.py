"""Read-only query walkthrough over the dashboard's established evidence model."""
from pathlib import Path

import pandas as pd
import streamlit as st
from dashboard import data_loader as data
from dashboard.metrics import guidance_status, guidance_support, family_map, state_counts
from dashboard.query_presentation import (presentation_trajectory, visible_rounds, attempt_label,
                                          message_delta, constraint_history, json_evidence, safe_evidence)
from dashboard.utils import compact_verification, itinerary_rows, present
from dashboard.components.common import table, cards, freshness
from dashboard.components import itinerary_cards as itinerary


def state(label, verification):
    st.markdown(f'**{label}**')
    cards(state_counts(verification))
    with st.expander(f'{label}: failed constraints and verification details'):
        st.json(safe_evidence(compact_verification(verification)), expanded=False)


def _download(label, value, filename, key):
    st.download_button(label, json_evidence(value), file_name=filename, mime='application/json', key=key)


def _move(key, value):
    st.session_state[key] = value


def navigation(rows, key):
    """Widget ordinals navigate records; displayed step IDs come from artifacts."""
    choices = [-1] + [r['ordinal'] for r in rows]
    labels = {-1: 'Initial', **{r['ordinal']: attempt_label(r) for r in rows}}
    if st.session_state.get(key) not in choices:
        st.session_state[key] = -1
    current = st.session_state[key]
    # Wrap long trajectories into compact strips rather than a very wide row.
    for start in range(0, len(choices), 7):
        chunk = choices[start:start + 7]
        for col, value in zip(st.columns(len(chunk)), chunk):
            col.button(labels[value], key=f'{key}_jump_{value}',
                       type='primary' if current == value else 'secondary',
                       on_click=_move, args=(key, value), use_container_width=True)
    prev, _, nxt = st.columns([1, 3, 1])
    pos = choices.index(current)
    prev.button('← Previous', key=f'{key}_previous', disabled=pos == 0,
                on_click=_move, args=(key, choices[max(0, pos - 1)]))
    nxt.button('Next →', key=f'{key}_next', disabled=pos == len(choices) - 1,
               on_click=_move, args=(key, choices[min(len(choices) - 1, pos + 1)]))
    return next((r for r in rows if r['ordinal'] == current), None)


def attempt_details(run, cp, r, key):
    a = r['attempt']; meta = a.get('repair_metadata') or {}
    decision = 'Accepted' if r['accepted'] is True else 'Rejected' if r['accepted'] is False else 'Unavailable'
    st.subheader(f"{attempt_label(r)} · {decision}")
    if r['accepted'] is False:
        st.error('Rejected candidate — inspect the candidate separately from the accepted plan.')
    reason = a.get('decision_reason') or meta.get('decision_reason')
    families = family_map(a.get('constraint_descriptors'))
    summary = {'Recorded step': r['step'], 'Repair phase': r['phase'], 'Actual scope': r['scope'],
               'Target PC indices': a.get('target_constraint_indices'), 'Target PC labels': a.get('target_constraint_labels'),
               'Target families': [families.get(i, 'unmapped') for i in a.get('target_constraint_indices') or []],
               'Target CS messages': a.get('target_commonsense_errors'), 'Decision reason': reason,
               'Changed (team definition)': r['changed_team_definition'],
               'No-progress (explicit marker)': True if reason == 'no_progress_unchanged' else None,
               'Candidate PC fixes': a.get('fixed'), 'Candidate PC regressions': a.get('newly_violated'),
               'Tokens': r['tokens'], 'Repair time (s)': r['repair time (s)']}
    st.write({k: present(v) for k, v in summary.items()})
    diff = itinerary.align_diff(r['before_plan'], r['candidate_plan'])
    delta = message_delta(r['before'], r['candidate'])
    cards({'Candidate PC fixes': len(a['fixed']) if isinstance(a.get('fixed'), list) else None,
           'New candidate PC regressions': len(a['newly_violated']) if isinstance(a.get('newly_violated'), list) else None,
           'Candidate CS messages introduced': len(delta['introduced messages']) if delta['introduced messages'] is not None else None,
           'Changed activities (aligned raw diff)': diff['changed activities']})
    st.caption('PC cards use recorded candidate transitions. CS changes are saved message-set diagnostics, not resolved benchmark checks. Raw field differences do not redefine the team changed metric.')
    st.write({k: present(v) for k, v in delta.items()})
    if run.strategy == 'R2':
        st.markdown('**R2 protection and preserved accepted plan**')
        st.write({'Protected PCs': present(a.get('protected_constraint_indices', meta.get('protected_constraint_indices'))),
                  'Candidate regressions': present(a.get('newly_violated')),
                  'Rejection reason': present(reason),
                  'Logged rollback indices': present(meta.get('rolled_back_constraint_indices')),
                  'Previous accepted raw plan retained': present(r['retention']) if r['accepted'] is False else 'Not a rejected attempt'})
        st.caption('Retention compares recorded raw plans after an explicit rejection; equality alone does not establish rollback.')
    if run.strategy == 'R3':
        st.write({'Actual editable scope': present(r['scope']),
                  'Recorded escalation': present(a.get('escalation_reason', meta.get('escalation_reason')))})
        st.caption('Scope uses scheduled widening semantics. Failure-triggered widening is not inferred.')
    if run.strategy == 'R4':
        guard = meta.get('proposal_rejected_reason')
        st.markdown('**R4 guidance, structural guard and loop decision**')
        st.write({'Logged relationship status': guidance_status(meta), 'Support': guidance_support(meta),
                  'Matrix guidance policy': present(meta.get('matrix_guidance_policy')),
                  'Matrix path': present(meta.get('risk_matrix_path')), 'Matrix used': present(meta.get('matrix_used')),
                  'Structural guard status': ('Rejection recorded' if guard else 'No rejection recorded')
                      if 'proposal_rejected_reason' in meta else 'Unavailable',
                  'Structural rejection reason': present(guard), 'Parse failed': present(meta.get('parse_failed')),
                  'Candidate PC fixes': present(a.get('fixed')), 'Candidate regressions': present(a.get('newly_violated')),
                  'Loop acceptance': decision})
        st.caption('Missing guard status is unavailable. Logged guidance does not prove the model followed it. Post-hoc selection is shown separately below.')
        with st.expander('Recorded guidance and relationship evidence'):
            st.json(safe_evidence({k: v for k, v in meta.items() if k in (
                'matrix_guidance_policy', 'neutral_risk_fallback', 'risk_target_ranking', 'commonsense_source_risks',
                'recommended_risk_target', 'risk_matrix_sha256', 'risk_matrix_path', 'matrix_used', 'matrix')}), expanded=False)
    tabs = st.tabs(['Before', 'Candidate', 'Accepted after', 'What changed?'])
    # Editable locations refer to the repair INPUT, not guessed candidate positions.
    focus_options = itinerary.recorded_focus(r['before_plan'], meta)
    with tabs[0]:
        focus = None
        if focus_options:
            selected = st.selectbox('Focus recorded editable location in Before', ['None'] + list(focus_options), key=f'{key}_focus')
            focus = focus_options.get(selected)
        state('Before', r['before']); itinerary.render(r['before_plan'], 'Before itinerary', focus)
    with tabs[1]:
        state('Candidate', r['candidate']); itinerary.render(r['candidate_plan'], 'Candidate itinerary')
    with tabs[2]:
        state('Accepted after', r['after']); itinerary.render(r['after_plan'], 'Accepted after itinerary')
    with tabs[3]:
        comparison = st.radio('Field comparison', ['Before → Candidate', 'Before → Accepted after'], key=f'{key}_diff', horizontal=True)
        shown = diff if comparison.endswith('Candidate') else itinerary.align_diff(r['before_plan'], r['after_plan'])
        st.caption(shown['status'])
        st.caption('Matched using recorded IDs or unique place/route identities. Unmatched activities are not paired by position.')
        table(itinerary.diff_frame(shown), 'Selected attempt field diff')
    with st.expander('Cost / process details'):
        fields = ('input_tokens_delta', 'output_tokens_delta', 'total_tokens_delta', 'repair_time_seconds',
                  'attempt_time_seconds', 'verification_time_seconds', 'model_calls', 'repair_model_calls',
                  'verification_model_calls', 'failed_model_calls', 'verification_count', 'tool_call_count', 'exception')
        st.write({k: present(a.get(k)) for k in fields})
        st.write({'Failure reason': present(meta.get('failure_reason'))})
    with st.expander('Raw evidence · selected attempt'):
        st.json(safe_evidence({'attempt': a, 'before verification': r['before'], 'candidate verification': r['candidate'],
                               'accepted after verification': r['after']}), expanded=False)
    export = {'run_id': run.run_id, 'partition': run.partition, 'strategy': run.strategy,
              'query_uid': cp.get('query_uid'), 'trial': cp.get('matrix_run_id'), 'step': r['step'],
              'record': r['ordinal'], 'attempt': a}
    _download('Download selected attempt JSON', export, 'selected_attempt.json', f'{key}_attempt_download')
    _download('Download field diff JSON', dict(export, comparison=comparison, field_diff=shown),
              'field_diff.json', f'{key}_diff_download')
    _download('Download Before/Candidate/Accepted JSON', dict(export, states={
        'Before': {'plan': r['before_plan'], 'verification': r['before']},
        'Candidate': {'plan': r['candidate_plan'], 'verification': r['candidate']},
        'Accepted after': {'plan': r['after_plan'], 'verification': r['after']}}), 'state_comparison.json', f'{key}_states_download')


def render(run, uid, filters):
    st.markdown(itinerary.CSS, unsafe_allow_html=True)
    bundle = data.query_artifacts(run, uid)
    cps = bundle['checkpoints']
    if not cps:
        st.info('Checkpoint unavailable. The logged proposal evidence, if any, remains available on Strategy-Specific.')
        return
    paths = bundle.get('checkpoint_paths', [])
    trial_key = f'query_trial_{run.path}_{uid}'
    index = st.selectbox('Independent trial', range(len(cps)), key=trial_key,
                         format_func=lambda i: f"{cps[i].get('matrix_run_id') or cps[i].get('repair_strategy', 'trial')} · {Path(paths[i]).name if i < len(paths) else f'record {i + 1}'}")
    cp = cps[index]
    t = presentation_trajectory(cp)
    key = f'query_walk_{run.path}_{uid}_{index}'
    q = data.test_table(run, 'per_query')
    reporting = q[q.query_uid == uid] if not q.empty else q
    difficulty = reporting.iloc[0].get('group') if not reporting.empty else None
    reference = bundle.get('reference') or cp.get('reference_query') or {}
    st.subheader('Query summary')
    st.write({'Query UID': uid, 'Partition': run.partition, 'Strategy': run.strategy, 'Difficulty': present(difficulty),
              'Run': run.run_id, 'Independent trial': cp.get('matrix_run_id') or (paths[index] if index < len(paths) else index),
              'Repair attempts recorded': len(t['rounds'])})
    request = reference.get('nature_language_en') or reference.get('nature_language')
    if request:
        st.markdown('**Original user request**'); st.write(request)
    else:
        st.caption('Original user request: Unavailable.')
    state('Initial state — loop verifier', t['initial'])
    state('Final accepted trial state', cp.get('final_verification') or t['final'])
    st.caption('CS here counts loop error messages; benchmark CS check pass rates are on TEST set. Rejected candidates never advance the accepted trajectory.')
    rounds = visible_rounds(t['rounds'], uid, cp.get('repair_strategy'), filters)
    st.subheader('Repair trajectory')
    selected = navigation(rounds, key)
    if not rounds:
        st.info('No repair attempts match the current filters; initial and final endpoints remain available.')
    if run.strategy == 'R3':
        table(pd.DataFrame([{'Attempt': attempt_label(r), 'Scope': r['scope'],
                             'Decision': 'Accepted' if r['accepted'] is True else 'Rejected' if r['accepted'] is False else 'Unavailable',
                             'Changed (team definition)': r['changed_team_definition'],
                             'Escalation': r['attempt'].get('escalation_reason')} for r in rounds]), 'R3 scope trajectory')
        st.caption('Recorded scope sequence; scheduled widening, not inferred failure-triggered widening.')
    if selected is None:
        itinerary.render(t['initial_plan'], 'Initial itinerary')
    else:
        attempt_details(run, cp, selected, f"{key}_{selected['ordinal']}")
    with st.expander('Constraint history'):
        pc, cs = constraint_history(t)
        st.caption('Candidate states by recorded attempt; final accepted state is separate. Full trial history is retained when navigation is filtered.')
        table(pd.DataFrame(pc), 'PC constraint history')
        st.caption('Loop CS saved message evidence — no persistent check IDs or benchmark CS scores are inferred.')
        table(pd.DataFrame(cs), 'Loop CS message history')
    st.subheader('Final accepted loop plan')
    itinerary.render(t['final_plan'], 'Final accepted itinerary')
    rows = itinerary_rows(t['final_plan'])
    if rows:
        with st.expander('Final accepted itinerary table'):
            table(pd.DataFrame(rows), 'Final accepted itinerary')
    if t['final_plan'] is not None:
        _download('Download final itinerary', t['final_plan'], f'{uid}_plan.json', f'{key}_final_download')
    outcome = bundle['selected']
    if outcome:
        st.subheader('Post-hoc selected outcome — separate from TEST reporting')
        st.write({k: present(outcome.get(k)) for k in ('selected_source', 'selected_step', 'selection_score', 'selection_rule', 'selected_matrix_used')})
        state('Post-hoc selected state', outcome.get('final_verification') or {})
        itinerary.render(outcome.get('final_accepted_plan'), 'Post-hoc selected itinerary')
    st.subheader('Benchmark reporting — separate from loop diagnostics')
    table(reporting, 'Query benchmark reporting outcome')
    if q.empty:
        st.caption('Raw persisted benchmark rows — reporting tables are not generated for this run.')
        for name, frame in data.benchmark_query(run, uid).items():
            table(frame, f'Query raw benchmark {name}')
    with st.expander('Raw evidence · source checkpoint'):
        st.caption('Saved checkpoint; credential/environment fields are redacted.')
        st.json(safe_evidence(cp), expanded=False)
        _download('Download source checkpoint JSON', cp, 'checkpoint.json', f'{key}_checkpoint_download')
    with st.expander('Provenance'):
        st.write({'partition': run.partition, 'run path': run.path, 'run ID': run.run_id,
                  'strategy': run.strategy, 'query UID': uid,
                  'trial identity': cp.get('matrix_run_id'),
                  'source checkpoint': paths[index] if index < len(paths) else 'Unavailable',
                  'attempt source': 'repair_history[].repair_attempt in selected checkpoint',
                  'generation timestamp': present(cp.get('generation_timestamp') or cp.get('created_at'))})
        freshness(run)
