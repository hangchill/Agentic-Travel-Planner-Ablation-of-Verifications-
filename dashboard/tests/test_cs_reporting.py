"""CS Table 2 parity, availability, round diagnostics and filtered downloads."""
from io import StringIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard import data_loader as d, metrics as m
from dashboard.components import cs, pc, reporting
from dashboard.components.common import table
from dashboard.tests.fixtures import Repository


class CSReportingTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(size=6, steps=(1, 3, 9))
        self.addCleanup(self.repo.close)
        guard = patch.multiple(d, ROOT=self.repo.root, ANALYSIS=self.repo.analysis, TEST_TABLES=self.repo.reporting)
        guard.start(); self.addCleanup(guard.stop)
        self.labels = ['Does not follow Chronological Order', 'Visiting attraction in their closed time',
                       'Incorrect cost information of Inner-City Transport', 'Fixture check 4']
        for strategy in d.STRATEGIES:
            rows, _ = self.repo.rows[('TEST', strategy)]
            for i, row in enumerate(rows):
                failed = i % 5
                row.update(group=['easy', 'medium', 'human'][i % 3], cs_passed_initial=24,
                           cs_passed_final=28 - failed, cs_failed_checks_final='; '.join(self.labels[:failed]),
                           cs_failed_raw_final=failed)
        self.repo.write_reporting()
        from scripts.result_analysis import build_test_result_tables as team
        for name in ('score_plans', 'build_queries'):
            forbidden = patch.object(team, name, side_effect=AssertionError('No scoring/model calls'))
            forbidden.start(); self.addCleanup(forbidden.stop)

    def context(self):
        from dashboard.tests.test_dashboard import context
        return context('TEST', 'R0')

    def cohorts(self):
        ctx = self.context(); runs = d.available_reporting_runs(ctx['runs'])
        q, a, summaries = cs._cohorts(ctx, runs)
        return runs, q, a, summaries

    def app(self, cs_only=False):
        module = 'dashboard.components.cs' if cs_only else 'dashboard.pages.test_results'
        return AppTest.from_string(f"from dashboard.tests.test_dashboard import context\nfrom {module} import render\nrender(context('TEST', 'R0'))").run(timeout=90)

    def main_frame(self, app):
        return next(frame.value for frame in app.dataframe if 'Metric' in frame.value
                    and frame.value.Metric.eq('Avg CS per query').any())

    def test_pivot_order_and_direct_table2_parity(self):
        runs, q, _, summaries = self.cohorts()
        pivot = m.cs_report_pivot(summaries, q, list(runs), ['Easy', 'Medium', 'Human', 'All'])
        self.assertEqual(pivot.columns.tolist(), ['Metric'] + [f'{g} {s}' for g in ['Easy', 'Med', 'Human', 'All'] for s in d.STRATEGIES])
        result = pivot.set_index('Metric')
        for strategy in runs:
            source = summaries[strategy].set_index('metric')
            for displayed, key in m.CS_REPORT_ROWS.items():
                if displayed == key:
                    continue
                for label, group in [('Easy', 'Easy'), ('Med', 'Medium'), ('Human', 'Human'), ('All', 'All')]:
                    self.assertEqual(result.loc[displayed, f'{label} {strategy}'], float(source.loc[key, group]))

    def test_saved_count_summaries_are_not_raw_micro_metrics(self):
        runs, q, _, summaries = self.cohorts()
        pivot = m.cs_report_pivot(summaries, q, ['R0'], ['All']).set_index('Metric')['All R0']
        self.assertEqual(pivot['Avg CS per query'], 28)
        self.assertEqual(pivot['Avg CS passed: initial'], 24)
        self.assertAlmostEqual(pivot['Avg CS passed: final'], (28+27+26+25+24+28)/6)
        self.assertEqual(pivot['Final plans: 2+ failed CS'], 3)
        self.assertEqual(pivot['Final plans with >85% CS passed'], 6)
        self.assertEqual(pivot['% final plans with >85% CS passed'], 100)
        self.assertAlmostEqual(pivot['Avg % CS passed: initial'], 100 * 24 / 28)

    def test_strict_85_percent_threshold(self):
        _, q, _, _ = self.cohorts()
        small = q['R0'].iloc[:2].copy()
        small['cs_total'] = 20; small['cs_passed_initial'] = 15
        small['cs_passed_final'] = [17, 18]
        summary = m.team_table(small, 'cs')
        result = m.cs_report_pivot({'R0': summary}, {'R0': small}, ['R0'], ['All']).set_index('Metric')
        self.assertEqual(result.loc['Final plans with >85% CS passed', 'All R0'], 1)
        self.assertEqual(result.loc['% final plans with >85% CS passed', 'All R0'], 50)

    def test_threshold_unavailable_for_heterogeneous_check_totals(self):
        _, q, _, summaries = self.cohorts()
        q['R0'] = q['R0'].copy(); q['R0'].loc[0, 'cs_total'] = 29
        pivot = m.cs_report_pivot(summaries, q, ['R0'], ['All']).set_index('Metric')
        self.assertTrue(pd.isna(pivot.loc['Final plans with >85% CS passed', 'All R0']))
        self.assertTrue(pd.isna(pivot.loc['% final plans with >85% CS passed', 'All R0']))

    def test_difficulty_and_strategy_controls_filter_export_frame(self):
        app = self.app(cs_only=True)
        self.assertFalse(app.exception)
        app.multiselect(key='cs_report_strategies').set_value(['R2', 'R4']).run(timeout=90)
        app.selectbox(key='cs_report_difficulty').select('Medium').run(timeout=90)
        self.assertFalse(app.exception)
        self.assertEqual(self.main_frame(app).columns.tolist(), ['Metric', 'Med R2', 'Med R4'])

    def test_missing_r0_r1_and_future_availability(self):
        self.repo.write_reporting(['R2', 'R3', 'R4'])
        app = self.app()
        self.assertFalse(app.exception)
        self.assertNotIn('All R0', self.main_frame(app))
        self.assertNotIn('All R1', self.main_frame(app))
        self.repo.write_reporting()
        app = self.app()
        self.assertFalse(app.exception)
        self.assertIn('All R0', self.main_frame(app))
        self.assertIn('All R1', self.main_frame(app))

    def test_arbitrary_cohort_sizes_and_dynamic_difficulties(self):
        for size in (1, 13, 41):
            fixture = Repository(size=size, strategies=('R1',))
            try:
                run = next(r for r in d.discover_runs(fixture.root) if r.partition == 'TEST')
                folder = d.test_folder(run, fixture.reporting)
                q = d.read_csv(folder / 'per_query.csv'); summary = d.read_csv(folder / 'table2_cs.csv')
                pivot = m.cs_report_pivot({'R1': summary}, {'R1': q}, ['R1'], ['Easy', 'Medium', 'Human', 'All'])
                self.assertEqual(pivot.columns.tolist(), ['Metric', 'Easy R1', 'All R1'])
                self.assertEqual(pivot.set_index('Metric').loc['Final plans with >85% CS passed', 'All R1'], size)
            finally:
                fixture.close()

    def test_source_rows_missing_stay_unavailable(self):
        _, q, _, summaries = self.cohorts()
        summaries['R0'] = summaries['R0'][summaries['R0'].metric != 'Avg CS checks failed per query - final plan']
        pivot = m.cs_report_pivot(summaries, q, ['R0'], ['All']).set_index('Metric')
        self.assertTrue(pd.isna(pivot.loc['Avg CS failed: final', 'All R0']))
        q['R0'] = q['R0'].drop(columns='cs_passed_initial')
        pivot = m.cs_report_pivot(summaries, q, ['R0'], ['All']).set_index('Metric')
        self.assertTrue(pd.isna(pivot.loc['Avg CS passed: initial', 'All R0']))

    def test_failure_labels_and_denominator_exclude_exceptions(self):
        _, q, _, _ = self.cohorts()
        sample = q['R0'].iloc[:3].copy()
        sample.loc[sample.index[2], ['cs_evaluator_exception_final', 'cs_passed_final', 'cs_failed_checks_final']] = [True, 0, '']
        failures, coverage = m.cs_failure_families(sample, 'R0', 'All')
        self.assertEqual(coverage['Attributable plans'], 2)
        self.assertEqual(coverage['Excluded unattributable plans'], 1)
        self.assertEqual(failures['CS family'].tolist(), [self.labels[0]])
        self.assertEqual(failures['Failure count'].iloc[0], 1)
        self.assertEqual(failures['Failure rate (%)'].iloc[0], 50)

    def test_failure_family_filter_and_original_labels(self):
        app = self.app(cs_only=True)
        family = self.labels[0]
        app.multiselect(key='cs_failure_families').set_value([family]).run(timeout=90)
        self.assertFalse(app.exception)
        frame = next(x.value for x in app.dataframe if 'CS family' in x.value)
        self.assertEqual(set(frame['CS family']), {family})

    def test_incompatible_populations_block_comparison(self):
        runs, q, _, _ = self.cohorts()
        q['R1'] = q['R1'].iloc[:-1]
        self.assertIn('All', m.incompatible_populations(q, ['R0', 'R1'], ['All']))
        self.assertEqual(m.incompatible_populations(q, ['R0', 'R1'], ['Easy']), [])
        manifest_path = Path(runs['R1'].path) / 'run_manifest.json'
        manifest = d.read_json(manifest_path); manifest['query_uids'] = manifest['query_uids'][:-1]
        manifest_path.write_text(json.dumps(manifest))
        rows, refs = self.repo.rows[('TEST', 'R1')]
        self.repo.rows[('TEST', 'R1')] = (rows[:-1], refs)
        self.repo.write_reporting()
        app = self.app(cs_only=True)
        self.assertFalse(app.exception)
        self.assertTrue(any('different query populations' in w.value for w in app.warning))
        self.assertFalse(any('Metric' in x.value and x.value.Metric.eq('Avg CS per query').any() for x in app.dataframe))

    def test_round_diagnostics_and_unsupported_check_metrics(self):
        runs, q, a, _ = self.cohorts()
        result = m.cs_round_table(q['R0'], a['R0'], d.checkpoints(runs['R0'])).set_index('Metric')
        self.assertEqual(result.columns.tolist(), ['Initial', 'Round 1', 'Round 3', 'Round 9', 'Final'])
        self.assertTrue(result.loc['Mean CS pass rate (%)'].isna().all())
        self.assertTrue(result.loc['Avg # CS fixed'].isna().all())
        self.assertEqual(result.loc['Mean # CS error messages', 'Initial'], 1)
        self.assertEqual(result.loc['Mean # CS error messages', 'Final'], 0)
        self.assertEqual(result.loc['Avg # CS messages removed', 'Round 1'], 1)
        self.assertEqual(result.loc['Avg net CS message reduction', 'Round 1'], 1)
        self.assertTrue(pd.isna(result.loc['Avg # CS messages removed', 'Initial']))
        self.assertTrue(pd.isna(result.loc['Avg # CS messages removed', 'Final']))
        self.assertEqual(result.loc['# queries still active (observed)', 'Round 3'], 6)

    def test_rejected_candidates_do_not_remove_accepted_errors(self):
        runs, q, a, _ = self.cohorts()
        result = m.cs_round_table(q['R2'], a['R2'], d.checkpoints(runs['R2'])).set_index('Metric')
        self.assertEqual(result.loc['Mean # CS error messages', 'Round 1'], 1)
        self.assertEqual(result.loc['Avg # CS messages removed', 'Round 1'], 0)
        self.assertEqual(result.loc['Avg # CS messages removed', 'Round 3'], 1)

    def test_round_comparison_chart_includes_initial_rounds_and_final(self):
        runs, q, a, _ = self.cohorts()
        tables = {s: m.cs_round_table(q[s], a[s], d.checkpoints(runs[s])) for s in ('R0', 'R2')}
        comparison, points = m.cs_round_comparison(tables, 'Mean CS error messages')
        self.assertEqual(comparison.columns.tolist(), ['Strategy', 'Initial', 'Round 1', 'Round 3', 'Round 9', 'Final'])
        figure = reporting.round_chart(points, 'Mean CS error messages', 'Mean # CS error messages', endpoints=True)
        for trace in figure.data:
            self.assertEqual(list(trace.x), list(comparison.columns[1:]))
            self.assertFalse(trace.connectgaps)
            for stage, value in zip(trace.x, trace.y):
                self.assertEqual(value, comparison.set_index('Strategy').loc[trace.name, stage])

    def test_unavailable_comparison_does_not_fabricate_chart(self):
        app = self.app(cs_only=True)
        app.selectbox(key='cs_round_compare_metric').select('Mean CS pass rate').run(timeout=90)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('plotly_chart')), 0)
        self.assertTrue(any('Unavailable from loop error-message logs' in item.value for item in app.info))

    def test_csv_download_dataframe_is_exactly_filtered_frame(self):
        _, q, _, summaries = self.cohorts()
        pivot = m.cs_report_pivot(summaries, q, ['R2', 'R4'], ['Human'])
        with patch('dashboard.components.common.st.download_button') as download, patch('dashboard.components.common.st.dataframe') as display:
            table(pivot, 'CS comparison table')
            pd.testing.assert_frame_equal(display.call_args.args[0].data, pivot)
            self.assertEqual(download.call_args.args[1], pivot.to_csv(index=False).encode())
            self.assertEqual(pd.read_csv(StringIO(download.call_args.args[1].decode())).columns.tolist(), ['Metric', 'Human R2', 'Human R4'])

    def test_pc_pivot_and_chart_unchanged_after_shared_refactor(self):
        ctx = self.context(); runs = d.available_pc_runs(ctx['runs'])
        q, a, summaries = pc._cohorts(ctx, runs)
        pivot = m.pc_report_pivot(summaries, q, list(runs), ['All']).set_index('Metric')
        for s in runs:
            source = summaries[s].set_index('metric')
            for displayed, row in m.PC_REPORT_ROWS.items():
                if row:
                    self.assertEqual(str(pivot.loc[displayed, f'All {s}']), str(source.loc[row, 'All']))
        tables = {s: m.pc_round_table(q[s], a[s], d.checkpoints(runs[s])) for s in runs}
        comparison, points = m.pc_round_comparison(tables, 'Avg # PCs fixed')
        figure = pc.round_chart(points, 'Avg # PCs fixed')
        self.assertTrue(all('Initial' not in list(trace.x) for trace in figure.data))
        self.assertEqual(comparison.columns[-1], 'Final')

    def test_message_introduction_and_rate_are_explicit_diagnostics(self):
        runs, q, a, _ = self.cohorts()
        bundles = json.loads(json.dumps(d.checkpoints(runs['R0'])))
        for bundle in bundles.values():
            bundle['checkpoints'][0]['repair_history'][1]['verification']['commonsense_errors'] = ['initial error', 'new error']
        result = m.cs_round_table(q['R0'], a['R0'], bundles).set_index('Metric')
        self.assertEqual(result.loc['Mean # CS error messages', 'Round 1'], 2)
        self.assertEqual(result.loc['Avg # CS messages introduced', 'Round 1'], 1)
        self.assertEqual(result.loc['% rounds introducing >=1 CS message', 'Round 1'], 100)
        self.assertEqual(result.loc['Avg net CS message reduction', 'Round 1'], -1)
        self.assertTrue(pd.isna(result.loc['New CS violation rate (%)', 'Round 1']))

    def test_macro_rates_reuse_saved_query_denominators(self):
        _, q, _, _ = self.cohorts()
        frame = q['R0'].iloc[:2].copy()
        frame['cs_total'] = [2, 4]
        frame['cs_passed_initial'] = [1, 1]
        frame['cs_passed_final'] = [2, 2]
        summary = m.team_table(frame, 'cs')
        result = m.cs_report_pivot({'R0': summary}, {'R0': frame}, ['R0'], ['All']).set_index('Metric')
        self.assertEqual(result.loc['Avg % CS passed: initial', 'All R0'], 37.5)
        self.assertEqual(result.loc['Avg % CS passed: final', 'All R0'], 75)
        self.assertEqual(result.loc['Avg % CS passed: change (pts)', 'All R0'], 37.5)
        self.assertTrue(pd.isna(result.loc['Final plans with >85% CS passed', 'All R0']))

    def test_unknown_failure_attribution_is_not_zero_failure(self):
        _, q, _, _ = self.cohorts()
        frame = q['R0'].copy().astype(object)
        frame['cs_evaluator_exception_final'] = None
        failures, coverage = m.cs_failure_families(frame, 'R0', 'All')
        self.assertTrue(failures.empty)
        self.assertEqual(coverage['Attributable plans'], 0)
        self.assertEqual(coverage['Excluded unattributable plans'], len(frame))


if __name__ == '__main__':
    unittest.main()
