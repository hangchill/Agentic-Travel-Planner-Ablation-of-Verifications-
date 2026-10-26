"""Offline analysis adapter tests; synthetic persisted fixtures only."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import warnings

import pandas as pd

from scripts.analyze_repair_strategies import (
    accepted_states, analyze, build_tables, file_hashes, hook_r2, hook_r3,
    load_matrices, load_run, main, parse_runs, record_metrics, state_stats,
)
from chinatravel.evaluation.repair_attempt import RepairAttemptRecord


def record(before=(False, True), after=(True, True), step=1, accepted=True,
           strategy='R0', uid='q1', **kwargs):
    transitions = {k: [] for k in ('fixed', 'newly_violated', 'still_failed', 'still_passed', 'unknown')}
    for i, (old, new) in enumerate(zip(before, after), 1):
        key = ('unknown' if old is None or new is None else
               'fixed' if old is False and new is True else
               'newly_violated' if old is True and new is False else
               'still_failed' if old is False else 'still_passed')
        transitions[key].append(i)
    return RepairAttemptRecord(
        step=step, repair_strategy=strategy, query_uid=uid,
        target_constraint_indices=[i for i, s in enumerate(before, 1) if s is False],
        target_constraint_labels=[], accepted=accepted,
        before_personal_constraints=list(before), after_personal_constraints=list(after),
        candidate_plan=[{'candidate': step}], accepted_plan_after=[{'accepted': step if accepted else 0}],
        repair_metadata={}, repair_phase='personal', **transitions, **kwargs).to_dict()


def make_run(folder, strategy='R0', records=None, declared=('q1', 'missing')):
    folder.mkdir(parents=True)
    (folder/'run_manifest.json').write_text(json.dumps(dict(
        run_id='test-'+strategy, repair_strategies=[strategy], query_uids=list(declared))))
    if records is not None:
        (folder/'attempts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    return folder


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_multiple_runs_sorted(self):
        a, b = self.root/'a', self.root/'b'
        a.mkdir(); b.mkdir()
        self.assertEqual(list(parse_runs([f'R2={b}', f'R0={a}'])), ['R0', 'R2'])

    def test_duplicate_label_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            parse_runs([f'R0={self.root}', f'R0={self.root}'])

    def test_invalid_directory_and_r3p_rejected(self):
        for arg in [f'R0={self.root}/absent', f'R3P={self.root}', 'R1']:
            with self.subTest(arg=arg), self.assertRaises(ValueError):
                parse_runs([arg])

    def test_generic_loading_sorting_and_envelope(self):
        r1 = record(uid='q1'); r1.update(run_id='test', matrix_run_id='test/R0')
        r2 = record(uid='q2')
        path = make_run(self.root/'r', records=[r2, r1], declared=['q2', 'q1'])
        run = load_run('R0', path)
        self.assertEqual([r['query_uid'] for r in run.attempts], ['q1', 'q2'])
        self.assertEqual(record_metrics(run.attempts[0])['fixed_count'], 1)

    def test_duplicate_step_rejected(self):
        path = make_run(self.root/'r', records=[record(), record()])
        with self.assertRaisesRegex(ValueError, 'Duplicate query/step'):
            load_run('R0', path)

    def test_missing_optional_files_and_missing_outcome(self):
        run = load_run('R0', make_run(self.root/'r', records=[record()]))
        self.assertFalse(run.checkpoints or run.summaries or run.benchmarks)
        a, q, _ = build_tables(run)
        missing = q[q.query_uid == 'missing'].iloc[0]
        self.assertFalse(missing.evidence_available)
        self.assertFalse(missing.terminal_status_known)
        self.assertTrue(pd.isna(missing.attempts))
        self.assertIsNone(missing.final_observed_states)
        self.assertFalse(q[q.query_uid == 'q1'].iloc[0].terminal_status_known)
        self.assertEqual(len(a), 1)

    def test_unknown_is_not_false_or_pass(self):
        row = state_stats([True, False, None], '')
        self.assertEqual(row['satisfaction'], .5)
        self.assertEqual(row['unknown'], 1)
        self.assertFalse(row['all_personal_pass'])
        self.assertIsNone(state_stats([None], '')['satisfaction'])
        self.assertIsNone(state_stats(None, '')['failures'])
        metrics = record_metrics(record(before=[None, True], after=[True, None]))
        self.assertEqual(metrics['fixed_count'], 0)
        self.assertEqual(metrics['newly_violated_count'], 0)

    def test_r2_rejected_candidate_does_not_advance(self):
        rejected = record(after=[True, False], accepted=False, strategy='R2',
                          protected_constraint_indices=[2])
        following = record(step=2, strategy='R2')
        run = load_run('R2', make_run(self.root/'r', 'R2', [rejected, following]))
        a, q, _ = build_tables(run)
        self.assertEqual(a.iloc[0].accepted_personal_constraints_after, [False, True])
        self.assertEqual(a.iloc[0].after_personal_constraints, [True, False])
        self.assertEqual(q[q.query_uid == 'q1'].iloc[0].final_observed_states, [True, True])
        self.assertEqual(a.iloc[0].accepted_newly_violated_count, 0)
        self.assertEqual(a.iloc[0].newly_violated_count, 1)
        hook, _ = hook_r2(a)
        h = hook['protection_and_rollback'].iloc[0]
        self.assertTrue(h.harmful_candidate_blocked)
        self.assertTrue(h.fixed_target_but_protected_regression_rejected)
        self.assertTrue(h.rejected_and_continued)

    def test_final_rejected_candidate_restores_initial(self):
        r = record(after=[True, False], accepted=False, strategy='R2')
        self.assertEqual(accepted_states([r]), [[False, True]])

    def test_bad_trajectory_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Inconsistent accepted trajectory'):
            accepted_states([record(), record(step=2)])

    def test_r3_scope_metadata_and_escalation(self):
        first = record(strategy='R3', after=[False, True], editable_scope='slot', scope_level=1)
        first['decision_reason'] = 'no_progress_unchanged'
        second = record(strategy='R3', step=2, editable_scope='day', scope_level=2,
                        escalation_reason='scheduled_widen_slot_to_day')
        run = load_run('R3', make_run(self.root/'r', 'R3', [second, first]))
        a, q, _ = build_tables(run)
        self.assertTrue(a.iloc[0].next_scope_escalation)
        self.assertEqual(q[q.query_uid == 'q1'].iloc[0].scope_sequence, 'slot,day')
        hooks, text = hook_r3(a)
        self.assertIn('fixed iteration', text)
        self.assertEqual(hooks['scope_outcomes'].attempts.sum(), 2)

    def test_missing_phase_is_not_guessed(self):
        r = record(); r.pop('repair_phase')
        a, q, _ = build_tables(load_run('R0', make_run(self.root/'r', records=[r])))
        self.assertIsNone(a.iloc[0].repair_phase)
        self.assertEqual(q[q.query_uid == 'q1'].iloc[0].phase_sequence, '?')

    def test_checkpoint_without_summary_or_jsonl(self):
        path = make_run(self.root/'r', declared=['q1'])
        cpdir = path/'queries'/'q1'; cpdir.mkdir(parents=True)
        (cpdir/'R0.json').write_text(json.dumps(dict(query_uid='q1', repair_strategy='R0',
            repair_attempts=[record()], initial_verification={'personal_constraints': [False, True]},
            final_verification={'personal_constraints': [True, True]}, execution_status='completed')))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            run = load_run('R0', path)
        a, q, _ = build_tables(run)
        self.assertEqual(len(a), 1)
        self.assertTrue(q.iloc[0].terminal_status_known)

    def test_summary_without_checkpoint(self):
        path = make_run(self.root/'r', declared=['q1'])
        pd.DataFrame([dict(query_uid='q1', repair_strategy='R0', attempts=3,
                          execution_status='completed', final_personal_constraint_satisfaction_rate=.5,
                          final_failed_count=1)]).to_csv(path/'summaries.csv', index=False)
        a, q, _ = build_tables(load_run('R0', path))
        self.assertEqual(len(a), 0)
        self.assertEqual(q.iloc[0].attempts, 3)
        self.assertEqual(q.iloc[0].final_observed_satisfaction, .5)
        self.assertIsNone(q.iloc[0].total_fixed_events)
        self.assertIsNone(q.iloc[0].model_calls)

    def test_identity_mismatch_warned(self):
        path = make_run(self.root/'r', strategy='R2', records=[record(strategy='R2')])
        with self.assertWarnsRegex(UserWarning, 'disagrees'):
            load_run('R0', path)

    def matrix(self, support=5, count=2, rate=.4):
        path = self.root/'matrices'; path.mkdir(exist_ok=True)
        for kind, value in [('support', support), ('count', count), ('rate', rate)]:
            pd.DataFrame([[value]], index=pd.Index(['budget'], name='source_family'),
                         columns=['dining']).to_csv(path/f'candidate_regression_{kind}.csv')
        return path

    def test_matrix_count_support_rate(self):
        for n, k, v in [(1, 0, 0.), (50, 0, 0.), (5, 2, .4), (0, 0, None)]:
            with self.subTest(n=n):
                frame, _ = load_matrices(self.matrix(n, k, v))
                self.assertEqual(frame.iloc[0].support_count, n)
                self.assertEqual(frame.iloc[0].regression_count, k)
                self.assertTrue(pd.isna(frame.iloc[0].regression_rate) if v is None else frame.iloc[0].regression_rate == v)

    def test_bad_matrix_ratio_rejected(self):
        with self.assertRaisesRegex(ValueError, 'rate disagrees'):
            load_matrices(self.matrix(0, 0, 0.))

    def test_optional_matrix_missing(self):
        m, messages = load_matrices(self.root/'none')
        self.assertTrue(m.empty)
        self.assertIn('unavailable', messages[0])

    def test_single_run_cli_and_repeat_numerical_outputs(self):
        path = make_run(self.root/'run', records=[record()])
        before = file_hashes(path)
        out = self.root/'out'
        args = ['--run', f'R0={path}', '--output-dir', str(out), '--no-figures']
        with redirect_stdout(StringIO()):
            self.assertEqual(main(args), 0)
            first = {p.name: p.read_bytes() for p in (out/'R0').glob('*.csv')}
            self.assertEqual(main(args), 0)
        self.assertEqual(first, {p.name: p.read_bytes() for p in (out/'R0').glob('*.csv')})
        self.assertEqual(before, file_hashes(path))
        self.assertTrue((out/'R0'/'ANALYSIS.md').exists())
        self.assertTrue((out/'R0'/'matrix_summary.csv').exists())

    def test_cli_multiple_runs_order_independent(self):
        a = make_run(self.root/'a', records=[record()])
        b = make_run(self.root/'b', 'R2', [record(strategy='R2')])
        for name, entries in [('out1', [f'R0={a}', f'R2={b}']), ('out2', [f'R2={b}', f'R0={a}'])]:
            args = ['--output-dir', str(self.root/name), '--no-figures']
            for entry in entries:
                args.extend(['--run', entry])
            with redirect_stdout(StringIO()):
                main(args)
        for strategy in ('R0', 'R2', 'cross_strategy'):
            for p in (self.root/'out1'/strategy).glob('*.csv'):
                self.assertEqual(p.read_bytes(), (self.root/'out2'/strategy/p.name).read_bytes())

    def test_output_cannot_overlap_source(self):
        path = make_run(self.root/'r', records=[])
        with self.assertRaises(SystemExit), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            main(['--run', f'R0={path}', '--output-dir', str(path/'analysis'), '--no-figures'])

    def test_checkpoint_missing_attempt_evidence_not_zero(self):
        path = make_run(self.root/'r', declared=['q1'])
        cpdir = path/'queries'/'q1'; cpdir.mkdir(parents=True)
        (cpdir/'R0.json').write_text(json.dumps(dict(query_uid='q1', repair_strategy='R0',
            final_verification={'personal_constraints': [True]}, execution_status='completed')))
        _, q, _ = build_tables(load_run('R0', path))
        self.assertTrue(q.iloc[0].terminal_status_known)
        self.assertIsNone(q.iloc[0].attempts)
        self.assertIsNone(q.iloc[0].total_fixed_events)
        self.assertIsNone(q.iloc[0].model_calls)

    def test_explicit_zero_attempt_checkpoint(self):
        path = make_run(self.root/'r', declared=['q1'])
        cpdir = path/'queries'/'q1'; cpdir.mkdir(parents=True)
        (cpdir/'R0.json').write_text(json.dumps(dict(query_uid='q1', repair_strategy='R0',
            repair_attempts=[], initial_verification={'personal_constraints': [True]},
            final_verification={'personal_constraints': [True]}, execution_status='completed')))
        _, q, _ = build_tables(load_run('R0', path))
        self.assertEqual(q.iloc[0].attempts, 0)
        self.assertEqual(q.iloc[0].total_fixed_events, 0)
        self.assertEqual(q.iloc[0].model_calls, 0)

    def test_empty_population_no_fabricated_terminal(self):
        path = make_run(self.root/'r', records=[], declared=[])
        with redirect_stdout(StringIO()):
            main(['--run', f'R0={path}', '--output-dir', str(self.root/'out'), '--no-figures'])
        self.assertEqual(len(pd.read_csv(self.root/'out/R0/query_level.csv')), 0)

    def test_each_strategy_with_no_attempt_records(self):
        for strategy in ('R0', 'R1', 'R2', 'R3'):
            path = make_run(self.root/strategy, strategy, records=[], declared=['missing'])
            with self.subTest(strategy=strategy), redirect_stdout(StringIO()):
                main(['--run', f'{strategy}={path}', '--output-dir', str(self.root/'out'), '--no-figures'])
            q = pd.read_csv(self.root/'out'/strategy/'query_level.csv')
            self.assertTrue(q.attempts.isna().all())
            self.assertFalse(q.terminal_status_known.any())

    def test_r2_missing_protection_stays_unavailable(self):
        r = record(strategy='R2'); r.pop('protected_constraint_indices')
        path = make_run(self.root/'r', 'R2', [r])
        a, _, _ = build_tables(load_run('R2', path))
        hook, _ = hook_r2(a)
        self.assertIsNone(hook['protection_and_rollback'].iloc[0].harmful_candidate_blocked)

    def test_matrix_saved_contributions_disagreement_fails(self):
        path = self.matrix()
        pd.DataFrame([dict(perspective='candidate', source_family='budget',
                           destination_family='dining', eligible=True,
                           regression=False, query_uid='q1')]).to_csv(path/'matrix_contributions.csv', index=False)
        with self.assertRaisesRegex(ValueError, 'saved contributions'):
            load_matrices(path)

    def test_missing_manifest_infers_evidence_not_declared(self):
        path = make_run(self.root/'r', records=[record()])
        (path/'run_manifest.json').unlink()
        with self.assertWarnsRegex(UserWarning, 'No declared population'):
            run = load_run('R0', path)
        self.assertEqual(run.query_uids, ['q1'])

    def test_invalid_persisted_transition_fails(self):
        r = record(); r['fixed'] = []
        path = make_run(self.root/'r', records=[r])
        with self.assertRaises(ValueError):
            load_run('R0', path)

    def test_symlink_output_cannot_overwrite_source(self):
        path = make_run(self.root/'r', records=[record()])
        out = self.root/'out'; out.mkdir()
        (out/'R0').symlink_to(path, target_is_directory=True)
        with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
            main(['--run', f'R0={path}', '--output-dir', str(out), '--no-figures'])


class R4AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def fixture(self):
        path=make_run(self.root/'r4', 'R4', declared=['q1'])
        m=json.loads((path/'run_manifest.json').read_text());m['split_query_source']='subset_test';m['language']='en'
        (path/'run_manifest.json').write_text(json.dumps(m))
        r=record(strategy='R4',editable_scope='plan',scope_level=3,model_calls=1,total_tokens_delta=22)
        r['accepted_plan_after']=r['candidate_plan']
        ranking=dict(constraint_index=1,family='monetary_budget',expected_regressed_families=.5,support_sum=0,
                     destination_risks=[dict(family='party_resources',regression_probability=.5,support_count=0,
                                            support_query_count=0,evidence_status='unobserved')])
        r['repair_metadata'].update(risk_target_ranking=[ranking],recommended_risk_target=ranking,
                                   commonsense_source_risks=[],neutral_risk_fallback=.5,matrix_guidance_policy='advisory',
                                   parse_failed=False,proposal_rejected_reason=None)
        (path/'attempts.jsonl').write_text(json.dumps(r)+'\n')
        q=path/'queries/q1';(q/'trials').mkdir(parents=True)
        before=dict(personal_constraints=[False,True],commonsense_errors=[],schema_errors=[],passed=False,
                    translated_plan={'itinerary':'initial'})
        after=dict(personal_constraints=[True,True],commonsense_errors=['new1','new2'],schema_errors=[],passed=False,
                   translated_plan={'itinerary':'candidate'})
        plan=[{'original':True}]
        initial=dict(query_uid='q1',state=dict(raw_initial_plan=plan,initial_verification=before))
        (q/'initial_state.json').write_text(json.dumps(initial))
        trial=dict(query_uid='q1',repair_strategy='R4',initial_raw_plan=plan,initial_verification=before,
                   final_accepted_plan=r['accepted_plan_after'],final_verification=after,execution_status='completed',
                   repair_attempts=[r],repair_history=[{'step':0,'verification':before},
                       {'step':1,'repair_attempt':r,'candidate_plan':r['candidate_plan'],'verification':after}])
        (q/'trials/R4-test.json').write_text(json.dumps(trial))
        costs=dict(all_trials_model_calls=1,all_trials_total_tokens_delta=22)
        selection=dict(query_uid='q1',mode='combined',execution_status='completed',selected_source='initial',selected_step=0,
                       selected_plan=plan,selected_verification=before,selection_score=[1,0,1,0,0],
                       selection_rule='saved rule',repair_attempt_count_all_trials=1,costs=costs,monetary_cost=None)
        (path/'r4_selection_and_costs.json').write_text(json.dumps([selection]))
        (path/'r4_run_metadata.json').write_text(json.dumps(dict(mode='combined',split='subset_test',
             evaluation_split_partition='test',selected_query_ids=['q1'],repair_budgets={'R4':6})))
        (q/'final_state.json').write_text(json.dumps(dict(query_uid='q1',repair_strategy='R4',
             final_verification=before,final_accepted_plan=plan,execution_status='completed')))
        (q/'repair_history.json').write_text(json.dumps(dict(query_uid='q1',repair_strategy='R4',
             final_verification=before,final_accepted_plan=plan,repair_attempts=[r])))
        (q/'final_itinerary.json').write_text(json.dumps(dict(query_uid='q1',itinerary=plan)))
        (q/'computational_cost.json').write_text(json.dumps(dict(query_uid='q1',costs=costs,repair_attempt_count_all_trials=1)))
        return path

    def test_r4_cli_and_metadata_loading(self):
        path=self.fixture();run=load_run('R4',path)
        self.assertEqual(list(parse_runs([f'R4={path}'])),['R4'])
        self.assertEqual(run.extra['metadata']['mode'],'combined')
        self.assertEqual(len(run.extra['trials']),1)
        self.assertEqual(run.checkpoints['q1']['final_verification']['personal_constraints'],[True,True])

    def test_selected_initial_is_not_loop_endpoint(self):
        path=self.fixture();run=load_run('R4',path)
        a,q,_=build_tables(run)
        from scripts.repair_analysis_r4 import build_tables as r4_tables
        t=r4_tables(run,a)
        self.assertEqual(q.iloc[0].final_observed_states,[True,True])
        self.assertEqual(t['r4_selections'].iloc[0].selected_personal_states,[False,True])
        self.assertEqual(t['r4_selections'].iloc[0].considered_outcomes,2)
        self.assertEqual(t['r4_selections'].iloc[0].non_selected_outcomes,1)
        self.assertFalse(t['r4_trials'].iloc[0].supplies_selected_outcome)

    def test_support_fallback_and_prompt_safety_fields(self):
        from scripts.repair_analysis_r4 import build_tables as r4_tables
        run=load_run('R4',self.fixture());a,_,_=build_tables(run);t=r4_tables(run,a)
        self.assertEqual(t['r4_matrix_guidance'].iloc[0].support_count,0)
        self.assertEqual(t['r4_matrix_guidance'].iloc[0].regression_probability,.5)
        self.assertTrue(t['r4_fallbacks'].iloc[0].has_unsupported_relationship)
        self.assertTrue(t['r4_recommendations'].iloc[0].is_recommended)
        self.assertIsNone(t['r4_safety_summary'].iloc[0].explicit_safety_rejection)
        self.assertEqual(t['r4_costs'].iloc[0].all_trials_total_tokens_delta,22)

    def test_missing_optional_r4_files(self):
        path=make_run(self.root/'r', 'R4', [record(strategy='R4')], declared=['q1'])
        run=load_run('R4',path);a,q,_=build_tables(run)
        self.assertEqual(len(a),1);self.assertFalse(q.iloc[0].terminal_status_known)
        self.assertEqual(run.extra['selections'],[])

    def test_r4_repeat_csvs(self):
        path=self.fixture();out=self.root/'out'
        args=['--run',f'R4={path}','--output-dir',str(out),'--no-figures']
        with redirect_stdout(StringIO()):
            main(args);first={p.name:p.read_bytes() for p in (out/'R4').glob('*.csv')};main(args)
        self.assertEqual(first,{p.name:p.read_bytes() for p in (out/'R4').glob('*.csv')})
        q=pd.read_csv(out/'R4/query_level.csv')
        self.assertEqual(q.iloc[0].final_observed_satisfaction,1.)
        self.assertEqual(q.iloc[0].selected_final_satisfaction,.5)

    def test_test_partition_not_in_train_aggregate(self):
        r4=self.fixture();r0=make_run(self.root/'r0',records=[record()],declared=['q1'])
        m=json.loads((r0/'run_manifest.json').read_text());m['split_query_source']='subset_train'
        (r0/'run_manifest.json').write_text(json.dumps(m))
        out=self.root/'out'
        with redirect_stdout(StringIO()):main(['--run',f'R4={r4}','--run',f'R0={r0}','--output-dir',str(out),'--no-figures'])
        summary=pd.read_csv(out/'cross_strategy/overall_summary.csv')
        self.assertEqual(set(summary.strategy),{'R0'})
        self.assertEqual(pd.read_csv(out/'cross_strategy/excluded_runs.csv').iloc[0].strategy,'R4')

    def test_benchmark_policy_difference_is_audited(self):
        from scripts.repair_analysis_r4 import validate_population
        path=self.fixture();b=path/'benchmark_eval/R4';(b/'plans').mkdir(parents=True)
        trial=json.loads(next((path/'queries/q1/trials').glob('*.json')).read_text())
        (b/'plans/q1.json').write_text(json.dumps(trial['final_verification']['translated_plan']))
        (b/'benchmark_summary.json').write_text(json.dumps(dict(query_uids=['q1'],query_count=1)))
        checks=validate_population(load_run('R4',path))
        self.assertFalse(checks[0]['matches_selected_outcome'])
        self.assertTrue(checks[0]['matches_last_accepted_trial'])

    def test_partition_mismatch_rejected(self):
        from scripts.repair_analysis_r4 import partition
        with self.assertRaises(ValueError):partition({'split_query_source':'subset_test'},{'evaluation_split_partition':'train'})

    def matrix_fixture(self):
        import hashlib
        repo=self.root/'repo';root=repo/'experiments/test';(root/'inputs/pooled').mkdir(parents=True)
        splits=repo/'chinatravel/evaluation/default_splits';splits.mkdir(parents=True)
        (splits/'subset_train.txt').write_text('train-1\n')
        inputs=[]
        def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
        for label in ['R0','R1','R2','R3']:
            d=repo/'experiments'/('train-'+label)/'regression_matrix';d.mkdir(parents=True)
            source={'strategy':label,'directory':str(d),'commonsense_destination_evidence':{}}
            for kind,value in [('count',0),('support',1),('rate',0)]:
                f=d/f'candidate_regression_{kind}.csv';pd.DataFrame([[value]],index=['budget'],columns=['dining']).to_csv(f)
                source[kind+'_sha256']=sha(f)
            f=d/'matrix_contributions.csv';pd.DataFrame([dict(query_uid='train-1',repair_strategy=label)]).to_csv(f,index=False)
            source['contributions_sha256']=sha(f);inputs.append(source)
        matrix=root/'inputs/pooled/main_matrix.csv'
        pd.DataFrame([dict(source_family='budget',destination_family='dining',regression_count=0,support_count=4,
                           regression_probability=0,evidence_status='observed')]).to_csv(matrix,index=False)
        manifest=dict(input_matrices=inputs,perspective='candidate',output_sha256=sha(matrix))
        mp=matrix.with_name('main_matrix_manifest.json');mp.write_text(json.dumps(manifest))
        meta=dict(split='subset_test',evaluation_split_partition='test',selected_query_ids=['q1'],
                  matrices={'R4':dict(path='inputs/pooled/main_matrix.csv',sha256=sha(matrix),manifest_sha256=sha(mp))})
        return repo,root,meta

    def test_matrix_provenance_train_only(self):
        from scripts.repair_analysis_r4 import audit_matrix
        repo,root,meta=self.matrix_fixture();audit=audit_matrix(root,meta,repo)
        self.assertTrue(audit['train_only_guidance_verified'])
        self.assertTrue(audit['byte_exact_provenance_verified'])
        self.assertEqual(audit['cells'][0]['support_count'],4)

    def test_matrix_test_leakage_flagged(self):
        from scripts.repair_analysis_r4 import audit_matrix
        repo,root,meta=self.matrix_fixture()
        cp=repo/'experiments/train-R0/regression_matrix/matrix_contributions.csv'
        cp.write_text(cp.read_text().replace('train-1','q1'))
        audit=audit_matrix(root,meta,repo)
        self.assertFalse(audit['train_only_guidance_verified'])
        self.assertEqual(audit['sources'][0]['test_overlap_count'],1)

    def test_hash_newline_equivalence_is_not_byte_equality(self):
        import hashlib
        from scripts.repair_analysis_r4 import hash_evidence
        p=self.root/'text.csv';p.write_bytes(b'a,b\n1,2\n')
        expected=hashlib.sha256(b'a,b\r\n1,2\r\n').hexdigest()
        self.assertEqual(hash_evidence(p,expected)['hash_status'],'CRLF_equivalent')

    def test_multiple_trials_keep_independent_trajectories(self):
        path=self.fixture();q=path/'queries/q1';first=json.loads(next((q/'trials').glob('*.json')).read_text())
        records=[]
        for i,label in enumerate(['R4_R0','R4_R1']):
            t=json.loads(json.dumps(first));t['repair_strategy']=label
            for r in t['repair_attempts']:r['repair_strategy']=label;records.append(r)
            for e in t['repair_history'][1:]:e['repair_attempt']['repair_strategy']=label
            (q/'trials'/(label+'.json')).write_text(json.dumps(t))
        (q/'trials/R4-test.json').unlink()
        (path/'attempts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
        run=load_run('R4',path);a,queries,_=build_tables(run)
        self.assertEqual(len(a),2);self.assertEqual(queries.iloc[0].attempts,2)
        self.assertIsNone(queries.iloc[0].final_observed_states)
        self.assertEqual(len(queries.iloc[0].trial_trajectories),2)

    def test_training_allowlist_hash_uses_documented_canonical_uid_set(self):
        import hashlib
        from scripts.repair_analysis_r4 import audit_matrix
        repo,root,meta=self.matrix_fixture()
        meta['training_uid_allowlist_sha256']=hashlib.sha256(b'train-1').hexdigest()
        audit=audit_matrix(root,meta,repo)
        self.assertTrue(audit['train_only_guidance_verified'])
        check=next(r for r in audit['artifacts'] if r['role']=='training_uid_allowlist')
        self.assertEqual(check['hash_status'],'exact_canonical_uid_set')
        meta['training_uid_allowlist_sha256']='wrong'
        self.assertFalse(audit_matrix(root,meta,repo)['train_only_guidance_verified'])

    def test_shared_core_definitions_identical_for_all_strategies(self):
        from scripts.analyze_repair_strategies import summarize
        for label in ['R0','R1','R2','R3','R4']:
            with self.subTest(label=label):
                path=make_run(self.root/label,label,[record(strategy=label)],declared=['q1'])
                run=load_run(label,path);a,q,_=build_tables(run);summary=summarize(run,a,q).set_index('metric')
                self.assertEqual(summary.loc['total_attempts','value'],1)
                self.assertEqual(summary.loc['personal_fixed_count_sum','value'],1)
                self.assertEqual(summary.loc['personal_pooled_targeted_success','value'],1)
                self.assertEqual(summary.loc['final_observed_satisfaction_mean','value'],1)

    def test_selection_count_disagreement_rejected(self):
        from scripts.repair_analysis_r4 import build_tables as r4_tables
        run=load_run('R4',self.fixture());run.extra['selections'][0]['repair_attempt_count_all_trials']=2
        a,_,_=build_tables(run)
        with self.assertRaisesRegex(ValueError,'count disagrees'):
            r4_tables(run,a)


if __name__ == '__main__':
    unittest.main()
