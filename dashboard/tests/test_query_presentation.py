"""Presentation contracts over saved fixtures; no scorer, provider or artifact writes."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest
from dashboard import data_loader as data
from dashboard.query_presentation import (presentation_trajectory, visible_rounds, attempt_label,
                                          constraint_history, message_delta, json_evidence)
from dashboard.components.itinerary_cards import align_diff, recorded_focus
from dashboard.tests.test_dashboard import FixtureCase, context


def plan(*activities):
    return [{'day': 1, 'activities': list(activities)}]


def activity(name='Museum', **kwargs):
    return dict(type='attraction', position=name, **kwargs)


class AlignmentTests(unittest.TestCase):
    def test_stable_id_changed_place_and_transfer(self):
        a = plan(activity(activity_id='a', transports={'cost': 2}))
        b = plan(activity('Palace', activity_id='a', transports={'cost': 3}))
        result = align_diff(a, b)
        self.assertEqual(result['status'], 'Aligned')
        self.assertEqual(result['changed activities'], 1)
        self.assertEqual({r['Field'] for r in result['changes']}, {'position', 'transports.cost'})

    def test_insert_delete_reorder_by_identity(self):
        a = plan(activity('A', activity_id='a'), activity('B', activity_id='b'))
        b = plan(activity('B', activity_id='b'), activity('C', activity_id='c'))
        fields = [r['Field'] for r in align_diff(a, b)['changes']]
        self.assertIn('Removed activity', fields)
        self.assertIn('Added activity', fields)
        self.assertIn('activity order (1-based)', fields)
        self.assertNotIn('position', fields)

    def test_unique_anchor_matches_reordering_not_positions(self):
        a = plan(activity('A'), activity('B'))
        result = align_diff(a, plan(activity('B'), activity('A')))
        self.assertEqual(result['changed activities'], 2)
        self.assertTrue(all(r['Field'] == 'activity order (1-based)' for r in result['changes']))

    def test_insert_remove_without_id_preserves_known_pairs(self):
        a = plan(activity('A'), activity('B', cost=2))
        b = plan(activity('X'), activity('A'), activity('B', cost=3))
        diff = align_diff(a, b)
        self.assertTrue(diff['status'].startswith('Partial'))
        self.assertIsNone(diff['changed activities'])
        self.assertTrue(any(r['Field'] == 'cost' and r['Before'] == 2 and r['After'] == 3 for r in diff['changes']))
        self.assertFalse(any(r['Field'] == 'position' for r in diff['changes']))
        self.assertTrue(any('Unmatched' in r['Field'] for r in align_diff(b, a)['changes']))

    def test_ambiguous_or_changed_venue_is_not_paired(self):
        for a, b in [(plan(activity('A')), plan(activity('B'))),
                     (plan(activity('A'), activity('A')), plan(activity('A'), activity('A', cost=2)))]:
            diff = align_diff(a, b)
            self.assertIsNone(diff['changed activities'])
            self.assertTrue(all(r['Alignment'] == 'Unavailable' for r in diff['changes']))

    def test_missing_multi_day_and_wrapper(self):
        self.assertIsNone(align_diff(None, [])['changed activities'])
        self.assertEqual(align_diff({'itinerary': plan(activity())}, plan(activity()))['changes'], [])
        multi = plan(activity()) + [{'day': 2, 'activities': [activity('B')]}]
        self.assertEqual(align_diff(multi, deepcopy(multi))['status'], 'Aligned')
        self.assertIn('ambiguous day', align_diff([{'activities': []}, {'activities': []}], [])['status'])

    def test_only_explicit_focus_locations(self):
        p = plan(activity())
        self.assertEqual(recorded_focus(p, {'editable_slots': [{'day': 0, 'activity_index': 0}]}).popitem()[1], (0, 0))
        self.assertEqual(recorded_focus(p, {'editable_slots': [{'day': 10, 'activity_index': 0}, {'day': 0, 'slot': 0}]}), {})

    def test_cards_long_multi_day_missing_fields_and_html_escape(self):
        script = """from dashboard.components.itinerary_cards import render
render([{'day':i,'activities':[{'position':'<script>alert(1)</script>','transports':[{'from':'A','to':'B','cost':2}]} for _ in range(25)]} for i in range(1,4)], 'Long itinerary', (0,0))
render(None, 'Missing')
render([{'day':1,'activities':[{}]}], 'Empty fields')
"""
        app = AppTest.from_string(script).run(timeout=60)
        self.assertFalse(app.exception)
        self.assertTrue(any('Inbound transfer' in m.value for m in app.markdown))
        self.assertTrue(any('&lt;script&gt;' in m.value for m in app.markdown))
        self.assertFalse(any('<script>alert' in m.value for m in app.markdown))
        self.assertTrue(any('qe-focus' in m.value for m in app.markdown))
        self.assertTrue(any('unavailable' in x.value for x in app.info))


class QueryPresentationTests(FixtureCase):
    def cp(self, strategy='R2'):
        return data.query_artifacts(context('TEST', strategy)['run'], 'fixture-0')['checkpoints'][0]

    def test_before_candidate_accepted_rejection_and_acceptance(self):
        cp = self.cp(); original = deepcopy(cp)
        t = presentation_trajectory(cp); first, second = t['rounds']
        self.assertFalse(first['accepted'])
        self.assertNotEqual(first['candidate_plan'], first['after_plan'])
        self.assertEqual(first['before_plan'], first['after_plan'])
        self.assertTrue(first['retention'])
        self.assertEqual(second['before_plan'], first['after_plan'])
        self.assertEqual(second['candidate_plan'], second['after_plan'])
        self.assertEqual(t['final_plan'], cp['final_accepted_plan'])
        self.assertEqual(cp, original)

    def test_missing_plan_and_missing_step_are_unavailable(self):
        cp = self.cp(); entry = cp['repair_history'][1]
        del entry['step']; del entry['repair_attempt']['step']
        del entry['repair_attempt']['candidate_plan']; del entry['repair_attempt']['accepted_plan_after']
        cp.pop('final_accepted_plan'); cp.pop('initial_raw_plan')
        t = presentation_trajectory(cp)
        self.assertIsNone(t['rounds'][0]['step'])
        self.assertIn('unavailable', attempt_label(t['rounds'][0]))
        self.assertIsNone(t['rounds'][0]['candidate_plan'])
        self.assertIsNone(t['rounds'][0]['after_plan'])
        self.assertIsNone(t['rounds'][0]['retention'])
        self.assertIsNone(t['final_plan'])

    def test_nonsequential_steps_and_filters(self):
        cp = self.cp()
        cp['repair_history'][1]['step'] = 10
        cp['repair_history'][2]['step'] = 70
        rows = presentation_trajectory(cp)['rounds']
        self.assertEqual([r['step'] for r in rows], [10, 70])
        filtered = visible_rounds(rows, 'fixture-0', 'R2', {'round':'70'})
        self.assertEqual(filtered[0]['ordinal'], 2)
        self.assertEqual(visible_rounds(rows, 'fixture-0', 'R2', {'allowed_steps':set()}), [])

    def test_history_pc_unknown_and_cs_message_sets(self):
        cp = self.cp(); cp['repair_history'][1]['verification']['personal_constraints'] = [True, None]
        t = presentation_trajectory(cp); pc, cs = constraint_history(t)
        self.assertEqual(pc[1]['Attempt 1 · record 1 (candidate)'], 'Unknown')
        self.assertIn('Final accepted', pc[0])
        self.assertIn('Saved messages', cs[0])
        self.assertEqual(message_delta({'commonsense_errors':['old']}, {'commonsense_errors':['new']}),
                         {'removed messages':['old'], 'introduced messages':['new']})
        self.assertIsNone(message_delta({}, {})['removed messages'])

    def test_initial_only_history_without_descriptors(self):
        cp=self.cp()
        cp['repair_history']=cp['repair_history'][:1]
        t=presentation_trajectory(cp)
        pc,cs=constraint_history(t)
        self.assertEqual(t['rounds'], [])
        self.assertEqual(pc[0]['Family'], 'unmapped')
        self.assertEqual(len(cs), 2)

    def test_redaction(self):
        payload = json.loads(json_evidence({'api_key':'secret-value', 'metadata':{'environment':{'TOKEN':'secret'}, 'total_tokens_delta':10}}))
        self.assertEqual(payload['api_key'], '[redacted]')
        self.assertEqual(payload['metadata']['environment'], '[redacted]')
        self.assertEqual(payload['metadata']['total_tokens_delta'], 10)

    def ui(self, strategy='R2'):
        return AppTest.from_string(f"from dashboard.components.query_explorer import render\nfrom dashboard.tests.test_dashboard import context\nc=context('TEST','{strategy}')\nrender(c['run'],'fixture-0',c['filters'])").run(timeout=60)

    def test_navigation_rejection_states_downloads_and_provenance(self):
        app = self.ui(); self.assertFalse(app.exception)
        next(b for b in app.button if b.label == 'Next →').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Rejected candidate' in x.value for x in app.error))
        self.assertEqual([x.label for x in app.tabs], ['Before', 'Candidate', 'Accepted after', 'What changed?'])
        self.assertTrue(any('R2 protection' in x.value for x in app.markdown))
        self.assertTrue(any(x.label == 'Download Before/Candidate/Accepted JSON' for x in app.get('download_button')))
        self.assertTrue(any(x.label == 'Provenance' for x in app.expander))
        next(b for b in app.button if b.label == 'Next →').click().run()
        self.assertTrue(next(b for b in app.button if b.label == 'Next →').disabled)
        next(b for b in app.button if b.label == '← Previous').click().run()
        self.assertTrue(any('Rejected candidate' in x.value for x in app.error))

    def test_arbitrary_navigation_count_and_filters(self):
        script = """from dashboard.components.query_explorer import navigation
rows=[{'ordinal':i,'step':i*10} for i in range(1,31)]
navigation(rows,'nav')
"""
        app = AppTest.from_string(script).run()
        self.assertEqual(len([b for b in app.button if b.label.startswith('Attempt')]), 30)
        next(b for b in app.button if b.label == 'Attempt 300').click().run()
        self.assertTrue(next(b for b in app.button if b.label == 'Next →').disabled)
        self.assertEqual(app.session_state['nav'], 30)

    def test_r3_scope_and_r4_selection(self):
        for strategy in ('R3','R4'):
            app=self.ui(strategy)
            next(b for b in app.button if b.label=='Next →').click().run()
            self.assertFalse(app.exception)
            if strategy=='R3':
                self.assertTrue(any('scheduled widening' in x.value for x in app.caption))
                scopes=next(x.value for x in app.dataframe if 'Scope' in x.value)
                self.assertEqual(scopes.Scope.tolist(), ['slot','day'])
            else:
                self.assertTrue(any('Post-hoc selected outcome' in x.value for x in app.subheader))
                self.assertTrue(any('R4 guidance' in x.value for x in app.markdown))
                self.assertTrue(any('Final accepted loop plan' in x.value for x in app.subheader))

    def test_independent_trials_and_export_binding(self):
        run=context('TEST','R4')['run']; bundle=data.query_artifacts(run,'fixture-0')
        second=deepcopy(bundle['checkpoints'][0]); second['matrix_run_id']='second-trial'
        second['repair_history'][1]['step']=77
        supplied=dict(bundle, checkpoints=bundle['checkpoints']+[second], checkpoint_paths=['first.json','second.json'])
        with patch.object(data,'query_artifacts',return_value=supplied):
            app=self.ui('R4')
            app.selectbox[0].select(1).run()
            self.assertFalse(app.exception)
            self.assertTrue(any(b.label=='Attempt 77' for b in app.button))
            next(b for b in app.button if b.label=='Attempt 77').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Attempt 77' in x.value for x in app.subheader))
            with patch.object(st, 'download_button', wraps=st.download_button) as downloads:
                next(b for b in app.button if b.label=='Attempt 77').click().run()
            payloads = {call.args[0]: call.args[1] for call in downloads.call_args_list}
            exported = json.loads(payloads['Download Before/Candidate/Accepted JSON'])
            self.assertEqual((exported['trial'], exported['step'], exported['query_uid']),
                             ('second-trial', 77, 'fixture-0'))
            self.assertEqual(exported['states']['Candidate']['plan'], second['repair_history'][1]['repair_attempt']['candidate_plan'])
            diff = json.loads(payloads['Download field diff JSON'])
            self.assertEqual(diff['comparison'], 'Before → Candidate')
            self.assertEqual(diff['trial'], 'second-trial')

    def test_missing_plans_ui_never_uses_selected_as_final(self):
        run=context('TEST','R4')['run']; bundle=deepcopy(data.query_artifacts(run,'fixture-0'))
        cp=bundle['checkpoints'][0]
        cp.pop('final_accepted_plan'); cp.pop('initial_raw_plan')
        cp['repair_history'][1]['repair_attempt'].pop('candidate_plan')
        cp['repair_history'][1]['repair_attempt'].pop('accepted_plan_after')
        cp['repair_history'][1]['accepted']=None
        with patch.object(data,'query_artifacts',return_value=bundle):
            app=self.ui('R4')
            next(b for b in app.button if b.label=='Next →').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Itinerary unavailable' in x.value for x in app.info))
            self.assertTrue(any('Post-hoc selected itinerary' in x.value for x in app.markdown))
            self.assertFalse(any(x.label=='Download final itinerary' for x in app.get('download_button')))
