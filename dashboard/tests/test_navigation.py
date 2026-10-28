"""Page partition isolation and local filter contracts."""
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from dashboard import data_loader as d, metrics
from dashboard.tests.test_dashboard import FixtureCase, context


class NavigationTests(FixtureCase):
    def page(self, page):
        # Deliberately inject stale TRAIN filters; page entry points ignore them.
        return AppTest.from_string(f"from dashboard.tests.test_dashboard import context\nfrom dashboard.pages.{page} import render\nctx = context('TRAIN', 'R0')\nctx['filters'].update(round='999', outcome='Rejected')\nrender(ctx)").run(timeout=90)

    def test_actual_top_navigation_names_order_and_stable_routes(self):
        from pathlib import Path
        expected = ['Overview', 'Query Explorer', 'TRAIN set', 'TEST set', 'Ablations & Comparisons', 'Strategy-Specific']
        # Streamlit exposes the default Overview page at the root URL.
        routes = ['', 'query_explorer', 'train_interdependencies', 'test_results', 'ablation_comparisons', 'strategy_details']
        with patch('streamlit.navigation', wraps=st.navigation) as navigation:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=90)
        self.assertFalse(app.exception)
        self.assertEqual([page.title for page in navigation.call_args.args[0]], expected)
        self.assertEqual([page.url_path for page in navigation.call_args.args[0]], routes)
        self.assertEqual(navigation.call_args.kwargs['position'], 'top')
        self.assertNotIn('dashboard.pages.representative_examples', __import__('sys').modules)
        self.assertFalse((Path(__file__).resolve().parents[1] / 'pages/representative_examples.py').exists())

    def test_page_headings_match_navigation_names(self):
        for module, heading in [('overview','Overview'), ('query_explorer','Query Explorer'),
                                ('train_interdependencies','TRAIN set'), ('test_results','TEST set'),
                                ('ablation_comparisons','Ablations & Comparisons'), ('strategy_details','Strategy-Specific')]:
            with self.subTest(page=module):
                app = self.page(module)
                self.assertFalse(app.exception)
                self.assertEqual(app.title[0].value, heading)

    def test_overview_has_no_manual_compatibility_inspector(self):
        app = self.page('overview')
        self.assertFalse(app.exception)
        self.assertFalse(any(x.value == 'Comparison safeguards' for x in app.subheader))
        self.assertFalse(any(x.label == 'Runs to check for comparison' for x in app.multiselect))
        self.assertFalse(any('Select at least two runs to inspect compatibility.' in x.value for x in app.caption))
        self.assertTrue(any(x.label == 'Run to inspect' for x in app.selectbox))

    def test_test_page_ignores_stale_train_and_proposal_filters(self):
        app = self.page('test_results')
        self.assertFalse(app.exception)
        self.assertEqual([t.label for t in app.tabs], ['Personal Constraints (PC)', 'Commonsense Constraints (CS)', 'Repair Process / Efficiency', 'ChinaTravel Evaluation'])
        saved = d.test_table(context('TEST', 'R0')['run'], 'table1_pc')
        shown = app.dataframe[0].value.set_index('Metric')
        self.assertEqual(float(shown.loc['Avg PC passed: final', 'All R0']), float(saved.loc[saved.metric == metrics.PC_REPORT_ROWS['Avg PC passed: final'], 'All'].iloc[0]))
        self.assertFalse(any(x.label == 'Partition' for x in app.selectbox))

    def test_train_always_uses_development_matrices_and_local_filters(self):
        original = d.matrix_table
        seen = []
        def matrix(run):
            seen.append(run)
            return original(run)
        with patch.object(d, 'matrix_table', side_effect=matrix):
            app = self.page('train_interdependencies')
        self.assertFalse(app.exception)
        self.assertTrue(seen)
        self.assertTrue(all(r.partition == 'TRAIN' and r.strategy != 'R4' for r in seen))
        self.assertFalse(app.sidebar.slider)
        next(x for x in app.selectbox if x.label == 'Repaired family').select('trip_specification').run(timeout=90)
        next(x for x in app.slider if x.label == 'Minimum matrix support').set_value(0).run(timeout=90)
        self.assertFalse(app.exception)
        cells = next(x.value for x in app.dataframe if 'source_family' in x.value)
        self.assertTrue(cells.source_family.eq('trip_specification').all())

    def test_details_binds_test_even_with_train_context(self):
        with patch('dashboard.pages.strategy_details.strategy') as render:
            app = self.page('strategy_details')
        self.assertFalse(app.exception)
        self.assertEqual(render.call_args.args[0].partition, 'TEST')
        self.assertFalse(any(x.label == 'Partition' for x in app.selectbox))

    def test_query_partition_is_local_and_defaults_test(self):
        for page, prefix in [('query_explorer', 'query')]:
            app = self.page(page)
            self.assertFalse(app.exception)
            partition = next(x for x in app.selectbox if x.label == 'Partition')
            self.assertEqual(partition.value, 'TEST')
            partition.select('TRAIN').run(timeout=90)
            self.assertFalse(app.exception)
            self.assertTrue(any('TRAIN ·' in x.value for x in app.caption))
            self.assertNotIn('dataset', app.session_state.filtered_state)
            self.assertEqual(app.session_state[f'{prefix}_partition'], 'TRAIN')

    def test_switching_pages_preserves_only_page_local_state(self):
        script = """import streamlit as st
from dashboard import data_loader as d
from dashboard.pages import query_explorer, test_results, train_interdependencies, strategy_details
page = st.radio('Test navigation', ['query', 'test', 'train', 'details'])
{'query': query_explorer, 'test': test_results, 'train': train_interdependencies, 'details': strategy_details}[page].render({'runs': d.discover_runs()})
"""
        app = AppTest.from_string(script).run(timeout=90)
        next(x for x in app.selectbox if x.label == 'Partition').select('TRAIN').run(timeout=90)
        next(x for x in app.selectbox if x.label == 'Round').select('2').run(timeout=90)
        for page in ['test', 'train', 'details', 'test']:
            app.radio[0].set_value(page).run(timeout=90)
            self.assertFalse(app.exception)
            self.assertFalse(any(x.label == 'Partition' for x in app.selectbox))
            if page == 'test':
                self.assertIn('All R0', app.dataframe[0].value.columns)
            if page == 'details':
                self.assertTrue(any('TEST ·' in x.value for x in app.caption))

    def test_missing_test_does_not_substitute_train(self):
        runs = [r for r in d.discover_runs() if r.partition == 'TRAIN']
        with patch.object(d, 'discover_runs', return_value=runs):
            app = AppTest.from_string("from dashboard import data_loader as d\nfrom dashboard.pages.strategy_details import render\nrender({'runs': d.discover_runs()})").run(timeout=90)
        self.assertFalse(app.exception)
        self.assertTrue(any('TEST runs: Unavailable' in x.value for x in app.info))
