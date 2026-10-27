"""Future-run loading, provenance and refresh contracts using isolated fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard import data_loader as d, metrics as m
from dashboard.tests.fixtures import Repository

APP = Path(__file__).resolve().parents[1] / 'app.py'


class FutureRefreshTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(size=7, steps=(2, 4, 9))
        self.addCleanup(self.repo.close)
        guard = patch.multiple(d, ROOT=self.repo.root, ANALYSIS=self.repo.analysis, TEST_TABLES=self.repo.reporting)
        guard.start()
        self.addCleanup(guard.stop)
        from scripts.result_analysis import build_test_result_tables as team
        for name in ('score_plans', 'build_queries'):
            forbidden = patch.object(team, name, side_effect=AssertionError('No evaluation in dashboard'))
            forbidden.start()
            self.addCleanup(forbidden.stop)

    def run_for(self, partition='TEST', strategy='R0'):
        return next(r for r in d.discover_runs() if r.partition == partition and r.strategy == strategy)

    def availability(self):
        runs = d.discover_runs()
        statuses = {r: {'reporting': bool(d.test_folder(r)), 'diagnostics': bool(d.analysis_folder(r)),
                        'queries': len(d.read_json(Path(r.path) / 'run_manifest.json')['query_uids'])} for r in runs}
        return m.availability_summary(runs, statuses).set_index('strategy')

    def test_all_strategies_and_live_availability(self):
        self.repo.write_reporting(['R2', 'R3', 'R4'])
        before = self.availability()
        self.assertFalse(before.loc['R0', 'common TEST reporting available'])
        self.assertFalse(before.loc['R1', 'common TEST reporting available'])
        script = 'from dashboard.tests.test_dashboard import context\nfrom dashboard.pages.overview import render\nrender(context())'
        app = AppTest.from_string(script).run(timeout=60)
        self.assertFalse(app.exception)
        self.assertFalse(app.dataframe[0].value.set_index('strategy').loc['R1', 'common TEST reporting available'])
        self.repo.write_reporting()
        app.run(timeout=60)
        self.assertFalse(app.exception)
        self.assertTrue(app.dataframe[0].value['common TEST reporting available'].all())
        for strategy in d.STRATEGIES:
            self.assertTrue(self.availability().loc[strategy, 'TEST run available'])
            self.assertIsNotNone(d.test_folder(self.run_for(strategy=strategy)))

    def test_arbitrary_cohort_sizes(self):
        for size in (1, 11, 47):
            fixture = Repository(size=size, strategies=('R1',))
            try:
                run = next(r for r in d.discover_runs(fixture.root) if r.partition == 'TEST')
                folder = d.test_folder(run, fixture.reporting)
                self.assertIsNotNone(folder)
                q = d.read_csv(folder / 'per_query.csv')
                table = m.team_table(q, 'pc')
                self.assertEqual(table.loc[table.metric == 'Queries (n)', 'All'].iloc[0], size)
            finally:
                fixture.close()

    def test_round_and_support_controls_derive_from_data(self):
        app = AppTest.from_string("from dashboard import data_loader as d\nfrom dashboard.pages.query_explorer import render\nrender({'runs': d.discover_runs()})").run(timeout=60)
        self.assertFalse(app.exception)
        rounds = next(x for x in app.selectbox if x.label == 'Round')
        self.assertEqual(rounds.options, ['All', '2', '4', '9'])
        app = AppTest.from_string("from dashboard import data_loader as d\nfrom dashboard.pages.train_interdependencies import render\nrender({'runs': d.discover_runs()})").run(timeout=60)
        support = next(x for x in app.slider if x.label == 'Minimum matrix support')
        self.assertGreater(support.max, 500)
        support.set_value(int(support.max)).run(timeout=60)
        self.assertFalse(app.exception)
        self.assertEqual(m.observed_rounds(pd.DataFrame({'step': [17, 1, 17, None]})), [1, 17])
        self.assertEqual(m.matrix_support_limit([pd.DataFrame()], [[2200]]), 2200)

    def test_empty_rounds_and_support_are_safe(self):
        self.assertEqual(m.observed_rounds(pd.DataFrame()), [])
        self.assertEqual(m.matrix_support_limit([]), 0)
        with patch.object(d, 'attempts', return_value=[]), patch.object(d, 'checkpoints', return_value={}), patch.object(d, 'matrix_table', return_value=pd.DataFrame()):
            app = AppTest.from_string("from dashboard import data_loader as d\nfrom dashboard.pages.query_explorer import render\nrender({'runs': d.discover_runs()})").run(timeout=60)
            self.assertFalse(app.exception)
            self.assertEqual(next(x for x in app.selectbox if x.label == 'Round').options, ['All'])
            train = AppTest.from_string("from dashboard import data_loader as d\nfrom dashboard.pages.train_interdependencies import render\nrender({'runs': d.discover_runs()})").run(timeout=60)
            self.assertTrue(train.slider[0].disabled)

    def test_train_and_test_diagnostics_coexist(self):
        train, test = self.run_for('TRAIN'), self.run_for('TEST')
        train_path = d.analysis_folder(train) / 'query_level.csv'
        train_hash = hashlib.sha256(train_path.read_bytes()).hexdigest()
        test_path = d.analysis_folder(test) / 'query_level.csv'
        q = d.read_csv(test_path); q['refreshed_value'] = 123
        q.to_csv(test_path, index=False)
        self.assertEqual(d.analysis_table(test, 'query_level').refreshed_value.iloc[0], 123)
        self.assertNotIn('refreshed_value', d.analysis_table(train, 'query_level'))
        self.assertEqual(hashlib.sha256(train_path.read_bytes()).hexdigest(), train_hash)

    def test_explicit_structure_preferred_and_legacy_fallback_is_bound(self):
        test, train = self.run_for(), self.run_for('TRAIN')
        legacy = self.repo.analysis / 'R0'
        shutil.copytree(self.repo.analysis / 'train/R0', legacy)
        self.assertEqual(d.analysis_folder(test), self.repo.analysis / 'test/R0')
        shutil.rmtree(self.repo.analysis / 'test/R0')
        self.assertIsNone(d.analysis_folder(test))  # Never accept legacy TRAIN for TEST.
        self.assertIsNotNone(d.analysis_folder(train))
        shutil.rmtree(self.repo.analysis / 'train/R0')
        self.assertEqual(d.analysis_folder(train), legacy)

    def test_reporting_rejects_wrong_path_population_strategy_and_missing_files(self):
        run = self.run_for()
        path = self.repo.reporting / 'R0/per_query.csv'
        original = d.read_csv(path)
        for bad in [original.assign(query_uid='duplicate'), original.assign(repair_strategy='R1'), original.iloc[:-1]]:
            bad.to_csv(path, index=False)
            self.assertIsNone(d.test_folder(run))
        original.to_csv(path, index=False)
        wrong = d.Run(str(self.repo.root / 'experiments/other'), run.partition, run.strategy, run.run_id)
        self.assertIsNone(d.test_folder(wrong))
        (self.repo.reporting / 'R0/table2_cs.csv').unlink()
        self.assertIsNone(d.test_folder(run))

    def test_partial_readme_regeneration_remains_guarded(self):
        self.repo.write_reporting(['R1'])
        self.assertIsNotNone(d.test_folder(self.run_for(strategy='R1')))
        folder, reason = d.reporting_binding(self.run_for(strategy='R2'))
        self.assertIsNone(folder)
        self.assertIn('Regenerate all reporting runs together', reason)
        self.repo.write_reporting()
        self.assertIsNotNone(d.test_folder(self.run_for(strategy='R2')))

    def test_provenance_does_not_claim_identity_means_freshness(self):
        run = self.run_for()
        rows = d.provenance_rows(run).set_index('artifact')
        self.assertEqual(rows.loc['Common TEST reporting', 'source freshness'], 'Source freshness cannot be cryptographically verified.')
        self.assertTrue(pd.isna(rows.loc['Common TEST reporting', 'generation timestamp']))
        self.assertIn('listed files only', rows.loc['Strategy diagnostics', 'source freshness'])
        self.assertEqual(rows.loc['Strategy diagnostics', 'query population/count'], 7)
        app = AppTest.from_string('from dashboard.tests.test_dashboard import context\nfrom dashboard.pages.overview import render\nrender(context())').run(timeout=60)
        self.assertTrue(any(w.value == 'Source freshness cannot be cryptographically verified.' for w in app.warning))

    def test_refresh_updates_loaded_values_and_downloads(self):
        run = self.run_for()
        path = self.repo.reporting / 'R0/per_query.csv'
        script = """import streamlit as st
from dashboard import data_loader as d
from dashboard.components.common import table
run = next(r for r in d.discover_runs() if r.partition == 'TEST' and r.strategy == 'R0')
if st.button('Refresh local data'):
    st.cache_data.clear()
    st.rerun()
table(d.test_table(run, 'per_query'), 'refreshed queries')
"""
        app = AppTest.from_string(script).run(timeout=60)
        self.assertEqual(app.dataframe[0].value.pc_passed_final.iloc[0], 2)
        q = d.read_csv(path); q['pc_passed_final'] = 1; q.to_csv(path, index=False)
        app.button[0].click().run(timeout=60)
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.pc_passed_final.iloc[0], 1)
        # Download content is built from the same refreshed frame, without a static snapshot.
        with patch('dashboard.components.common.st.download_button') as download, patch('dashboard.components.common.st.dataframe'):
            from dashboard.components.common import table
            table(d.test_table(run, 'per_query'), 'download check')
            csv = download.call_args.args[1].decode()
            self.assertEqual(pd.read_csv(__import__('io').StringIO(csv)).pc_passed_final.iloc[0], 1)

    def test_discovery_excludes_invalid_and_nested_archives(self):
        nested = self.repo.root / 'experiments/archive/old'
        nested.mkdir(parents=True)
        (nested / 'run_manifest.json').write_text(json.dumps({'run_id': 'old'}))
        malformed = self.repo.root / 'experiments/incomplete'
        malformed.mkdir(); (malformed / 'run_manifest.json').write_text('{}')
        self.assertEqual(len(d.discover_runs()), len(self.repo.manifests))

    def test_manifest_population_change_invalidates_checkpoint_bundle(self):
        run = self.run_for()
        old = d.checkpoints(run)
        manifest_path = Path(run.path) / 'run_manifest.json'
        manifest = d.read_json(manifest_path); manifest['query_uids'] = manifest['query_uids'][:1]
        manifest_path.write_text(json.dumps(manifest))
        self.assertEqual(len(old), 7)
        self.assertEqual(len(d.checkpoints(run)), 1)

    def test_regenerated_common_tables_and_figures_update(self):
        script = """import streamlit as st
from dashboard.tests.test_dashboard import context
from dashboard.pages.test_results import render
if st.button('Refresh local data'):
    st.cache_data.clear()
    st.rerun()
render(context('TEST', 'R0'))
"""
        app = AppTest.from_string(script).run(timeout=60)
        self.assertFalse(app.exception)
        def chart_y(app):
            import base64
            import numpy as np
            y = json.loads(app.get('plotly_chart')[0].proto.spec)['data'][0]['y']
            return np.frombuffer(base64.b64decode(y['bdata']), dtype=y['dtype']).tolist() if isinstance(y, dict) else y
        baseline_round_y = chart_y(app)
        primary = app.dataframe[0].value.set_index('Metric')
        self.assertEqual(float(primary.loc['Avg PC passed: final', 'All R0']), 2)
        rows, _ = self.repo.rows[('TEST', 'R0')]
        for row in rows:
            row.update(pc_passed_final=1, pc_share_final=.5, pc_failed_final=1,
                       pc_passed_final_excl_named=1, pc_failed_kinds_final='Days / people count')
        self.repo.write_reporting()
        app.button[0].click().run(timeout=60)
        self.assertFalse(app.exception)
        primary = app.dataframe[0].value.set_index('Metric')
        self.assertEqual(float(primary.loc['Avg PC passed: final', 'All R0']), 1)
        # Benchmark changes do not silently rewrite accepted-loop round results.
        self.assertEqual(chart_y(app), baseline_round_y)

    def test_checkpoint_refresh_updates_explorer_trajectory(self):
        run = self.run_for()
        uid = d.read_json(Path(run.path) / 'run_manifest.json')['query_uids'][0]
        original = d.query_artifacts(run, uid)['checkpoints'][0]
        self.assertEqual(original['final_verification']['personal_constraints'], [True, True])
        path = Path(run.path) / 'queries' / uid / 'R0-fixture.json'
        cp = json.loads(path.read_text())
        cp['final_verification']['personal_constraints'] = [False, True]
        path.write_text(json.dumps(cp))
        self.assertEqual(d.query_artifacts(run, uid)['checkpoints'][0]['final_verification']['personal_constraints'], [False, True])

    def test_existing_analysis_cli_writes_partitions_separately(self):
        from contextlib import redirect_stdout, redirect_stderr
        from io import StringIO
        from scripts.analyze_repair_strategies import main
        train, test = self.run_for('TRAIN'), self.run_for('TEST')
        output = self.repo.root / 'generated-analysis'
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(main(['--run', f'R0={train.path}', '--output-dir', str(output / 'train'), '--no-figures']), 0)
            hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (output / 'train/R0').glob('*') if p.is_file()}
            self.assertEqual(main(['--run', f'R0={test.path}', '--output-dir', str(output / 'test'), '--no-figures']), 0)
        self.assertIsNotNone(d.analysis_folder(train, output))
        self.assertIsNotNone(d.analysis_folder(test, output))
        self.assertEqual(hashes, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (output / 'train/R0').glob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
