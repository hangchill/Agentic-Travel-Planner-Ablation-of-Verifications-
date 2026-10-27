"""Read-only R4 artifact adapter and descriptive diagnostics.

Does not import R4 runtime/selection/build functions. Logged recommendations are
not inferred model decisions; saved selected outcomes are not trial endpoints.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def load_artifacts(root):
    root = Path(root)
    data = {'metadata': {}, 'selections': [], 'queries': {}, 'trials': []}
    for filename, key in [('r4_run_metadata.json', 'metadata'),
                          ('r4_selection_and_costs.json', 'selections')]:
        if (root/filename).exists():
            data[key] = read(root/filename)
    selections = data['selections']
    if not isinstance(selections, list):
        raise ValueError('R4 selections must be a list of per-query rows')
    if len({r['query_uid'] for r in selections}) != len(selections):
        raise ValueError('Duplicate R4 selection query')
    for qdir in sorted((root/'queries').glob('*')):
        if not qdir.is_dir():
            continue
        exports = {}
        for name in ['final_state', 'repair_history', 'final_itinerary', 'computational_cost']:
            if (qdir/(name+'.json')).exists():
                exports[name] = read(qdir/(name+'.json'))
        trials = []
        for path in sorted([*qdir.glob('R4*.json'), *(qdir/'trials').glob('*.json')]):
            trial = read(path)
            if not isinstance(trial.get('repair_history'), list):
                continue
            trial['_artifact_path'] = str(path.relative_to(root))
            trials.append(trial)
        if len({t['repair_strategy'] for t in trials}) != len(trials):
            raise ValueError('Duplicate R4 trial identity')
        uid = next((v.get('query_uid') for v in exports.values() if isinstance(v, dict) and v.get('query_uid')), None)
        uid = uid or next((t.get('query_uid') for t in trials), None)
        if uid:
            data['queries'][uid] = exports
        data['trials'].extend(trials)
    return data


def partition(manifest, metadata=None):
    metadata = metadata or {}
    split = manifest.get('split_query_source') or metadata.get('split')
    explicit = metadata.get('evaluation_split_partition')
    inferred = 'train' if str(split).endswith('_train') else 'test' if str(split).endswith('_test') else None
    if explicit and inferred and explicit != inferred:
        raise ValueError('Partition metadata conflicts with split name')
    return explicit or inferred


def resolve_recorded(raw, repo):
    """Rebase explicitly recorded Windows checkout paths; never search other runs."""
    value = str(raw).replace('\\', '/')
    for anchor in ('experiments/', 'r4/', 'chinatravel/'):
        if anchor in value:
            path = (repo/value[value.index(anchor):]).resolve()
            return path if path.is_relative_to(repo.resolve()) else None
    path = (repo/value).resolve()
    return path if path.is_relative_to(repo.resolve()) else None


def hash_evidence(path, expected):
    if path is None or not path.is_file():
        return {'hash_status': 'missing', 'actual_sha256': None}
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    lf = raw.replace(b'\r\n', b'\n')
    status = ('exact' if actual == expected else
              'LF_equivalent' if hashlib.sha256(lf).hexdigest() == expected else
              'CRLF_equivalent' if hashlib.sha256(lf.replace(b'\n', b'\r\n')).hexdigest() == expected else
              'mismatch' if expected else 'no_expected_hash')
    return {'hash_status': status, 'actual_sha256': actual}


def audit_matrix(root, metadata, repo=None):
    repo = (repo or Path(__file__).resolve().parents[1]).resolve()
    root = Path(root)
    artifacts, cells, sources, validations = [], [], [], []
    train_path = repo/'chinatravel/evaluation/default_splits/subset_train.txt'
    train = set(train_path.read_text().split()) if train_path.exists() else None
    test = set(metadata.get('selected_query_ids', [])) if partition({}, metadata) == 'test' else set()
    def inspect(path, expected, role, recorded=None):
        info = dict(role=role, recorded_path=str(recorded or path),
                    resolved_path=str(path.relative_to(repo)) if path and path.is_relative_to(repo) else None,
                    expected_sha256=expected, **hash_evidence(path, expected))
        artifacts.append(info)
        return info['hash_status']
    if metadata.get('training_uid_allowlist_sha256'):
        expected=metadata['training_uid_allowlist_sha256']
        actual=hashlib.sha256('\n'.join(sorted(train)).encode()).hexdigest() if train is not None else None
        artifacts.append(dict(role='training_uid_allowlist',recorded_path=str(train_path.relative_to(repo)),
                              resolved_path=str(train_path.relative_to(repo)),expected_sha256=expected,actual_sha256=actual,
                              hash_kind='sha256_of_LF_joined_sorted_UID_set_without_trailing_newline',
                              hash_status='exact_canonical_uid_set' if actual==expected else 'mismatch'))
    for label, info in sorted(metadata.get('matrices', {}).items()):
        path = (root/info['path']).resolve() if info.get('path') else None
        if path is not None and not path.is_relative_to(root.resolve()):
            raise ValueError('R4 matrix snapshot path escapes source run')
        if path is None or not path.is_file():
            continue
        mp = path.with_name('main_matrix_manifest.json')
        manifest = read(mp) if mp.exists() else {}
        inspect(path, info.get('sha256'), 'runtime_matrix', info.get('path'))
        inspect(mp, info.get('manifest_sha256'), 'runtime_matrix_manifest')
        inspect(path, manifest.get('output_sha256'), 'matrix_manifest_output')
        frame = pd.read_csv(path)
        required = {'source_family', 'destination_family', 'regression_count', 'support_count', 'regression_probability'}
        if not required <= set(frame):
            raise ValueError('R4 guidance matrix lacks required columns')
        if frame.duplicated(['source_family', 'destination_family']).any():
            raise ValueError('Duplicate R4 prior matrix cell')
        for row in frame.to_dict('records'):
            k, n, p = row['regression_count'], row['support_count'], row['regression_probability']
            if pd.notna(n):
                if pd.isna(k) or int(n) != n or int(k) != k or not 0 <= k <= n:
                    raise ValueError('Invalid R4 prior count/support')
                if not (pd.isna(p) if n == 0 else np.isclose(p, k/n)):
                    raise ValueError('R4 prior probability disagrees with count/support')
            elif pd.notna(k) or pd.notna(p):
                raise ValueError('Unavailable prior evidence must remain missing')
            cells.append({'matrix_label': label, **row})
        for source in manifest.get('input_matrices', []):
            directory = resolve_recorded(source['directory'], repo)
            statuses = []
            for kind in ('count', 'support', 'rate'):
                f = directory/f"{manifest.get('perspective', 'candidate')}_regression_{kind}.csv" if directory else None
                statuses.append(inspect(f, source.get(kind+'_sha256'), 'training_'+kind, source['directory']))
            cp = directory/'matrix_contributions.csv' if directory else None
            statuses.append(inspect(cp, source.get('contributions_sha256'), 'training_contributions', source['directory']))
            uid_set, labels = None, set()
            if cp and cp.is_file():
                contributions = pd.read_csv(cp)
                uid_set = set(contributions.query_uid.dropna())
                labels = set(contributions.repair_strategy.dropna())
            history = source.get('commonsense_destination_evidence', {})
            history_uids, history_ok = set(), True
            inputs = history.get('history_files', []) + ([history['run_manifest']] if history.get('run_manifest') else [])
            for h in inputs:
                f = resolve_recorded(h['path'], repo)
                status = inspect(f, h.get('sha256'), 'training_history', h['path'])
                statuses.append(status)
                if f and f.is_file():
                    saved = read(f)
                    if saved.get('query_uid'):
                        history_uids.add(saved['query_uid'])
                    history_uids.update(saved.get('query_uids', []))
                else:
                    history_ok = False
            all_uids = (uid_set or set()) | history_uids
            good_hashes = all(s in ('exact', 'LF_equivalent', 'CRLF_equivalent') for s in statuses)
            train_only = bool(uid_set) and train is not None and all_uids <= train and not (all_uids & test)
            sources.append(dict(matrix_label=label, strategy=source.get('strategy'), directory=source['directory'],
                                distinct_training_uids=len(all_uids) if uid_set is not None else None,
                                outside_training_count=len(all_uids-train) if train is not None else None,
                                test_overlap_count=len(all_uids & test), train_only_content_verified=train_only,
                                source_label_verified=labels == {source.get('strategy')},
                                content_hashes_verified=good_hashes,
                                byte_exact_hashes_verified=all(s == 'exact' for s in statuses),
                                commonsense_history_status=history.get('status'),
                                history_files=len(inputs), history_available=history_ok))
        validations.append(dict(matrix_label=label, path=str(path.relative_to(repo)),
                                manifest_type=manifest.get('matrix_type'), perspective=manifest.get('perspective'),
                                rows=len(frame), source_dimensions=frame.source_family.nunique(),
                                destination_dimensions=frame.destination_family.nunique(),
                                matrix_manifest=manifest))
    for recorded,expected in metadata.get('implementation_sha256',{}).items():
        normalized=recorded.replace('\\','/')
        if any(normalized.endswith(suffix) for suffix in ('r4/build_main_matrix.py','r4/commonsense_evidence.py','repair_strategies/r4.py')):
            inspect(resolve_recorded(recorded,repo),expected,'recorded_implementation',recorded)
    # Inspect separately supplied repository snapshots; never replace the run's snapshot.
    root_manifest = repo/'r4/main_matrix_manifest.json'
    if root_manifest.exists():
        m = read(root_manifest)
        inspect(repo/'r4/main_matrix_from_subset_train_r0_r3_10x10.csv', m.get('output_sha256'), 'repository_matrix')
        pivot = m.get('probability_pivot', {})
        if pivot.get('file'):
            inspect(repo/'r4'/pivot['file'], pivot.get('sha256'), 'repository_probability_pivot')
    strict = bool(artifacts) and all(x['hash_status'] == 'exact' for x in artifacts)
    verified = bool(sources) and {s['strategy'] for s in sources} == {'R0','R1','R2','R3'} and all(
        s['train_only_content_verified'] and s['content_hashes_verified'] and s['source_label_verified'] for s in sources)
    runtime_verified = all(x['hash_status'] in ('exact','LF_equivalent','CRLF_equivalent','exact_canonical_uid_set') for x in artifacts
                           if x['role'].startswith('runtime') or x['role'] in ('matrix_manifest_output','training_uid_allowlist'))
    return dict(train_only_guidance_verified=verified and runtime_verified,
                byte_exact_provenance_verified=strict,
                provenance_caveat='Raw and line-ending-equivalent hashes are reported separately; Windows paths are rebased to the same repository artifacts. No matrix is rebuilt.',
                artifacts=artifacts, sources=sources, matrices=validations, cells=cells)


def hook(attempts):
    columns = ['query_uid','repair_strategy','step','repair_phase','target_constraint_indices','target_commonsense_errors',
               'protected_constraint_indices','editable_scope','scope_level','accepted','fixed_count',
               'newly_violated_count','accepted_newly_violated_count','changed_slot_count']
    return {'r4_targeting': attempts.reindex(columns=columns)}, (
        'MatrixGuidedRepair uses whole-plan freedom and advisory rankings. All failed personal constraints remain declared targets; '
        'the recommended target is not an enforced target/order. Passing constraints are prompt protection, not an R2 rollback rule. '
        'Structural/parse rejection can return an unchanged proposal; final outcome selection is separate from proposal acceptance.')


def build_tables(run, attempts):
    data = run.extra
    selections = {s['query_uid']: s for s in data.get('selections', [])}
    trials, costs, selection_rows, guidance, recommendations, fallbacks, safety = [], [], [], [], [], [], []
    for trial in sorted(data.get('trials', []), key=lambda t:(t['query_uid'],t['repair_strategy'])):
        uid, label = trial['query_uid'], trial['repair_strategy']
        s = selections.get(uid, {})
        eligible = [e for e in trial['repair_history'][1:] if (e.get('repair_attempt') or {}).get('exception') is None and e.get('candidate_plan') is not None]
        trials.append(dict(query_uid=uid, trial_id=label, execution_status=trial.get('execution_status'),
                           proposals=len(trial.get('repair_attempts', [])), considered_candidate_outcomes=len(eligible),
                           supplies_selected_outcome=s.get('selected_source')==label if s else None,
                           selected_step=s.get('selected_step') if s.get('selected_source')==label else None,
                           matrix_used=trial.get('matrix_used'), artifact_path=trial['_artifact_path']))
    for uid in sorted(set(selections) | set(data.get('queries', {}))):
        s = selections.get(uid)
        exports = data.get('queries', {}).get(uid, {})
        cost = exports.get('computational_cost')
        if cost:
            if s and cost.get('costs') != s.get('costs'):
                raise ValueError('R4 selection and computational costs disagree')
            costs.append({'query_uid':uid,'repair_attempt_count_all_trials':cost.get('repair_attempt_count_all_trials'),
                          'monetary_cost':cost.get('monetary_cost'), **(cost.get('costs') or {})})
        elif s and isinstance(s.get('costs'), dict):
            costs.append({'query_uid':uid,'repair_attempt_count_all_trials':s.get('repair_attempt_count_all_trials'),
                          'monetary_cost':s.get('monetary_cost'), **s['costs']})
        if not s:
            continue
        related = [t for t in trials if t['query_uid']==uid]
        n = sum(t['considered_candidate_outcomes'] for t in related) + (1 if uid in run.initial_states else 0)
        selected = s.get('selected_verification') or {}
        final = exports.get('final_state', {})
        if final and (final.get('final_verification') != s.get('selected_verification') or final.get('final_accepted_plan') != s.get('selected_plan')):
            raise ValueError('R4 final export disagrees with saved selected outcome')
        if exports.get('final_itinerary') and exports['final_itinerary'].get('itinerary') != s.get('selected_plan'):
            raise ValueError('R4 final itinerary disagrees with selection')
        pool = []
        if uid in run.initial_states:
            pool.append(('initial',0,run.initial_states[uid].get('initial_verification')))
        for t in data.get('trials', []):
            if t['query_uid']==uid:
                pool.extend((t['repair_strategy'],e['step'],e.get('verification')) for e in t['repair_history'][1:]
                            if (e.get('repair_attempt') or {}).get('exception') is None and e.get('candidate_plan') is not None)
        # Verify identity/content only; do not recompute or alter the selection score/rule.
        matching = [v for src,step,v in pool if src==s.get('selected_source') and step==s.get('selected_step')]
        if pool and (len(matching)!=1 or matching[0]!=s.get('selected_verification')):
            raise ValueError('Saved R4 selection is not a matching persisted pool member')
        selection_rows.append(dict(query_uid=uid, mode=s.get('mode'), selected_source=s.get('selected_source'),
                                   selected_step=s.get('selected_step'), selected_matrix_used=s.get('selected_matrix_used'),
                                   selection_score=s.get('selection_score'), selection_rule=s.get('selection_rule'),
                                   considered_outcomes=n if related or uid in run.initial_states else None,
                                   non_selected_outcomes=n-1 if matching else None, trials=len(related),
                                   selected_personal_states=selected.get('personal_constraints'),
                                   selected_commonsense_errors=selected.get('commonsense_errors'),
                                   selected_schema_errors=selected.get('schema_errors'),
                                   repair_attempt_count_all_trials=s.get('repair_attempt_count_all_trials')))
        observed = sum(t['proposals'] for t in related)
        if related and observed != s.get('repair_attempt_count_all_trials'):
            raise ValueError('R4 selected all-trial attempt count disagrees with checkpoints')
    raw = {(r['query_uid'],r['repair_strategy'],r['step']):r for r in run.attempts}
    for row in attempts.to_dict('records'):
        original = raw[(row['query_uid'],row['repair_strategy'],row['step'])];m=original.get('repair_metadata') or {}
        ranked = m.get('risk_target_ranking');common=m.get('commonsense_source_risks')
        used = []
        for rank, rec in enumerate(ranked or [],1):
            rec_id=rec.get('constraint_index');recommended=m.get('recommended_risk_target')
            recommendations.append(dict(query_uid=row['query_uid'],trial_id=row['repair_strategy'],step=row['step'],rank=rank,
                constraint_index=rec_id,family=rec.get('family'),expected_regressed_families=rec.get('expected_regressed_families'),
                support_sum=rec.get('support_sum'),is_recommended=rec==recommended))
            for index,cell in enumerate(rec.get('destination_risks',[])):
                used.append(dict(origin='personal_ranking',relationship_ordinal=index,rank=rank,
                                 source_family=rec.get('family'),ranked_constraint_index=rec_id,**cell))
        for index,cell in enumerate(common or []):
            used.append(dict(origin='commonsense_source_risks',relationship_ordinal=index,rank=None,
                             source_family='commonsense_repair',ranked_constraint_index=None,**cell))
        for cell in used:
            guidance.append(dict(query_uid=row['query_uid'],trial_id=row['repair_strategy'],step=row['step'],repair_phase=row['repair_phase'],
                                 matrix_path=m.get('risk_matrix_path'),matrix_sha256=m.get('risk_matrix_sha256'),
                                 guidance_policy=m.get('matrix_guidance_policy'),**cell))
        if ranked is not None or common is not None or m.get('failure_reason') or m.get('decision_reason'):
            neutral=sum(c.get('support_count') is None or c.get('support_count')==0 for c in used)
            fallbacks.append(dict(query_uid=row['query_uid'],trial_id=row['repair_strategy'],step=row['step'],repair_phase=row['repair_phase'],
                                  logged_relationships=len(used),unsupported_relationships=neutral,
                                  has_unsupported_relationship=bool(neutral) if used else None,
                                  no_logged_relationships=not used,neutral_risk_config=m.get('neutral_risk_fallback'),
                                  unmapped_ranked_targets=sum(r.get('family') is None for r in ranked) if ranked is not None else None,
                                  parse_failed=m.get('parse_failed'),structural_rejection_reason=m.get('proposal_rejected_reason'),
                                  failure_reason=m.get('failure_reason'),decision_reason=row.get('decision_reason')))
        safety.append(dict(query_uid=row['query_uid'],trial_id=row['repair_strategy'],step=row['step'],accepted=row['accepted'],
                           protected_constraint_indices=row.get('protected_constraint_indices'),
                           protected_regression_count=row.get('protected_regression_count'),
                           candidate_regressions=row['newly_violated_count'],accepted_regressions=row['accepted_newly_violated_count'],
                           parse_failed=m.get('parse_failed'),structural_rejection_reason=m.get('proposal_rejected_reason'),
                           explicit_safety_rejection=m.get('safety_rejection')))
    tables={}
    for name,rows in [('r4_trials',trials),('r4_selections',selection_rows),('r4_costs',costs),
                      ('r4_matrix_guidance',guidance),('r4_recommendations',recommendations),
                      ('r4_fallbacks',fallbacks),('r4_safety_summary',safety)]:
        if rows:tables[name]=pd.DataFrame(rows)
    if guidance:
        g=tables['r4_matrix_guidance']
        tables['r4_support_summary']=g.groupby(['origin','evidence_status','support_count'],dropna=False,sort=True).size().reset_index(name='logged_relationships')
    if len(attempts):
        tables['r4_scope_summary']=attempts.groupby(['repair_phase','editable_scope'],dropna=False,sort=True).agg(
            proposals=('step','size'),fixes=('fixed_count','sum'),regressions=('newly_violated_count','sum'),
            mean_changed_slots=('changed_slot_count','mean'),footprint_valid_n=('changed_slot_count','count')).reset_index()
    return tables


def figures(folder, tables, export, bar):
    if 'r4_matrix_cells' in tables:
        import matplotlib.pyplot as plt
        for label,g in tables['r4_matrix_cells'].groupby('matrix_label',sort=True):
            for field,kind in [('regression_probability','probability'),('support_count','support')]:
                pivot=g.pivot(index='source_family',columns='destination_family',values=field)
                fig,ax=plt.subplots(figsize=(12,8));cmap=plt.get_cmap('YlOrRd' if kind=='probability' else 'Blues').copy();cmap.set_bad('#dddddd')
                im=ax.imshow(np.ma.masked_invalid(pivot.to_numpy(float)),cmap=cmap,vmin=0,vmax=1 if kind=='probability' else None,aspect='auto')
                for r in g.to_dict('records'):
                    i,j=list(pivot.index).index(r['source_family']),list(pivot.columns).index(r['destination_family'])
                    n,k=r['support_count'],r['regression_count']
                    text=f'{int(k)}/{int(n)}' if kind=='probability' and pd.notna(n) and n>0 else ('—' if kind=='probability' else str(int(n)) if pd.notna(n) else '—')
                    v=pivot.iloc[i,j];threshold=.5 if kind=='probability' else float(np.nanmax(pivot.to_numpy(float)))/2
                    ax.text(j,i,text,ha='center',va='center',fontsize=8,color='white' if pd.notna(v) and v>threshold else 'black')
                ax.set(xticks=range(len(pivot.columns)),yticks=range(len(pivot.index)),xticklabels=pivot.columns,yticklabels=pivot.index,title=f'R4 TRAIN-derived prior {kind} [{label}] (not R4 outcome risk)')
                plt.setp(ax.get_xticklabels(),rotation=45,ha='right');fig.colorbar(im,ax=ax);export(fig,f'r4_prior_{label}_{kind}')
    if 'r4_trials' in tables:
        t=tables['r4_trials']
        bar('r4_trials_per_query',t.groupby('query_uid').size().value_counts().sort_index().to_dict(),'Independent matrix trials per query','Queries')
    if 'r4_selections' in tables:
        t=tables['r4_selections']
        bar('r4_selected_sources',t.selected_source.value_counts().sort_index().to_dict(),'Saved selected outcome source','Queries')
        bar('r4_pool_outcomes',{'selected':len(t),'non-selected':t.non_selected_outcomes.sum()},'Outcome pool includes initial plan and eligible proposals','Outcomes')
    if 'r4_matrix_guidance' in tables:
        t=tables['r4_matrix_guidance']
        counts={str(int(k)):int(n) for k,n in t.support_count.dropna().value_counts().sort_index().items()}
        if t.support_count.isna().any():counts['unavailable']=int(t.support_count.isna().sum())
        bar('r4_logged_support',counts,'Support in logged advisory relationships','Logged relationships')
    if 'r4_fallbacks' in tables:
        t=tables['r4_fallbacks']
        bar('r4_fallback_evidence',{'unsupported relationship logged':int(t.has_unsupported_relationship.eq(True).sum()),
                                  'no relationship logged':int(t.no_logged_relationships.sum())},'Advisory evidence gaps; not inferred LLM actions')
    if 'r4_scope_summary' in tables:
        bar('r4_scopes',tables['r4_scope_summary'].groupby('editable_scope').proposals.sum().to_dict(),'R4 recorded scope')
    if 'r4_costs' in tables:
        t=tables['r4_costs']
        if 'all_trials_model_calls' in t:
            bar('r4_repair_model_calls',t.all_trials_model_calls.dropna().value_counts().sort_index().to_dict(),'Repair model calls per query','Queries')
    if 'r4_safety_summary' in tables:
        t=tables['r4_safety_summary'];reasons=t.structural_rejection_reason.dropna().value_counts().to_dict()
        if reasons:bar('r4_structure_rejections',reasons,'Logged structural rejection reasons')


def cost_summary(frame):
    rows=[]
    for column in frame.select_dtypes(include='number'):
        values=frame[column].dropna()
        rows.append(dict(metric=column,valid_n=len(values),known_subset_sum=values.sum() if len(values) else None,
                         complete_total=values.sum() if len(values)==len(frame) else None,
                         median=values.median() if len(values) else None))
    return pd.DataFrame(rows)


def report_sections(run, tables, audit, markdown):
    def table(name):
        return markdown(tables[name]) if name in tables else 'Unavailable: no corresponding persisted evidence.\n'
    return [
        ('R4 data source and partition', f"Partition: **{partition(run.manifest,run.extra.get('metadata')) or 'unknown'}**. Source `{run.path}`. Persisted mode: {run.extra.get('metadata',{}).get('mode','unavailable')}. Trial count is read from saved checkpoints, not assumed."),
        ('R4 mechanism', 'Active class: chinatravel.agent.nesy_verifier.repair_strategies.r4.MatrixGuidedRepair; r4/strategy.py re-exports it. Whole-plan advisory risk guidance reuses R3 parsing/structure helpers, not its widening schedule. Ranked personal targets minimize summed empirical probabilities to passing families, then prefer more total support, then lower index. All failed personal constraints remain targets. UNKNOWN feedback is included. Commonsense risks are separately logged. No enforced target order or matrix-chosen scope is claimed.'),
        ('Matrix provenance and leakage', f"TRAIN-only guidance content verified: **{audit['train_only_guidance_verified']}**. Byte-exact provenance verified: **{audit['byte_exact_provenance_verified']}**. {audit['provenance_caveat']} Sources and each hash result are in r4_matrix_sources.csv and r4_provenance_files.csv. Unavailable R1 commonsense-destination evidence remains missing; no matrix is rebuilt. Code versions are recorded in r4_run_metadata.json; no independent build version is invented."),
        ('Logged matrix guidance', 'Relationships below are persisted prompt advice, not demonstrated causal influence on the model. Recommendations are not actual chosen targets. Duplicate logged relationships are retained. No low-support cutoff is inferred. A configured neutral probability is not itself a fallback event.\n\n'+table('r4_support_summary')),
        ('Candidate/trial/outcome selection', 'One loop proposal, an independent matrix trial, a selectable saved outcome, loop acceptance and final selection are different units. The selector considers the initial plan and eligible verified candidate histories. It minimizes the saved unresolved-check score, then earliest step and source. Analysis reads the saved choice and validates membership, without running selection. It does not select the cheapest outcome.\n\n'+table('r4_selections')),
        ('R4 scope and targeting', table('r4_scope_summary')),
        ('Protection and safety', 'Passing constraints are prompt-only protection. MatrixGuidedRepair inherits always-accept behavior; there is no R2-style rollback on personal regression. Parse or structural failure can enforce an unchanged proposal before shared verification; that is not a rejected proposal. All candidates still use the shared verifier. Explicit safety rejection is unavailable unless logged. See r4_safety_summary.csv.'),
        ('R4 fallbacks', 'Count unsupported probabilities only from logged relationships. No-relationship and unmapped-target cases are separate. Do not infer the model followed a recommendation or a fallback. Parsing/structure failures are separate from missing prior evidence.\n\n'+(markdown(tables['r4_fallbacks'].groupby(['repair_phase','has_unsupported_relationship','no_logged_relationships'],dropna=False).size().reset_index(name='proposals')) if 'r4_fallbacks' in tables else 'Unavailable.')),
        ('Computational cost', 'r4_costs.csv preserves per-query repair/all-trial and including-initial counters separately. Selection overhead, currency charges and per-outcome cost are unavailable unless explicitly persisted; one trial containing several saved outcomes does not assign separate model cost to each selected/non-selected outcome. Do not equate repair tokens with end-to-end tokens.\n\n'+(markdown(cost_summary(tables['r4_costs'])) if 'r4_costs' in tables else 'Unavailable.')),
        ('Saved benchmark outcome policy',
         ('All saved benchmark plans match the trial last-accepted endpoint: '+str(int(tables['r4_benchmark_plan_audit'].matches_last_accepted_trial.sum()))+'/'+str(len(tables['r4_benchmark_plan_audit']))+
          '. Plans differing from post-hoc selection: **'+str(int((~tables['r4_benchmark_plan_audit'].matches_selected_outcome).sum()))+'**. These scores must not be presented as selected-outcome scores when plans differ. See r4_benchmark_plan_audit.csv.'
          if 'r4_benchmark_plan_audit' in tables else 'No saved benchmark plan comparison available.')),
        ('R4 interpretation and limitations', 'This individual R4 run uses the TEST partition. Generic final_observed fields describe the repair loop accepted trajectory; selected_final fields describe the persisted post-hoc exported choice, which can be initial or an earlier step. Benchmark population and saved translated plans are checked without invoking any evaluator. r4_benchmark_plan_audit.csv identifies whether scores describe last accepted trial or post-hoc selection; do not conflate them. Generic matrix_summary represents realized saved regression matrices, not the guidance prior; absent realized matrices remain unavailable. No selection/safety decision is invented from unlogged evidence.')]


def validate_population(run):
    """Reconcile saved exports only; never call a benchmark or selection evaluator."""
    declared=set(run.query_uids)
    checks=[]
    meta=run.extra.get('metadata',{})
    if meta.get('selected_query_ids') is not None and set(meta['selected_query_ids']) != declared:
        raise ValueError('R4 metadata population disagrees with manifest')
    selections={s['query_uid']:s for s in run.extra.get('selections',[])}
    if selections and set(selections)!=declared:
        raise ValueError('R4 selected outcomes do not cover exact declared population')
    for key,benchmark in run.benchmarks.items():
        if 'query_uids' in benchmark and set(benchmark['query_uids'])!=declared:
            raise ValueError('R4 benchmark population disagrees with manifest')
        if benchmark.get('query_count',len(declared))!=len(declared):
            raise ValueError('R4 benchmark count disagrees with manifest')
        directory=run.path/Path(key).parent
        pop=directory/'evaluation_population.json'
        if pop.exists():
            saved=read(pop)
            if set(saved.get('query_uids',[]))!=declared:
                raise ValueError('R4 saved evaluation population disagrees with manifest')
            if saved.get('language') not in (None,run.manifest.get('language')):
                raise ValueError('R4 benchmark language differs from run')
        for uid,s in selections.items():
            plan=directory/'plans'/(uid+'.json')
            if plan.exists():
                expected=(s.get('selected_verification') or {}).get('translated_plan') or {}
                actual=read(plan)
                trial_matches=[t for t in run.extra.get('trials',[]) if t['query_uid']==uid and
                               (directory.name==t['repair_strategy'] or directory.name.startswith(t['repair_strategy']+'-'))]
                trial=trial_matches[0] if len(trial_matches)==1 else (run.checkpoints.get(uid,{}) if not run.extra.get('independent_trials') else None)
                last=(trial.get('final_verification') or {}).get('translated_plan') or {} if trial is not None else None
                checks.append(dict(query_uid=uid,benchmark_directory=str(directory.relative_to(run.path)),
                                   matches_selected_outcome=actual==expected, matches_last_accepted_trial=actual==last if last is not None else None,
                                   saved_outcome_policy=read(pop).get('outcome_policy') if pop.exists() else None))
    return checks


def evidence_rows(run, audit):
    data=run.extra
    return [
        dict(metric='R4 selected outcomes',evidence='directly persisted' if data.get('selections') else 'unavailable',valid_n=len(data.get('selections',[]))),
        dict(metric='R4 independent trials',evidence='directly persisted' if data.get('trials') else 'unavailable',valid_n=len(data.get('trials',[]))),
        dict(metric='R4 guidance prior cells',evidence='directly persisted' if audit['cells'] else 'unavailable',valid_n=len(audit['cells'])),
        dict(metric='Actual LLM use of a particular advisory cell/target order',evidence='unavailable; logged ranking is advice only',valid_n=None),
        dict(metric='Post-hoc selection CPU overhead and monetary charges',evidence='unavailable unless explicitly persisted; not inferred from runtime differences',valid_n=None),
        dict(metric='R4 protection enforcement by personal-regression rollback',evidence='not implemented; prompt protection is not an enforced rollback',valid_n=None),
        dict(metric='TRAIN-only matrix provenance',evidence='reconstructable from hashes and UID membership',valid_n=len(audit['sources'])),
    ]
