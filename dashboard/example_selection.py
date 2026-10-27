"""Evidence-only narrative selection; no aggregate reporting or experiment mutation."""
import json

import pandas as pd

from dashboard.metrics import family_map, guidance_status, trajectory

TITLES = {
    'cascade': 'Cascading violation / interdependency case — TRAIN',
    'r2': 'R2 protection success — TEST',
    'r3': 'R3 widening success — TEST',
    'r4': 'R4 matrix-guided case — TEST',
    'contrast': 'Contrast / limitation case',
}
EMPTY = 'No qualifying example found in the currently available run.'


def state_view(state):
    """Compact verifier evidence; never dump a full itinerary or log."""
    return {'PC states (1-based order)': state.get('personal_constraints'),
            'CS loop error messages': state.get('commonsense_errors')}


def transitions(row):
    before = row['before'].get('personal_constraints')
    candidate = row['candidate'].get('personal_constraints')
    if not isinstance(before, list) or not isinstance(candidate, list) or len(before) != len(candidate):
        return set(), set()
    return ({i for i, (a, b) in enumerate(zip(before, candidate), 1) if a is False and b is True},
            {i for i, (a, b) in enumerate(zip(before, candidate), 1) if a is True and b is False})


def improved(row):
    """A target fix or reduced CS message count in an accepted proposal."""
    if row['accepted'] is not True:
        return False
    fixed, _ = transitions(row)
    targets = set(row['attempt'].get('target_constraint_indices') or [])
    before, after = row['before'].get('commonsense_errors'), row['after'].get('commonsense_errors')
    return bool(fixed & targets) or (row['phase'] == 'commonsense' and
        isinstance(before, list) and isinstance(after, list) and len(after) < len(before))


def relationships(row):
    meta = row['attempt'].get('repair_metadata') or {}
    cells = []
    for ranked in meta.get('risk_target_ranking') or []:
        for cell in ranked.get('destination_risks') or []:
            cells.append(dict(cell, source_family=ranked.get('family'), destination_family=cell.get('family')))
    for cell in meta.get('commonsense_source_risks') or []:
        cells.append(dict(cell, source_family='commonsense_repair', destination_family=cell.get('family')))
    return cells


def matched_guidance(row, train_matrix):
    """Require the logged support/rate to match the bound TRAIN matrix cell."""
    matches = []
    if train_matrix.empty:
        return matches
    for cell in relationships(row):
        if not isinstance(cell.get('support_count'), (int, float)) or cell['support_count'] <= 0:
            continue
        found = train_matrix[(train_matrix.source_family == cell['source_family']) &
                             (train_matrix.destination_family == cell['destination_family'])]
        for source in found.to_dict('records'):
            rate = source.get('regression_probability', source.get('regression_rate'))
            logged = cell.get('regression_probability')
            if (source.get('support_count') == cell['support_count'] and
                isinstance(rate, (int, float)) and isinstance(logged, (int, float)) and abs(rate - logged) < 1e-9):
                matches.append(cell)
    return matches


def trajectory_rows(rows):
    result = []
    for row in rows:
        fixed, new = transitions(row)
        before_cs, after_cs = row['before'].get('commonsense_errors'), row['candidate'].get('commonsense_errors')
        result.append({'Attempt': row['step'], 'Scope': row['scope'], 'Phase': row['phase'],
                       'Target PC indices': row['attempt'].get('target_constraint_indices') or [],
                       'Target labels': row['attempt'].get('target_constraint_labels') or [],
                       'CS targets': row['attempt'].get('target_commonsense_errors') or [],
                       'Changed?': row['changed_team_definition'] if 'translated_plan' in row['before'] and 'translated_plan' in row['candidate'] else None,
                       'No-progress marker': (row['attempt'].get('decision_reason') or (row['attempt'].get('repair_metadata') or {}).get('decision_reason')) == 'no_progress_unchanged',
                       'Candidate PC fixed': sorted(fixed), 'Candidate PC new violations': sorted(new),
                       'Candidate CS message change': len(after_cs)-len(before_cs) if isinstance(before_cs,list) and isinstance(after_cs,list) else None,
                       'Result': 'Accepted' if row['accepted'] is True else 'Rejected' if row['accepted'] is False else 'Unknown'})
    return result


def find_examples(run, bundles, matrix=None, contributions=None, train_matrix=None, difficulties=None):
    """Return ranked examples from independent checkpoint trials, never merge trials."""
    found = {key: [] for key in TITLES}
    matrix = matrix if matrix is not None else pd.DataFrame()
    contributions = contributions if contributions is not None else pd.DataFrame()
    train_matrix = train_matrix if train_matrix is not None else pd.DataFrame()
    difficulties = difficulties or {}
    for uid, bundle in bundles.items():
        for trial_index, cp in enumerate(bundle.get('checkpoints', [])):
            t = trajectory(cp)
            current_plan = cp.get('initial_raw_plan')
            for index, row in enumerate(t['rounds']):
                attempt = row['attempt']
                fixed, new = transitions(row)
                targets = set(attempt.get('target_constraint_indices') or [])
                families = family_map(attempt.get('constraint_descriptors'))
                meta = attempt.get('repair_metadata') or {}
                retained = (row['accepted'] is False and current_plan is not None and
                            attempt.get('accepted_plan_after') is not None and
                            attempt['accepted_plan_after'] == current_plan)
                selected = bundle.get('selected') or {}
                # A trial's own final state is distinct from the selected cross-trial export.
                posthoc = None
                if selected.get('selected_source') is not None and selected.get('selected_step') is not None:
                    same_source = selected['selected_source'] == cp.get('repair_strategy')
                    if not same_source or selected['selected_step'] != row['step']:
                        posthoc = False
                    else:
                        matching_trials = [trial for trial in bundle.get('trial_identities', bundle.get('checkpoints', [])) if trial.get('repair_strategy') == selected['selected_source']]
                        matrix_id = selected.get('selected_matrix_used')
                        if matrix_id is not None:
                            trial_matrix = cp.get('matrix_used', (cp.get('matrix') or {}).get('matrix_used'))
                            if trial_matrix is not None:
                                posthoc = matrix_id == trial_matrix
                        elif len(matching_trials) == 1:
                            posthoc = True
                base = {'run': run, 'uid': uid, 'difficulty': difficulties.get(uid),
                        'trial': cp.get('repair_strategy'), 'trial_index': trial_index, 'step': row['step'],
                        'row': row, 'sequence': [row], 'families': families, 'retained': retained,
                        'final': cp.get('final_verification') or t['final'],
                        'selected': state_view(selected.get('final_verification') or {}) if selected else None,
                        'selected_source': selected.get('selected_source'), 'selected_step': selected.get('selected_step'),
                        'posthoc': posthoc, 'relationships': [], 'rank': (0,), 'checkpoint': cp.get('matrix_run_id')}
                if run.partition == 'TRAIN' and run.strategy in ('R0','R1','R2','R3') and row['phase'] == 'personal':
                    # Exactly one mapped target family A; B must be a different known family.
                    target_families = {families.get(i) for i in targets}
                    if targets & fixed and len(target_families) == 1 and None not in target_families and 'unmapped' not in target_families:
                        source = next(iter(target_families))
                        affected = sorted({families.get(i) for i in new} - {source, None, 'unmapped'})
                        for destination in affected:
                            rel = matrix[(matrix.source_family == source) & (matrix.destination_family == destination) & (matrix.perspective == 'candidate')] if {'source_family','destination_family','perspective'} <= set(matrix) else pd.DataFrame()
                            contributed = False
                            required = {'query_uid','step','source_family','destination_family','perspective','eligible','regression'}
                            if required <= set(contributions):
                                c = contributions
                                contributed = bool(((c.query_uid == uid) & (c.step == row['step']) & (c.source_family == source) & (c.destination_family == destination) & (c.perspective == 'candidate') & c.eligible.eq(True) & c.regression.eq(True)).any())
                            support = float(rel.support_count.max()) if not rel.empty and pd.notna(rel.support_count.max()) else 0
                            found['cascade'].append(dict(base, relationships=rel.to_dict('records'), source_family=source, destination_family=destination,
                                contributed=contributed, rank=(int(len(targets)==1), int(contributed), support),
                                explanation=f'The targeted {source} PC was fixed in the candidate, while a previously passing {destination} PC failed. This illustrates an observed repair interdependency; it does not establish a causal aggregate effect.'))
                if run.partition == 'TEST' and run.strategy == 'R2':
                    protected = set(attempt.get('protected_constraint_indices') or [])
                    decision = attempt.get('decision_reason') or meta.get('decision_reason')
                    if new & protected and retained and decision == 'previously_satisfied_constraint_regressed':
                        explanation = 'R2 generated a protected-PC regression and rejected the candidate. Logged accepted-plan equality confirms that the previous itinerary was retained.'
                        if targets & fixed:
                            explanation += ' The candidate also fixed a targeted PC.'
                        found['r2'].append(dict(base, protected_regressions=sorted(new & protected), rank=(int(bool(targets & fixed)),len(new & protected)), explanation=explanation))
                if run.partition == 'TEST' and run.strategy == 'R3' and row['scope'] in ('day','plan') and improved(row):
                    earlier = []
                    for prior in t['rounds'][:index]:
                        prior_fixed, _ = transitions(prior)
                        prior_targets = set(prior['attempt'].get('target_constraint_indices') or [])
                        states = prior['before'].get('personal_constraints')
                        unresolved = isinstance(states,list) and any(0 < i <= len(states) and states[i-1] is False for i in prior_targets) and not (prior_fixed & prior_targets)
                        no_progress = prior['attempt'].get('decision_reason') == 'no_progress_unchanged' or (prior['attempt'].get('repair_metadata') or {}).get('decision_reason') == 'no_progress_unchanged'
                        if prior['scope'] == 'slot' and (unresolved or no_progress or prior['accepted'] is False):
                            earlier.append(prior)
                    if earlier:
                        start = t['rounds'].index(earlier[0])
                        found['r3'].append(dict(base, sequence=t['rounds'][start:index+1], rank=(int(bool(fixed & targets)),int(not new),len(earlier),int(row['scope']=='plan')),
                            explanation=f'An earlier slot repair did not resolve its target, was rejected, or logged no progress. R3 later reached {row["scope"]} scope and made an accepted target-PC fix or CS-message reduction. R3 widens on a fixed schedule; this sequence does not establish failure-triggered escalation.'))
                if run.partition == 'TEST' and run.strategy == 'R4':
                    matched = matched_guidance(row, train_matrix)
                    if matched and improved(row):
                        found['r4'].append(dict(base, relationships=matched, rank=(int(posthoc is True),int(not new),int(bool(fixed & targets)),sum(c['support_count'] for c in matched)),
                            explanation='R4 was provided matrix guidance with logged support and rates matching its saved TRAIN matrix. The candidate produced an accepted target-PC fix or CS-message reduction. These logs do not establish that R4 followed the guidance or that the matrix caused the repair.'))
                    status = guidance_status(meta)
                    reasons = []
                    if status != 'supported':
                        reasons.append(status)
                    if meta.get('proposal_rejected_reason'):
                        reasons.append('structural guard: ' + str(meta['proposal_rejected_reason']))
                    if status == 'supported' and (not improved(row) or posthoc is False):
                        reasons.append('supported guidance but no accepted target improvement or candidate not selected post hoc')
                    if reasons:
                        found['contrast'].append(dict(base, relationships=relationships(row), limitation='; '.join(reasons),
                            rank=(int(bool(meta.get('proposal_rejected_reason'))),int(status=='unsupported'),int(posthoc is False)),
                            explanation='R4 contrast: ' + '; '.join(reasons) + '. Guidance availability alone does not establish a useful accepted repair.'))
                if row['accepted'] is True:
                    current_plan = attempt.get('accepted_plan_after')
    for key in found:
        found[key].sort(key=lambda e: (e['rank'], e['uid'], str(e['trial']), -e['step']), reverse=True)
    return found


def trajectory_markdown(rows):
    records = trajectory_rows(rows)
    columns = ['Attempt', 'Scope', 'Phase', 'Target PC indices', 'Target labels', 'CS targets', 'Changed?',
               'No-progress marker', 'Candidate PC fixed', 'Candidate PC new violations',
               'Candidate CS message change', 'Result']
    def cell(value):
        return ('Unavailable' if value is None else str(value)).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(columns) + ' |', '| ' + ' | '.join(['---'] * len(columns)) + ' |'] +
                     ['| ' + ' | '.join(cell(row[c]) for c in columns) + ' |' for row in records])


def markdown(example, category):
    row, run = example['row'], example['run']
    attempt = row['attempt']
    details = {'Strategy / partition': f'{run.strategy} / {run.partition}', 'Run ID': run.run_id,
               'Source run': run.path, 'Query UID': example['uid'], 'Difficulty': example['difficulty'],
               'Trial': example['trial'], 'Checkpoint identity': example['checkpoint'], 'Round / attempt': row['step'],
               'Repair phase': row['phase'], 'Target PCs': attempt.get('target_constraint_indices'),
               'Target labels': attempt.get('target_constraint_labels'),
               'Target constraint expressions': {d.get('constraint_index'): d.get('hard_logic_py') for d in attempt.get('constraint_descriptors') or [] if d.get('constraint_index') in (attempt.get('target_constraint_indices') or [])},
               'New violation constraint expressions': {d.get('constraint_index'): d.get('hard_logic_py') for d in attempt.get('constraint_descriptors') or [] if d.get('constraint_index') in transitions(row)[1]}, 'CS targets': attempt.get('target_commonsense_errors'),
               'PC family mapping': example['families'], 'Protected PCs': attempt.get('protected_constraint_indices'),
               'Target PCs fixed': sorted(transitions(row)[0] & set(attempt.get('target_constraint_indices') or [])),
               'Candidate new PC violations': sorted(transitions(row)[1]),
               'Acceptance decision': row['accepted'], 'Decision reason': attempt.get('decision_reason') or (attempt.get('repair_metadata') or {}).get('decision_reason')}
    if category == 'cascade':
        details.update({'Matrix relationship': f'{example["source_family"]} → {example["destination_family"]}', 'Saved TRAIN contribution': example['contributed']})
    if category == 'r2':
        details.update({'Protected regressions': example['protected_regressions'], 'Prior accepted plan retained': example['retained']})
    if category in ('r4','contrast'):
        details.update({'Guidance status': guidance_status(attempt.get('repair_metadata') or {}),
                        'Post-hoc candidate selected': example['posthoc'], 'Post-hoc selected source': example['selected_source'],
                        'Post-hoc selected step': example['selected_step']})
    text = [f'# {TITLES[category]}', '', 'Selected representative example', '']
    text.extend(f'- {key}: {json.dumps(value, ensure_ascii=False, default=str) if value is not None else "Unavailable"}' for key,value in details.items())
    text += ['', '## Short trajectory', '', trajectory_markdown(example['sequence']), '', '## Key verifier states', '']
    for label, state in [('Accepted before proposal',row['before']),('Candidate',row['candidate']),('Accepted after decision',row['after'])]:
        text += [f'- {label}: {json.dumps(state_view(state), ensure_ascii=False)}']
    if category in ('r4','contrast'):
        text += [f'- Final loop accepted state: {json.dumps(state_view(example["final"]), ensure_ascii=False)}',
                 f'- Post-hoc selected outcome (separate): {json.dumps(example["selected"], ensure_ascii=False)}',
                 '- TEST benchmark reporting uses the final accepted trial trajectory, not the post-hoc selection.']
    text += ['', '## Matrix evidence', '', json.dumps(example['relationships'], ensure_ascii=False, default=str), '', '## Why this example matters', '', example['explanation']]
    return '\n'.join(text)
