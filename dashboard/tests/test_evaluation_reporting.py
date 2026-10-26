"""Final ChinaTravel Table 4 source parity, profiles and definition safeguards."""
from io import StringIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard import data_loader as d, metrics as m
from dashboard.components import evaluation
from dashboard.components.common import table
from dashboard.tests.fixtures import Repository


class EvaluationReportingTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(size=6, steps=(1, 3, 9))
        self.addCleanup(self.repo.close)
        guard = patch.multiple(d, ROOT=self.repo.root, ANALYSIS=self.repo.analysis, TEST_TABLES=self.repo.reporting)
        guard.start(); self.addCleanup(guard.stop)
        for strategy in d.STRATEGIES:
            rows, _ = self.repo.rows[('TEST', strategy)]
            for i, row in enumerate(rows):
                row.update(group=['easy', 'medium', 'human'][i % 3],
                           cs_failed_raw_final=i % 2, pc_passed_final=1 if i % 2 else 2,
                           pc_failed_final=1 if i % 2 else 0, all_pass_final=i % 2 == 0,
                           schema_final=True)
        self.repo.write_reporting()
        from scripts.result_analysis import build_test_result_tables as team
        for name in ('score_plans', 'build_queries'):
            forbidden = patch.object(team, name, side_effect=AssertionError('No benchmark scoring/model calls'))
            forbidden.start(); self.addCleanup(forbidden.stop)

    def cohorts(self):
        from dashboard.tests.test_dashboard import context
        ctx = context('TEST', 'R0'); runs = d.available_reporting_runs(ctx['runs'])
        q, a, summaries = evaluation._cohorts(ctx, runs)
        return runs, q, a, summaries

    def app(self, standalone=True):
        module = 'dashboard.components.evaluation' if standalone else 'dashboard.pages.test_results'
        return AppTest.from_string(f"from dashboard.tests.test_dashboard import context\nfrom {module} import render\nrender(context('TEST', 'R0'))").run(timeout=90)

    def main(self, app):
        return next(x.value for x in app.dataframe if 'Metric (%)' in x.value)

    def test_pivot_exact_values_against_generated_table4(self):
        runs, q, _, summaries = self.cohorts()
        result = m.evaluation_pivot(summaries, q, list(runs), ['Easy', 'Medium', 'Human', 'All'])
        self.assertEqual(result.columns.tolist(), ['Metric (%)'] + [f'{g} {s}' for g in ['Easy', 'Med', 'Human', 'All'] for s in d.STRATEGIES])
        self.assertEqual(result['Metric (%)'].tolist(), list(m.EVALUATION_REPORT_ROWS))
        for s in runs:
            source = summaries[s].set_index('metric')
            for label, row in m.EVALUATION_REPORT_ROWS.items():
                for prefix, group in [('Easy','Easy'),('Med','Medium'),('Human','Human'),('All','All')]:
                    self.assertEqual(result.set_index('Metric (%)').loc[label, f'{prefix} {s}'], float(source.loc[row, group]))

    def test_filter_controls_and_percentage_display(self):
        app = self.app(); self.assertFalse(app.exception)
        app.multiselect(key='evaluation_report_strategies').set_value(['R2', 'R4']).run(timeout=90)
        app.selectbox(key='evaluation_report_difficulty').select('Medium').run(timeout=90)
        frame = self.main(app)
        self.assertEqual(frame.columns.tolist(), ['Metric (%)', 'Med R2', 'Med R4'])
        self.assertTrue(frame['Med R2'].between(0,100).all())
        self.assertFalse(any(x.label.lower().startswith('round') for x in app.selectbox))
        self.assertFalse(any('round' in title.value.lower() for title in app.subheader))

    def test_percentage_not_scaled_twice_and_chart_range(self):
        _, q, _, summaries = self.cohorts()
        row = m.EVALUATION_REPORT_ROWS['Logical micro']
        summaries['R0'].loc[summaries['R0'].metric == row, 'All'] = 88.46
        scores = m.evaluation_scores(summaries, q, ['R0'], 'All', 'Logical micro')
        self.assertEqual(scores['Score (%)'].iloc[0], 88.46)
        chart = evaluation.percentage_bar(scores, 'Strategy', 'Logical micro')
        self.assertEqual(tuple(chart.layout.yaxis.range), (0,100))
        self.assertEqual(chart.data[0].y[0], 88.46)

    def test_missing_and_future_r0_r1(self):
        self.repo.write_reporting(['R2','R3','R4'])
        app = self.app(standalone=False); self.assertFalse(app.exception)
        self.assertNotIn('All R0',self.main(app)); self.assertNotIn('All R1',self.main(app))
        self.repo.write_reporting()
        app = self.app(); self.assertFalse(app.exception)
        self.assertIn('All R0',self.main(app)); self.assertIn('All R1',self.main(app))

    def test_arbitrary_cohorts_and_only_observed_difficulties(self):
        for size in (1, 13, 43):
            fixture=Repository(size=size, strategies=('R1',))
            try:
                run=next(r for r in d.discover_runs(fixture.root) if r.partition=='TEST')
                folder=d.test_folder(run,fixture.reporting)
                q={'R1':d.read_csv(folder/'per_query.csv')}; summaries={'R1':d.read_csv(folder/'table4_eval_exp.csv')}
                result=m.evaluation_pivot(summaries,q,['R1'],['Easy','Medium','Human','All'])
                self.assertEqual(result.columns.tolist(),['Metric (%)','Easy R1','All R1'])
                self.assertEqual(result.set_index('Metric (%)').loc['Logical micro','All R1'],100)
            finally:
                fixture.close()

    def test_metric_selector_strategy_profile_and_difficulty_profile(self):
        app=self.app(); self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key='evaluation_metric').options,m.EVALUATION_METRICS)
        app.selectbox(key='evaluation_metric').select('All-pass ratio').run(timeout=90)
        app.selectbox(key='evaluation_difficulty_metric').select('Logical micro').run(timeout=90)
        app.selectbox(key='evaluation_difficulty_strategy').select('R4').run(timeout=90)
        self.assertFalse(app.exception)
        profile=next(x.value for x in app.dataframe if list(x.value.columns)==['Difficulty','Score (%)'])
        self.assertEqual(profile.Difficulty.tolist(),['Easy','Medium','Human','All'])
        self.assertTrue(any('aggregate query cohort' in x.value for x in app.caption))
        strategy=next(x.value for x in app.dataframe if list(x.value.columns)==['Metric','Score (%)'])
        self.assertEqual(len(strategy),5)

    def test_download_exactly_matches_active_pivot(self):
        _,q,_,summaries=self.cohorts()
        pivot=m.evaluation_pivot(summaries,q,['R2','R4'],['Medium'])
        with patch('dashboard.components.common.st.download_button') as download, patch('dashboard.components.common.st.dataframe') as display:
            table(pivot,'Table 4 ChinaTravel evaluation',precision=2)
            pd.testing.assert_frame_equal(display.call_args.args[0].data,pivot)
            self.assertEqual(download.call_args.args[1],pivot.to_csv(index=False).encode())
            parsed=pd.read_csv(StringIO(download.call_args.args[1].decode()))
            self.assertEqual(parsed.columns.tolist(),['Metric (%)','Med R2','Med R4'])
            style=display.call_args.args[0]
            self.assertEqual(style._display_funcs[(0,1)](88.4),'88.40')

    def test_incompatible_populations_are_blocked(self):
        runs,_,_,_=self.cohorts()
        p=Path(runs['R1'].path)/'run_manifest.json'; manifest=d.read_json(p)
        manifest['query_uids']=manifest['query_uids'][:-1];p.write_text(json.dumps(manifest))
        rows,refs=self.repo.rows[('TEST','R1')];self.repo.rows[('TEST','R1')]=(rows[:-1],refs)
        self.repo.write_reporting()
        app=self.app();self.assertFalse(app.exception)
        self.assertTrue(any('different query populations' in w.value for w in app.warning))
        self.assertFalse(any('Metric (%)' in x.value for x in app.dataframe))

    def test_missing_metric_does_not_become_zero(self):
        _,q,_,summaries=self.cohorts()
        summaries['R0']=summaries['R0'][summaries['R0'].metric!=m.EVALUATION_REPORT_ROWS['All-pass ratio']]
        result=m.evaluation_pivot(summaries,q,['R0'],['All']).set_index('Metric (%)')
        self.assertTrue(pd.isna(result.loc['All-pass ratio','All R0']))

    def test_filtered_summary_reuses_original_helper(self):
        from scripts.result_analysis import build_test_result_tables as team
        _,q,_,_=self.cohorts(); selected=q['R0'].iloc[:3]
        actual=m.evaluation_summary(selected)
        expected=pd.DataFrame(team.table_eval_exp(m.records(selected)))
        pd.testing.assert_frame_equal(actual,expected)
        incomplete=selected.drop(columns='all_pass_final')
        self.assertTrue(m.evaluation_summary(incomplete)['All'].isna().all())

    def test_definitions_are_code_specific_and_macro_not_allpass(self):
        definitions=m.evaluation_definitions().set_index('Metric')
        self.assertIn('N queries × C raw matrix columns',definitions.loc['Commonsense micro*','Denominator'])
        self.assertIn('including any exception column',definitions.loc['Commonsense micro*','Denominator'])
        self.assertIn('hard_logic_py',definitions.loc['Logical micro','Denominator'])
        self.assertEqual(definitions.loc['All-pass ratio','Evaluator'],'eval_exp.py:evaluate_final_plans')
        self.assertIn('schema_pass ∩ commonsense_pass ∩ logical_pass',definitions.loc['All-pass ratio','Numerator'])
        _,q,_,_=self.cohorts(); frame=q['R0'].iloc[:2].copy()
        frame['cs_failed_raw_final']=0;frame['schema_final']=False;frame['all_pass_final']=False
        values=m.evaluation_summary(frame).set_index('metric')['All']
        self.assertEqual(float(values[m.EVALUATION_REPORT_ROWS['Commonsense macro']]),100)
        self.assertEqual(float(values[m.EVALUATION_REPORT_ROWS['All-pass ratio']]),0)

    def test_logical_micro_is_pooled_not_query_macro_average(self):
        _,q,_,_=self.cohorts(); frame=q['R0'].iloc[:2].copy()
        frame['pc_total']=[2,8];frame['pc_passed_final']=[2,4];frame['pc_failed_final']=[0,4]
        values=m.evaluation_summary(frame).set_index('metric')['All']
        self.assertEqual(float(values[m.EVALUATION_REPORT_ROWS['Logical micro']]),60)
        self.assertNotEqual(float(values[m.EVALUATION_REPORT_ROWS['Logical micro']]),75)

    def test_documented_exception_footnote_and_raw_micro(self):
        from scripts.result_analysis import build_test_result_tables as team
        self.assertIn('commonsense micro is inflated',team.readme([]))
        self.assertIn('exception',m.EVALUATION_MICRO_FOOTNOTE)
        _,q,_,_=self.cohorts(); frame=q['R0'].iloc[:1].copy()
        frame['cs_failed_raw_final']=1;frame['cs_total_raw_final']=29
        frame['cs_evaluator_exception_final']=True;frame['cs_passed_final']=0
        values=m.evaluation_summary(frame).set_index('metric')['All']
        self.assertEqual(float(values[m.EVALUATION_REPORT_ROWS['Commonsense micro*']]),round(100*28/29,2))
        self.assertEqual(float(values[m.EVALUATION_REPORT_ROWS['Commonsense macro']]),0)

    def test_query_drilldown_is_saved_counts_not_aggregate_inference(self):
        _,q,_,_=self.cohorts(); frame=q['R0'].copy()
        result=m.evaluation_query_detail(frame,'R0','Medium')
        self.assertEqual(len(result),2)
        self.assertEqual(set(result.Difficulty),{'medium'})
        self.assertEqual(set(result.Strategy),{'R0'})
        frame=frame.drop(columns=['schema_final','all_pass_final'])
        result=m.evaluation_query_detail(frame,'R0','All')
        self.assertTrue(result['Schema passed'].isna().all())
        self.assertTrue(result['All-pass'].isna().all())

    def test_tables_1_to_3_remain_present(self):
        app=self.app(standalone=False);self.assertFalse(app.exception)
        for metric in ('Avg PC per query','Avg CS per query','Queries with complete token data'):
            self.assertTrue(any('Metric' in x.value and x.value.Metric.eq(metric).any() for x in app.dataframe))
        self.assertTrue(any('Metric (%)' in x.value for x in app.dataframe))


if __name__=='__main__':
    unittest.main()
