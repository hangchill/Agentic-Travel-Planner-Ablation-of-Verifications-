"""Conservative control checklist and explicit intersection handling."""
from . import COMPARISONS

FIELDS = {
 'base_model': ('model_identifier',),
 'model_configuration': ('sampling_settings',),
 'repair_budget': ('max_steps',),
 'scheduler_version': ('scheduler_version','scheduler_hash'),
 'verifier_configuration': ('verifier_config','verifier_configuration','verifier_hash'),
 'evaluator_configuration': ('evaluator_config','evaluator_configuration','evaluator_hash'),
 'repair_implementation': ('repair_implementation_hash','implementation_hash'),
 'source_benchmark_population': ('benchmark_population_hash','benchmark_source','split_query_source'),
 'language': ('language',), 'oracle_translation': ('oracle_translation',),
 'random_seed': ('seed',),
}


MATRIX_COMPONENT_CONTROLS = (
    'repair_prompt_without_guidance_hash', 'repair_logic_without_guidance_hash',
    'repair_scope_policy', 'acceptance_behavior_hash', 'structural_guard_policy_hash',
    'candidate_generation_hash', 'selection_behavior_hash',
)

# Read-only repository audit. These observations do not establish which code
# version a historical run executed; recorded component controls remain required.
IMPLEMENTATION_AUDIT = [
    {'component':'Prompt / repair logic','finding':'R0 uses the legacy BACK_PROMPT; R4 uses the R3 prompt contract plus advisory matrix guidance.', 'source':'repair_strategies/r0.py:R0WholePlanRepair.repair; repair_strategies/r4.py:MatrixGuidedRepair.repair'},
    {'component':'Repair scope','finding':'Both implementations request whole-plan repair. R4 inherits the R3 contract but explicitly uses PLAN rather than scheduled scope widening.', 'source':'repair_strategies/r0.py:editable_scope; repair_strategies/r4.py:_editable_region(PLAN)'},
    {'component':'Scheduler','finding':'Both use the shared loop; equality of the executed scheduler version requires recorded metadata.', 'source':'nesy_verifier/shared_repair_loop.py; run manifest scheduler_version/hash'},
    {'component':'Acceptance','finding':'Both inherit default acceptance; R4 structural guards may replace the candidate before that acceptance. This is not the R2 protected-PC rollback rule.', 'source':'repair_strategies/base.py:BaseRepairStrategy.accept; repair_strategies/r4.py:MatrixGuidedRepair.repair'},
    {'component':'Structural guards / candidate generation','finding':'R0 prefixes and repairs the response JSON; R4 uses R3 parsing and structural checks and can return the previous plan. These differ beyond supplying a matrix.', 'source':'repair_strategies/r0.py:repair_json; repair_strategies/r4.py:_parse_response/_structure_problem'},
    {'component':'Selection','finding':'R4 has post-hoc least-unresolved outcome selection; R0 uses the accepted loop trajectory. Benchmark metrics for both remain final accepted, never the post-hoc selection.', 'source':'r4/select_outcomes.py; chinatravel/evaluation/export_final_plans.py'},
    {'component':'Verifier / model / budget / initial plans / population','finding':'Use the recorded compatibility checklist; equal strategy roles or missing configuration do not prove equivalence.', 'source':'run manifests, recorded initial-plan hashes and bound TEST reporting'},
]


def setting(manifest, names):
    for container in (manifest,manifest.get('comparison_controls',{}),manifest.get('compatibility',{}).get('config',{})):
        for name in names:
            if container.get(name) is not None:
                return container[name]
    return None


def matrix_enabled(manifest):
    # An absent/empty relationship is not evidence that guidance was disabled.
    value=setting(manifest,('matrix_guidance_enabled',))
    return value if type(value) is bool else None


def assess(left,right,comparison_id,intersection=False):
    checks=[]
    def check(name,a,b,passed=None):
        status='unknown' if a is None or b is None else ('pass' if (a==b if passed is None else passed) else 'fail')
        checks.append({'check':name,'status':status,'left':a,'right':b})
    if left is None or right is None or left.error or right.error:
        missing=[role for role,e in zip(COMPARISONS[comparison_id][1:3],(left,right)) if e is None or e.error]
        reason=('Required '+' and '.join(role+' TEST' for role in missing)+' run is not currently available.'
                if comparison_id=='r0_vs_r4_matrix' else 'Required TEST run is unavailable or invalid.')
        return {'classification':'Incompatible / blocked','available':False,'allow_deltas':False,'reason':reason,
                'checks':checks,'n_left':len(left.population) if left else 0,'n_right':len(right.population) if right else 0,
                'n_matched':0,'cohort_label':'Full cohort','uids':[],'excluded_left':[],'excluded_right':[],
                'errors':[e.error for e in (left,right) if e and e.error]}
    a,b=set(left.population),set(right.population);matched=a&b
    same=a==b
    check('query_uid_population',sorted(a),sorted(b))
    check('query_count',len(a),len(b))
    chosen=matched if intersection else (a if same else set())
    label='Matched-query subset' if intersection else 'Full cohort'
    check('TEST_partition','TEST','TEST')
    lg=left.q.set_index('query_uid').group.to_dict() if not left.q.empty else {}
    rg=right.q.set_index('query_uid').group.to_dict() if not right.q.empty else {}
    group_left={uid:lg.get(uid) for uid in sorted(chosen)}
    group_right={uid:rg.get(uid) for uid in sorted(chosen)}
    known_groups=bool(chosen) and all(group_left.values()) and all(group_right.values())
    check('difficulty_mapping',group_left if known_groups else None,group_right if known_groups else None)
    ih_left={uid:left.initial_hashes.get(uid) for uid in sorted(chosen)}
    ih_right={uid:right.initial_hashes.get(uid) for uid in sorted(chosen)}
    known_initial=bool(chosen) and all(ih_left.values()) and all(ih_right.values())
    check('initial_plan_identities',ih_left if known_initial else None,ih_right if known_initial else None)
    for name,keys in FIELDS.items():
        check(name,setting(left.manifest,keys),setting(right.manifest,keys))
    budgets=[]
    for e in (left,right):
        overrides=setting(e.manifest,('strategy_max_steps',)) or {}
        budgets.append(overrides.get(e.strategy,setting(e.manifest,('max_steps',))))
    check('effective_repair_budget',*budgets)
    # Per-query benchmark hashes are stronger than a split label when recorded.
    hashes=[e.manifest.get('compatibility',{}).get('query_hashes') for e in (left,right)]
    check('benchmark_query_identities',*[({u:h.get(u) for u in sorted(chosen)} if h and all(h.get(u) for u in chosen) else None) for h in hashes])
    is_matrix=comparison_id=='r0_vs_r4_matrix'
    check('intended_strategy_difference',left.key,right.key,passed=(left.key,right.key)==COMPARISONS[comparison_id][1:3])
    if is_matrix:
        check('distinct_source_run_paths',str(left.path),str(right.path),passed=left.path!=right.path)
        x,y=matrix_enabled(left.manifest),matrix_enabled(right.manifest)
        check('matrix_guidance_treatment',x,y,passed=(x is False and y is True))
        audit=right.raw.extra.get('_comparison_matrix_audit',{}) if right.raw else {}
        verified=audit.get('train_only_guidance_verified')
        check('TRAIN_only_matrix_provenance',True,verified)
        from .metrics import guidance_cells
        logged=list(left.raw.attempts) if left.raw else []
        if left.raw:
            for cp in [*left.raw.checkpoints.values(),*left.raw.extra.get('trials',[])]:
                logged.extend(entry.get('repair_attempt') or {} for entry in cp.get('repair_history',[])[1:])
        recorded_positive=any((c.get('support_count') or 0)>0 for r in logged for c in guidance_cells(r.get('repair_metadata') or {})) if left.raw else None
        check('no_matrix_has_no_logged_supported_guidance',False,recorded_positive)
        for component in MATRIX_COMPONENT_CONTROLS:
            check(component,setting(left.manifest,(component,)),setting(right.manifest,(component,)))
        # Controlled status needs an explicit complete settings snapshot. Only the
        # intended Boolean treatment may differ; no arbitrary keys are dropped.
        settings=[e.manifest.get('ablation_settings') for e in (left,right)]
        normalized=[]
        for e,s in zip((left,right),settings):
            required={'model_identifier','sampling_settings','max_steps','scheduler_version','repair_implementation_hash',
                      'verifier_config','evaluator_config','benchmark_population_hash','language','oracle_translation','seed',
                      'other_settings','matrix_guidance_enabled',*MATRIX_COMPONENT_CONTROLS}
            if (not isinstance(s,dict) or not required <= set(s) or e.manifest.get('ablation_settings_complete') is not True or
                'matrix_guidance_enabled' not in s or s['matrix_guidance_enabled'] is not matrix_enabled(e.manifest)):
                normalized.append(None)
            else:
                normalized.append({k:v for k,v in s.items() if k!='matrix_guidance_enabled'})
        check('all_other_ablation_settings',*normalized)
        if any(not value for value in normalized):
            checks[-1]['status']='unknown'
    blocked=(not chosen or (not same and not intersection) or
             any(c['status']=='fail' for c in checks if c['check'] in ('difficulty_mapping','intended_strategy_difference','distinct_source_run_paths')))
    if blocked:
        classification='Incompatible / blocked'
    elif is_matrix and all(c['status']=='pass' for c in checks):
        classification='Controlled ablation'
    elif (all(c['status']=='pass' for c in checks if c['check']!='all_other_ablation_settings') and
          not any(c['status']=='fail' for c in checks if c['check']=='all_other_ablation_settings')):
        classification='Matched strategy comparison'
    else:
        classification='Descriptive comparison only'
    return {'classification':classification,'available':True,'allow_deltas':not blocked,
            'reason':'Population/cohort compatibility failed.' if blocked else 'No causal claim is licensed.' if classification!='Controlled ablation' else 'Recorded controls agree; intended treatment is matrix guidance only.',
            'checks':checks,'implementation_audit':IMPLEMENTATION_AUDIT if is_matrix else [],
            'implementation_audit_basis':'Current repository review; the executed run versions require recorded component controls.' if is_matrix else '','n_left':len(a),'n_right':len(b),'n_matched':len(matched),
            'cohort_label':label,'uids':sorted(chosen),'excluded_left':sorted(a-chosen),'excluded_right':sorted(b-chosen)}
