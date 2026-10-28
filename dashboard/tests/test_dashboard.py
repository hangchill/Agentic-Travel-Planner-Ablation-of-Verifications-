"""Offline contract and UI tests over synthetic persisted fixtures. No scoring/model calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from dashboard import data_loader as d
from dashboard import metrics as m
from dashboard.tests.fixtures import repository, Repository


def context(partition='TRAIN', strategy='R0'):
    runs = d.discover_runs()
    run = next(r for r in runs if r.partition == partition and r.strategy == strategy)
    a = m.attempt_frame(d.attempts(run), d.analysis_table(run, 'attempt_level'))
    q = d.analysis_table(run, 'query_level')
    if q.empty:
        q = pd.DataFrame({'query_uid': d.read_json(Path(run.path) / 'run_manifest.json')['query_uids']})
    return {'runs': runs, 'run': run, 'a': a, 'a_full': a, 'q': q,
            'test_q': d.test_table(run, 'per_query'),
            'filters': {'phase': 'All', 'round': 'All', 'uid': '', 'family': 'All', 'outcome': 'All', 'minimum': 5}}


class FixtureCase(unittest.TestCase):
    def setUp(self):
        fixture = repository()
        guard = patch.multiple(d, ROOT=fixture.root, ANALYSIS=fixture.analysis, TEST_TABLES=fixture.reporting)
        guard.start()
        self.addCleanup(guard.stop)


class DiscoveryTests(FixtureCase):
    def test_partition_manifest_and_folder(self):
        self.assertEqual(d.identify_partition({'split_query_source': 'subset_test'}, 'run'), 'TEST')
        self.assertEqual(d.identify_partition({}, 'subset_train-r3-new'), 'TRAIN')
        self.assertEqual(d.identify_partition({}, 'contest'), 'UNKNOWN')
        with self.assertRaises(ValueError):
            d.identify_partition({'split_query_source': 'subset_test'}, 'subset_train-r0')

    def test_discovery_uses_manifests_not_names(self):
        runs = d.discover_runs()
        self.assertEqual({(r.partition, r.strategy) for r in runs}, set(repository().manifests))
        self.assertTrue(any('final_test' in r.path for r in runs))

    def test_provenance_never_substitutes_train_for_test(self):
        train, test = context('TRAIN', 'R0')['run'], context('TEST', 'R0')['run']
        self.assertEqual(d.analysis_folder(train), repository().analysis / 'train/R0')
        self.assertEqual(d.analysis_folder(test), repository().analysis / 'test/R0')
        self.assertNotEqual(d.analysis_folder(train), d.analysis_folder(test))

    def test_generated_test_binding(self):
        for strategy in d.STRATEGIES:
            run = context('TEST', strategy)['run']
            ids = d.read_json(Path(run.path) / 'run_manifest.json')['query_uids']
            self.assertEqual(len(d.test_table(run, 'per_query')), len(ids))
            self.assertIsNone(d.test_folder(d.Run(run.path, 'TRAIN', strategy, run.run_id)))

    def test_missing_files_are_unavailable(self):
        with tempfile.TemporaryDirectory() as p:
            self.assertEqual(d.read_json(Path(p) / 'missing.json'), {})
            self.assertTrue(d.read_csv(Path(p) / 'missing.csv').empty)


class MetricTests(FixtureCase):
    def test_team_summary_parity_all_generated_tables(self):
        # Calls summary helpers only: scoring must never occur in dashboard rendering.
        from scripts.result_analysis import build_test_result_tables as team
        with patch.object(team, 'score_plans', side_effect=AssertionError('Scoring forbidden')):
            for s in d.STRATEGIES:
                ctx = context('TEST', s)
                for kind, filename in [('pc', 'table1_pc'), ('cs', 'table2_cs'),
                                       ('process', 'table3_repair_process'), ('benchmark', 'table4_eval_exp')]:
                    got = m.team_table(ctx['test_q'], kind).fillna('').astype(str)
                    saved = d.test_table(ctx['run'], filename).fillna('').astype(str)
                    for col in ['Easy', 'Medium', 'Human', 'All']:
                        for x, y in zip(got[col], saved[col]):
                            try:
                                self.assertAlmostEqual(float(x), float(y))
                            except ValueError:
                                self.assertEqual(x, y)
                    self.assertEqual(list(got.metric), list(saved.metric))

    def test_filtered_team_summary_uses_subset(self):
        q = context('TEST', 'R2')['test_q'].iloc[:2]
        t = m.team_table(q, 'pc')
        self.assertEqual(t.loc[t.metric == 'Queries (n)', 'All'].iloc[0], 2)

    def test_unknown_state_denominator(self):
        self.assertEqual(m.state_rate([True, False, None]), .5)
        self.assertIsNone(m.state_rate([None]))

    def test_cs_strict_threshold_and_missing_costs(self):
        q = pd.DataFrame({'cs_total': [20, 20], 'cs_passed_initial': [15, 15],
                          'cs_passed_final': [17, 18]})
        rows = m.pc_cs_extras(q, 'cs').set_index('metric')
        self.assertEqual(rows.loc['Final plans with >85% CS passed (%)', 'value'], 50)
        process = m.process_summary(pd.DataFrame({'tokens_spent': [None, 100]}))
        self.assertEqual(process.iloc[0]['mean'], 100)
        self.assertEqual(process.iloc[0]['valid N'], 1)

    def test_zero_support_distinct_from_observed_zero(self):
        f = pd.DataFrame([{'perspective': 'candidate', 'source_family': 'a', 'destination_family': 'b', 'support_count': 0, 'regression_count': 0},
                          {'perspective': 'candidate', 'source_family': 'b', 'destination_family': 'a', 'support_count': 5, 'regression_count': 0}])
        cells = m.pool_saved_cells([f])
        self.assertTrue(pd.isna(cells.iloc[0].regression_rate))
        self.assertEqual(cells.iloc[1].regression_rate, 0)
        coverage = m.matrix_coverage(cells)
        self.assertEqual(coverage['coverage'], .5)
        self.assertEqual(coverage['possible cells'], 2)

    def test_pooling_uses_support_weighted_counts(self):
        f = pd.DataFrame([{'perspective': 'candidate', 'source_family': 'a', 'destination_family': 'b', 'support_count': 5, 'regression_count': 2}])
        g = f.copy(); g['support_count'] = 10; g['regression_count'] = 1
        self.assertEqual(m.pool_saved_cells([f, g]).iloc[0].regression_rate, .2)

    def test_localisation_missing_evidence_not_success(self):
        a = pd.DataFrame({'step': [1, 1], 'query_uid': ['a', 'b'],
                          'localisation_success': [True, None], 'localisation_failure': [False, True]})
        s = m.localisation_summary(a).iloc[0]
        self.assertEqual(s['logged successes'], 1)
        self.assertEqual(s['success evidence N'], 1)
        self.assertEqual(s['explicit failures'], 1)

    def test_protected_candidate_rejection(self):
        a = pd.DataFrame({'query_uid': ['a', 'b', 'c'], 'protected_regression_count': [1, 1, None], 'rejected': [True, False, False]})
        row = m.protection_summary(a).iloc[0]
        self.assertEqual(row['harmful candidates'], 2)
        self.assertEqual(row['harmful rejection rate (%)'], 50)
        self.assertEqual(row['harmful candidates accepted'], 1)

    def test_scope_transitions_and_success(self):
        a = pd.DataFrame({'query_uid': ['a'] * 3, 'repair_strategy': ['R3'] * 3,
                          'step': [1, 2, 3], 'editable_scope': ['slot', 'day', 'plan'],
                          'targeted_fixed_count': [0, 1, 1]})
        q, cohort = m.scope_summary(a)
        self.assertEqual(q.iloc[0]['highest scope'], 'plan')
        self.assertEqual(q.iloc[0]['escalations'], 2)
        self.assertEqual(q.iloc[0]['slot → day'], 1)
        self.assertEqual(cohort['successful target repairs'].sum(), 2)

    def test_guidance_nested_support_and_no_guidance(self):
        self.assertEqual(m.guidance_status({}), 'no logged relationship')
        self.assertEqual(m.guidance_status({'commonsense_source_risks': [{'support_count': 0}]}), 'unsupported')
        metadata = {'risk_target_ranking': [{'destination_risks': [{'support_count': 10}]}]}
        self.assertEqual(m.guidance_status(metadata), 'supported')
        self.assertEqual(m.guidance_support(metadata), [10])

    def test_filters_are_literal_and_candidate_based(self):
        ctx = context('TEST', 'R2'); f = dict(ctx['filters'], outcome='Rejected')
        a = m.filter_attempts(ctx['a'], f)
        self.assertTrue(a.rejected.all())
        self.assertTrue(m.filter_attempts(ctx['a'], dict(f, uid='[')).empty)
        q = m.filter_queries(ctx['test_q'], a, f)
        self.assertTrue(set(q.query_uid) <= set(a.query_uid))

    def test_trajectory_keeps_rejected_candidate_separate(self):
        initial = {'personal_constraints': [True, False], 'commonsense_errors': [], 'translated_plan': {'v': 1}}
        bad = {'personal_constraints': [False, True], 'commonsense_errors': ['x'], 'translated_plan': {'v': 2}}
        cp = {'query_uid': 'a', 'repair_history': [
            {'step': 0, 'verification': initial},
            {'step': 1, 'accepted': False, 'verification': bad, 'repair_attempt': {}},
            {'step': 2, 'accepted': True, 'verification': initial, 'repair_attempt': {}}]}
        t = m.trajectory(cp)
        self.assertEqual(t['rounds'][0]['candidate'], bad)
        self.assertEqual(t['rounds'][0]['after'], initial)
        self.assertEqual(t['final'], initial)
        self.assertTrue(t['rounds'][0]['changed_team_definition'])
        self.assertFalse(t['rounds'][1]['changed_team_definition'])

    def test_r4_trial_separate_from_selection(self):
        run = context('TEST', 'R4')['run']
        b = next(iter(d.checkpoints(run).values()))
        self.assertTrue(b['checkpoints'])
        self.assertTrue(b['selected'])
        self.assertNotEqual(b['checkpoints'][0].get('matrix_run_id'), b['selected'].get('matrix_run_id'))

    def test_candidate_example_cascade_requires_target_fix(self):
        a = pd.DataFrame({'targeted_fixed_count': [0, 1], 'newly_violated_count': [1, 1]})
        self.assertEqual(len(m.candidate_examples(a, 'Cascading regression')), 1)

    def test_comparison_mixed_partitions_and_initial_plans(self):
        run = d.Run('/tmp/x', 'TEST', 'R2', 'x')
        manifest = {'query_uids': ['a'], 'model_identifier': 'x', 'sampling_settings': {}, 'max_steps': 6,
                    'language': 'en', 'oracle_translation': True, 'implementation_hash': 'h', 'seed': 1}
        self.assertEqual(m.comparison_issues([run, run], [manifest, manifest], [{'a': 'h'}, {'a': 'h'}]), [])
        issues = m.comparison_issues([run, d.Run('/tmp/y', 'TRAIN', 'R0', 'y')], [manifest, manifest], [{'a': 'x'}, {'a': 'y'}])
        self.assertTrue(any('different dataset partitions' in x for x in issues))
        self.assertTrue(any('Initial plans differ' in x for x in issues))


class UISmokeTests(FixtureCase):
    def setUp(self):
        super().setUp()
        from scripts.result_analysis import build_test_result_tables as team
        for name in ('score_plans', 'build_queries'):
            guard = patch.object(team, name, side_effect=AssertionError('Dashboard must not score plans'))
            guard.start()
            self.addCleanup(guard.stop)

    def test_actual_app_and_invalid_combination(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=90)
        self.assertFalse(app.exception)
        self.assertFalse(app.sidebar.selectbox)
        self.assertFalse(any('Repair-analysis explorer' in x.value for x in app.title))

    def test_all_pages_fixture_data(self):
        from streamlit.testing.v1 import AppTest
        for page, partition, strategy in [
            ('train_interdependencies', 'TRAIN', 'R0'), ('test_results', 'TEST', 'R2'),
            ('test_results', 'TEST', 'R3'), ('test_results', 'TEST', 'R4'),
            ('test_results', 'TEST', 'R0'), ('strategy_details', 'TRAIN', 'R1'),
            ('strategy_details', 'TEST', 'R2'), ('strategy_details', 'TEST', 'R3'),
            ('strategy_details', 'TEST', 'R4'), ('query_explorer', 'TEST', 'R2'),
            ('query_explorer', 'TEST', 'R4')]:
            with self.subTest(page=page, strategy=strategy):
                script = f'from dashboard.tests.test_dashboard import context\nfrom dashboard.pages.{page} import render\nrender(context({partition!r}, {strategy!r}))'
                app = AppTest.from_string(script).run(timeout=90)
                self.assertFalse(app.exception, str(app.exception))




class AdditionalDerivationTests(FixtureCase):
    def test_saved_matrix_eligibility_not_recomputed(self):
        c = pd.DataFrame({'perspective': ['candidate'] * 4, 'eligible': [True, True, False, True],
                          'is_single_target': [True, True, True, False],
                          'source_family': ['a', 'a', 'a', 'commonsense_repair'],
                          'query_uid': ['x', 'x', 'y', 'z'], 'step': [1, 1, 2, 3]})
        self.assertEqual(m.eligible_matrix_attempts(c, 'candidate'), 1)
        self.assertIsNone(m.eligible_matrix_attempts(pd.DataFrame(), 'candidate'))

    def test_plan_preservation_verifies_equality(self):
        cp = {'initial_raw_plan': [1], 'repair_history': [{},
              {'step': 1, 'accepted': False, 'repair_attempt': {'accepted_plan_after': [1]}},
              {'step': 2, 'accepted': False, 'repair_attempt': {'accepted_plan_after': [2]}}]}
        rows = m.rollback_preservation({'x': {'checkpoints': [cp]}})
        self.assertEqual(rows['prior accepted plan preserved'].tolist(), [True, False])

    def test_complete_counter_sums(self):
        a = pd.DataFrame({'query_uid': ['x', 'x'], 'model_calls': [2, None], 'verification_count': [1, 1]})
        row = m.round_counters(a).iloc[0]
        self.assertTrue(pd.isna(row.model_calls))
        self.assertEqual(row.verification_count, 2)

    def test_logged_budget_exhaustion_not_inferred_from_rounds(self):
        q = pd.DataFrame({'stop_reason': ['repair_budget_exhausted', 'verification_passed', None], 'rounds': [1, 6, 6]})
        row = m.process_summary(q).iloc[-1]
        self.assertEqual(row['count'], 1)
        self.assertEqual(row['percent'], 50)
        self.assertEqual(row['valid N'], 2)


class FilteredUITests(FixtureCase):
    def test_filtered_test_page_reuses_team_functions(self):
        from streamlit.testing.v1 import AppTest
        script = """from dashboard.tests.test_dashboard import context
from dashboard.pages.test_results import render
from dashboard.metrics import filter_attempts, filter_queries
ctx = context('TEST', 'R2')
ctx['filters']['round'] = '2'
ctx['filters']['outcome'] = 'Accepted'
ctx['a'] = filter_attempts(ctx['a'], ctx['filters'])
ctx['test_q'] = filter_queries(ctx['test_q'], ctx['a'], ctx['filters']).iloc[:3]
render(ctx)
"""
        app = AppTest.from_string(script).run(timeout=90)
        self.assertFalse(app.exception)

    def test_r2_examples_require_verified_preservation(self):
        a = pd.DataFrame({'query_uid': ['x'], 'step': [1], 'protected_regression_count': [1], 'rejected': [True]})
        self.assertTrue(m.candidate_examples(a, 'R2 protection').empty)
        evidence = pd.DataFrame({'query_uid': ['x'], 'step': [1], 'prior accepted plan preserved': [True]})
        self.assertEqual(len(m.candidate_examples(a, 'R2 protection', preservation=evidence)), 1)

    def test_scope_percent_uses_declared_cohort_and_no_hidden_transition(self):
        a = pd.DataFrame({'query_uid': ['a', 'a'], 'repair_strategy': ['R3', 'R3'],
                          'step': [1, 3], 'editable_scope': ['slot', 'plan'], 'targeted_fixed_count': [0, 1]})
        q, cohort = m.scope_summary(a, cohort_size=2)
        self.assertEqual(cohort.iloc[0]['queries reaching (%)'], 50)
        self.assertEqual(q.iloc[0]['escalations'], 0)
        self.assertTrue(m.scope_round_summary(a).empty)


if __name__ == '__main__':
    unittest.main()
