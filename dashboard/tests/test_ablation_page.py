"""The comparison page consumes generated outputs without analysis on rerun."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard import data_loader as d
from dashboard.tests.fixtures import Repository
from scripts.result_analysis.ablation_comparisons import COMPARISONS
from scripts.result_analysis.ablation_comparisons.build_ablation_comparisons import main


class AblationPageTests(unittest.TestCase):
    def setUp(self):
        self.repo=Repository(size=3,steps=(1,2))
        self.addCleanup(self.repo.close)
        self.output=self.repo.root/'results/analysis/ablation_comparisons'
        self.args=['--repository-root',str(self.repo.root),'--test-reporting-dir',str(self.repo.reporting),
                   '--analysis-dir',str(self.repo.analysis/'test'),'--output-dir',str(self.output)]
        for key in ('R0','R2','R3','R4'):
            self.args.extend(['--'+key.lower(),str(self.repo.manifests[('TEST',key)][0])])
        self.build()
        guard=patch.object(d,'ROOT',self.repo.root);guard.start();self.addCleanup(guard.stop)

    def build(self,extra=()):
        with redirect_stdout(io.StringIO()):
            main(self.args+list(extra))

    def app(self):
        return AppTest.from_string("from dashboard.pages.ablation_comparisons import render\nrender({'runs': []})").run(timeout=90)

    def test_page_reads_exact_generated_values_and_csv_frame(self):
        with patch('scripts.result_analysis.ablation_comparisons.build_ablation_comparisons.build_comparison',side_effect=AssertionError('No frontend analysis')):
            app=self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[0].options,[value[0] for value in COMPARISONS.values()])
        shown=next(x.value for x in app.dataframe if 'Delta (Right - Left)' in x.value)
        saved=pd.read_csv(self.output/'r0_vs_r2/summary.csv');saved=saved[saved.difficulty=='All']
        self.assertEqual(shown.Metric.tolist(),saved.metric.tolist())
        pd.testing.assert_series_equal(shown.R0.reset_index(drop=True),saved.left_value.reset_index(drop=True),check_names=False)
        with patch('dashboard.components.common.st.dataframe'),patch('dashboard.components.common.st.download_button') as download:
            from dashboard.components.common import table
            table(shown,'comparison export test')
        exported=pd.read_csv(io.StringIO(download.call_args.args[1].decode()))
        pd.testing.assert_frame_equal(exported,shown.reset_index(drop=True),check_dtype=False)

    def test_difficulty_filter_and_no_silent_cohort_substitution(self):
        app=self.app()
        next(x for x in app.selectbox if x.label=='Difficulty').select('Easy').run(timeout=90)
        self.assertFalse(app.exception)
        self.assertTrue(any('Delta (Right - Left)' in x.value for x in app.dataframe))
        next(x for x in app.selectbox if x.label=='Difficulty').select('Human').run(timeout=90)
        self.assertFalse(app.exception)
        self.assertFalse(any('Delta (Right - Left)' in x.value for x in app.dataframe))
        self.assertTrue(any('populations are unavailable or incompatible' in x.value for x in app.info))

    def test_missing_runs_do_not_break_page_and_advanced_label(self):
        path=self.repo.manifests[('TEST','R4')][0]/'run_manifest.json'
        manifest=json.loads(path.read_text());manifest['implementation_hash']='different-R4-implementation'
        path.write_text(json.dumps(manifest));self.build()
        app=self.app()
        app.selectbox[0].set_value('r0_vs_r4_matrix').run(timeout=90)
        self.assertFalse(app.exception)
        self.assertTrue(any('Delta (R4 - R0)' in x.value for x in app.dataframe))
        self.assertFalse(any('current runs differ in additional implementation details' in x.value for x in app.warning))
        self.assertTrue(any(x.value=='Descriptive comparison only' for x in app.subheader))
        mechanisms=next(x.value for x in app.dataframe if 'evidence_n' in x.value)
        baseline=mechanisms[(mechanisms.run=='R0') & mechanisms.metric.str.startswith('Guidance:')]
        self.assertTrue(baseline.value.eq('Not applicable').all())
        self.assertFalse(baseline.empty)
        app.selectbox[0].set_value('r3_vs_r4').run(timeout=90)
        self.assertTrue(any(x.value=='Strategy comparison — not a matrix ablation' for x in app.caption))
        self.assertTrue(any('does not establish a causal' in x.value for x in app.warning))

    def test_missing_r0_or_r4_is_explicit_on_fourth_page(self):
        original=list(self.args)
        for role in ('R0','R4'):
            with self.subTest(role=role):
                self.args=list(original)
                i=self.args.index('--'+role.lower());del self.args[i:i+2]
                self.build()
                app=self.app();app.selectbox[0].set_value('r0_vs_r4_matrix').run(timeout=90)
                self.assertFalse(app.exception)
                self.assertTrue(any(role+' TEST' in x.value and 'not currently available' in x.value for x in app.markdown))
                self.assertFalse(any('Delta (R4 - R0)' in x.value for x in app.dataframe))

    def test_fourth_matrix_na_export_preserves_displayed_cells(self):
        app=self.app();app.selectbox[0].set_value('r0_vs_r4_matrix').run(timeout=90)
        shown=next(x.value for x in app.dataframe if 'evidence_n' in x.value)
        with patch('dashboard.components.common.st.dataframe'),patch('dashboard.components.common.st.download_button') as download:
            from dashboard.components.common import table
            table(shown,'matrix evidence export test')
        exported=pd.read_csv(io.StringIO(download.call_args.args[1].decode()),dtype=str)
        rows=exported[(exported.run=='R0') & exported.metric.str.startswith('Guidance:')]
        self.assertTrue(rows.value.eq('Not applicable').all())
        self.assertFalse(rows.empty)

    def test_retired_browser_selection_migrates_to_current_fourth_pair(self):
        app=AppTest.from_string("import streamlit as st\nst.session_state['ablation_comparison']='retired-selection'\nfrom dashboard.pages.ablation_comparisons import render\nrender({'runs': []})").run(timeout=90)
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[0].value,'r0_vs_r4_matrix')
        self.assertTrue(any('Delta (R4 - R0)' in x.value for x in app.dataframe))

    def test_stale_inputs_and_edited_outputs_block_values(self):
        self.assertTrue(d.comparison_bundle('r0_vs_r2')['ready'])
        p=self.output/'r0_vs_r2/summary.csv';p.write_text(p.read_text().replace('100','99',1))
        self.assertFalse(d.comparison_bundle('r0_vs_r2')['ready'])
        self.build()
        path=self.repo.manifests[('TEST','R0')][0]/'run_manifest.json'
        m=json.loads(path.read_text());m['changed_setting']='new';path.write_text(json.dumps(m))
        self.assertFalse(d.comparison_bundle('r0_vs_r2')['ready'])

    def test_dynamic_availability_after_cli_regeneration(self):
        self.assertFalse(d.comparison_bundle('r1_vs_r3')['validity']['available'])
        self.build(['--r1',str(self.repo.manifests[('TEST','R1')][0])])
        self.assertTrue(d.comparison_bundle('r1_vs_r3')['validity']['available'])
        app=self.app();app.selectbox[0].set_value('r1_vs_r3').run(timeout=90)
        self.assertFalse(app.exception)
        self.assertTrue(any('Delta (Right - Left)' in x.value for x in app.dataframe))

    def test_missing_generated_files_are_explicitly_unavailable(self):
        (self.output/'r0_vs_r2/validity.json').unlink()
        app=self.app()
        self.assertFalse(app.exception)
        self.assertTrue(any('Generated comparison outputs are unavailable' in x.value for x in app.info))
