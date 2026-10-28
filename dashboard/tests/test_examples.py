"""Canonical examples require mechanism evidence, never just a strategy label."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from dashboard import data_loader as d
from dashboard.example_selection import find_examples, markdown, trajectory_rows
from dashboard.components.examples import collect, recorded_hash_matches, bound_train_matrix
from dashboard.tests.test_dashboard import FixtureCase

DESCRIPTORS = [
    {'constraint_index': 1, 'hard_logic_py': 'result=(day_count(plan)==1)'},
    {'constraint_index': 2, 'hard_logic_py': 'total_cost=0\nfor activity in allactivities(plan):\n    total_cost+=activity_cost(activity)\nresult=(total_cost<=100)'}]


def checkpoint(strategy='R2', specs=None):
    initial = {'personal_constraints': [False, True], 'commonsense_errors': ['bad'], 'translated_plan': {'version': 0}}
    history = [{'verification': initial}]
    plan = {'version': 0}
    for i, spec in enumerate(specs or [{}], 1):
        candidate = {'personal_constraints': spec.get('pc', [True, False]),
                     'commonsense_errors': spec.get('cs', ['bad']), 'translated_plan': {'version': i}}
        accepted = spec.get('accepted', False)
        attempt = {'repair_phase': spec.get('phase', 'personal'), 'editable_scope': spec.get('scope', 'slot'),
                   'target_constraint_indices': [1], 'target_constraint_labels': ['day count'],
                   'protected_constraint_indices': [2], 'constraint_descriptors': copy.deepcopy(DESCRIPTORS),
                   'accepted_plan_after': {'version': i} if accepted else copy.deepcopy(plan),
                   'decision_reason': spec.get('reason', 'previously_satisfied_constraint_regressed' if strategy == 'R2' and not accepted else None), 'repair_metadata': spec.get('meta', {})}
        if spec.get('not_preserved'):
            attempt['accepted_plan_after'] = {'version': 999}
        history.append({'step': i, 'accepted': accepted, 'verification': candidate, 'repair_attempt': attempt})
        if accepted:
            plan = {'version': i}
    return {'query_uid': 'example-uid', 'repair_strategy': strategy, 'matrix_run_id': 'independent-trial',
            'initial_raw_plan': {'version': 0}, 'initial_verification': initial, 'repair_history': history,
            'final_verification': candidate}


def find(strategy, partition, specs=None, **kwargs):
    cp = checkpoint(strategy, specs)
    run = d.Run('/tmp/evidence', partition, strategy, 'fixture-run')
    return find_examples(run, {'example-uid': {'checkpoints': [cp], 'selected': kwargs.pop('selected', {})}}, **kwargs)


def guidance(support=7):
    return {'risk_target_ranking': [{'family': 'trip_specification', 'destination_risks': [
        {'family': 'monetary_budget', 'support_count': support, 'regression_probability': .25}]}]}


def train_matrix():
    return pd.DataFrame([{'source_family': 'trip_specification', 'destination_family': 'monetary_budget',
                          'support_count': 7, 'regression_probability': .25}])


class SelectionTests(unittest.TestCase):
    def test_cascade_requires_target_fix_and_other_known_family_regression(self):
        result = find('R0','TRAIN')['cascade']
        self.assertEqual(len(result),1)
        self.assertNotEqual(result[0]['source_family'],result[0]['destination_family'])
        self.assertFalse(find('R0','TRAIN',[{'pc':[False,False]}])['cascade'])
        self.assertFalse(find('R0','TRAIN',[{'pc':[True,True]}])['cascade'])
        cp=checkpoint('R0');cp['repair_history'][1]['repair_attempt']['constraint_descriptors'][1]=dict(DESCRIPTORS[0],constraint_index=2)
        run=d.Run('/tmp/evidence','TRAIN','R0','fixture')
        self.assertFalse(find_examples(run,{'u':{'checkpoints':[cp]}})['cascade'])
        cp['repair_history'][1]['verification']['personal_constraints']=[True,None]
        self.assertFalse(find_examples(run,{'u':{'checkpoints':[cp]}})['cascade'])

    def test_r2_requires_protected_harm_rejection_and_plan_equality(self):
        e=find('R2','TEST')['r2'][0]
        self.assertTrue(e['retained'])
        self.assertEqual(e['protected_regressions'],[2])
        self.assertEqual(e['row']['candidate']['personal_constraints'],[True,False])
        self.assertEqual(e['row']['after']['personal_constraints'],[False,True])
        for spec in [{'accepted':True},{'not_preserved':True},{'pc':[True,True]},{'reason':'other_rejection'}]:
            self.assertFalse(find('R2','TEST',[spec])['r2'])
        cp=checkpoint();cp['repair_history'][1]['repair_attempt']['protected_constraint_indices']=[]
        self.assertFalse(find_examples(d.Run('/tmp/e','TEST','R2','id'), {'u':{'checkpoints':[cp]}})['r2'])

    def test_r3_requires_earlier_slot_and_later_accepted_improvement(self):
        specs=[{'pc':[False,True],'scope':'slot','accepted':True},
               {'pc':[False,True],'scope':'slot','accepted':True},
               {'pc':[True,True],'scope':'day','accepted':True}]
        e=find('R3','TEST',specs)['r3'][0]
        self.assertEqual([r['Scope'] for r in trajectory_rows(e['sequence'])],['slot','slot','day'])
        self.assertIn('fixed schedule', e['explanation'])
        for later in [{'pc':[False,True],'scope':'day','accepted':True},
                      {'pc':[True,True],'scope':'day','accepted':False},
                      {'pc':[True,True],'scope':'slot','accepted':True}]:
            self.assertFalse(find('R3','TEST',[specs[0],later])['r3'])
        self.assertFalse(find('R3','TEST',[specs[-1]])['r3'])

    def test_r3_does_not_join_independent_trials(self):
        cp1=checkpoint('R3',[{'pc':[False,True],'scope':'slot'}])
        cp2=checkpoint('R3',[{'pc':[True,True],'scope':'day','accepted':True}])
        run=d.Run('/tmp/e','TEST','R3','id')
        self.assertFalse(find_examples(run,{'u':{'checkpoints':[cp1,cp2]}})['r3'])

    def test_r4_support_requires_matching_train_cell_and_accepted_improvement(self):
        spec={'pc':[True,True],'scope':'plan','accepted':True,'meta':guidance()}
        e=find('R4','TEST',[spec],train_matrix=train_matrix())['r4'][0]
        self.assertEqual(e['relationships'][0]['support_count'],7)
        self.assertIn('R4 was provided matrix guidance',e['explanation'])
        self.assertFalse(find('R4','TEST',[spec])['r4'])
        for meta in [guidance(0),guidance(8),{}]:
            self.assertFalse(find('R4','TEST',[dict(spec,meta=meta)],train_matrix=train_matrix())['r4'])
        self.assertFalse(find('R4','TEST',[dict(spec,accepted=False)],train_matrix=train_matrix())['r4'])

    def test_r4_contrasts_are_classified_from_logs(self):
        for meta, expected in [(guidance(0),'unsupported'),({},'no logged relationship'),
                               (dict(guidance(),proposal_rejected_reason='day_count_mismatch'),'structural guard')]:
            e=find('R4','TEST',[{'meta':meta}])['contrast'][0]
            self.assertIn(expected,e['limitation'])
        self.assertFalse(find('R4','TEST',[{'pc':[True,True],'accepted':True,'meta':guidance()}],train_matrix=train_matrix())['contrast'])

    def test_posthoc_selection_does_not_change_loop_acceptance(self):
        selected={'selected_source':'initial','selected_step':0,'final_verification':{'personal_constraints':[False,True]}}
        e=find('R4','TEST',[{'pc':[True,True],'accepted':True,'meta':guidance()}],selected=selected,train_matrix=train_matrix())['r4'][0]
        self.assertIs(e['posthoc'],False)
        self.assertTrue(e['row']['accepted'])
        self.assertEqual(e['final']['personal_constraints'],[True,True])
        self.assertEqual(e['selected']['PC states (1-based order)'],[False,True])
        self.assertIn('not the post-hoc selection',markdown(e,'r4'))

    def test_ambiguous_selected_trial_remains_unknown(self):
        cp=checkpoint('R4',[{'pc':[True,True],'accepted':True,'meta':guidance()}])
        bundle={'checkpoints':[cp,copy.deepcopy(cp)],'selected':{'selected_source':'R4','selected_step':1}}
        found=find_examples(d.Run('/tmp/e','TEST','R4','id'),{'u':bundle},train_matrix=train_matrix())
        self.assertTrue(all(e['posthoc'] is None for e in found['r4']))

    def test_partition_and_strategy_binding(self):
        self.assertFalse(find('R0','TEST')['cascade'])
        self.assertFalse(find('R4','TRAIN')['cascade'])
        self.assertFalse(find('R2','TRAIN')['r2'])
        self.assertFalse(find('R3','TRAIN',[{'pc':[False,True]},{'pc':[True,True],'scope':'day','accepted':True}])['r3'])
        self.assertFalse(find('R4','TRAIN',[{'pc':[True,True],'accepted':True,'meta':guidance()}],train_matrix=train_matrix())['r4'])

    def test_markdown_retains_trajectory_and_states(self):
        e=find('R2','TEST')['r2'][0]
        summary=markdown(e,'r2')
        self.assertIn('| Attempt | Scope |',summary)
        self.assertIn('Candidate PC new violations',summary)
        self.assertIn('"PC states (1-based order)": [true, false]',summary)
        self.assertIn('"PC states (1-based order)": [false, true]',summary)
        self.assertNotIn('translated_plan',summary)

    def test_missing_intermediate_accepted_plan_cannot_prove_rollback(self):
        cp=checkpoint('R2',[{'pc':[False,True],'accepted':True},{'pc':[True,False]}])
        cp['repair_history'][1]['repair_attempt'].pop('accepted_plan_after')
        cp['repair_history'][2]['repair_attempt']['accepted_plan_after']={'version':0}
        self.assertFalse(find_examples(d.Run('/tmp/e','TEST','R2','id'),{'u':{'checkpoints':[cp]}})['r2'])

    def test_matrix_binding_requires_train_provenance_and_unchanged_content(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'matrix.csv'
            path.write_text('source_family,destination_family,support_count,regression_probability\ntrip_specification,monetary_budget,7,0.25\n')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            manifest={'output_sha256':digest,'input_matrices':[{'strategy':'R0','directory':'experiments/subset_train-r0/regression_matrix'}]}
            manifest_path=root/'matrix_manifest.json';manifest_path.write_text(json.dumps(manifest))
            run=d.Run(str(root),'TEST','R4','id');cp={'matrix':{'path':'matrix.csv','sha256':digest}}
            self.assertEqual(len(bound_train_matrix(run,cp)),1)
            manifest['input_matrices'][0]['directory']='experiments/subset_test-r0/regression_matrix'
            manifest_path.write_text(json.dumps(manifest))
            self.assertTrue(bound_train_matrix(run,cp).empty)
            path.write_text('changed')
            self.assertTrue(bound_train_matrix(run,cp).empty)

    def test_frozen_file_hash_allows_only_line_ending_change(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'input.csv';p.write_bytes(b'col\nvalue\n')
            expected=hashlib.sha256(b'col\r\nvalue\r\n').hexdigest()
            self.assertTrue(recorded_hash_matches(p,expected))
            p.write_bytes(b'col\nchanged\n')
            self.assertFalse(recorded_hash_matches(p,expected))


class ExampleCollectionTests(FixtureCase):
    def test_collection_never_uses_wrong_partition(self):
        found=collect(d.discover_runs())
        for key, examples in found.items():
            for e in examples:
                self.assertEqual(e['run'].partition,'TRAIN' if key=='cascade' else 'TEST')
                if key != 'cascade':
                    self.assertEqual(e['run'].strategy,{'r2':'R2','r3':'R3','r4':'R4','contrast':'R4'}[key])
