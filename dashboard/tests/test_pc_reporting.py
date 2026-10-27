"""Report-ready PC pivots and round comparisons over generated-output fixtures."""
from io import StringIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard import data_loader as d, metrics as m
from dashboard.components import pc
from dashboard.components.common import table
from dashboard.tests.fixtures import Repository


class PCReportingTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(size=6, steps=(1, 3, 10))
        self.addCleanup(self.repo.close)
        guard = patch.multiple(d, ROOT=self.repo.root, ANALYSIS=self.repo.analysis, TEST_TABLES=self.repo.reporting)
        guard.start(); self.addCleanup(guard.stop)
        for strategy in d.STRATEGIES:
            rows, _ = self.repo.rows[('TEST', strategy)]
            for index, row in enumerate(rows):
                row['group'] = ['easy', 'medium', 'human'][index % 3]
                if index == 1:
                    row.update(pc_passed_final=1, pc_share_final=.5, pc_failed_final=1,
                               pc_passed_final_excl_named=1, pc_failed_kinds_final='Total budget')
        self.repo.write_reporting()
        from scripts.result_analysis import build_test_result_tables as team
        for name in ('score_plans', 'build_queries'):
            no_scoring = patch.object(team, name, side_effect=AssertionError('No benchmark/model calls'))
            no_scoring.start(); self.addCleanup(no_scoring.stop)

    def context(self):
        from dashboard.tests.test_dashboard import context
        return context('TEST', 'R0')

    def cohorts(self):
        ctx = self.context()
        runs = d.available_pc_runs(ctx['runs'])
        q, a, summaries = pc._cohorts(ctx, runs)
        return runs, q, a, summaries

    def app(self):
        return AppTest.from_string("from dashboard.tests.test_dashboard import context\nfrom dashboard.pages.test_results import render\nrender(context('TEST', 'R0'))").run(timeout=90)

    def test_pivot_order_and_exact_generated_values(self):
        runs, q, _, summaries = self.cohorts()
        pivot = m.pc_report_pivot(summaries, q, list(runs), ['Easy', 'Medium', 'Human', 'All'])
        expected = ['Metric'] + [f'{group} {s}' for group in ['Easy', 'Med', 'Human', 'All'] for s in d.STRATEGIES]
        self.assertEqual(pivot.columns.tolist(), expected)
        values = pivot.set_index('Metric')
        for strategy in runs:
            saved = d.test_table(runs[strategy], 'table1_pc').set_index('metric')
            for display, source in m.PC_REPORT_ROWS.items():
                for group, prefix in [('Easy', 'Easy'), ('Medium', 'Med'), ('Human', 'Human'), ('All', 'All')]:
                    if source:
                        self.assertEqual(str(values.loc[display, f'{prefix} {strategy}']), str(saved.loc[source, group]))
                    else:
                        self.assertTrue(pd.isna(values.loc[display, f'{prefix} {strategy}']))

    def test_missing_r1_and_future_r1_availability(self):
        self.repo.write_reporting(['R0', 'R2', 'R3', 'R4'])
        runs, q, _, summaries = self.cohorts()
        self.assertNotIn('R1', runs)
        pivot = m.pc_report_pivot(summaries, q, list(runs), ['All'])
        self.assertNotIn('All R1', pivot)
        self.repo.write_reporting()
        runs, q, _, summaries = self.cohorts()
        self.assertIn('All R1', m.pc_report_pivot(summaries, q, list(runs), ['All']))

    def test_dynamic_difficulties_and_no_empty_group_columns(self):
        runs, q, _, summaries = self.cohorts()
        easy = {s: frame[frame.group == 'easy'] for s, frame in q.items()}
        self.assertEqual(m.pc_available_difficulties(easy), ['Easy'])
        pivot = m.pc_report_pivot(summaries, easy, list(runs), ['Easy', 'Medium', 'Human', 'All'])
        self.assertFalse(any(c.startswith(('Med ', 'Human ')) for c in pivot))
        self.assertEqual(m.pc_available_difficulties(q), ['Easy', 'Medium', 'Human'])

    def test_table_is_primary_and_local_filters_work(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.columns[1], 'Easy R0')
        next(x for x in app.multiselect if x.label == 'Strategies').set_value(['R2', 'R4']).run(timeout=90)
        next(x for x in app.selectbox if x.label == 'Difficulty').select('Medium').run(timeout=90)
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.columns.tolist(), ['Metric', 'Med R2', 'Med R4'])

    def test_missing_selected_run_reporting_does_not_hide_comparison(self):
        self.repo.write_reporting(['R2', 'R3', 'R4'])
        app = self.app()
        self.assertFalse(app.exception)
        self.assertIn('All R2', app.dataframe[0].value)
        self.assertNotIn('All R0', app.dataframe[0].value)

    def test_explicit_cohort_filters_select_per_strategy_cohorts(self):
        ctx = self.context(); ctx['filters']['uid'] = 'fixture-1'
        available = d.available_pc_runs(ctx['runs'])
        q, a, summaries = pc._cohorts(ctx, available)
        for strategy in available:
            self.assertEqual(q[strategy].query_uid.tolist(), ['fixture-1'])
            self.assertEqual(set(a[strategy].query_uid), {'fixture-1'})
            self.assertEqual(summaries[strategy].loc[summaries[strategy].metric == 'Queries (n)', 'All'].iloc[0], 1)

    def test_full_trajectories_retained_for_proposal_filtered_cohorts(self):
        ctx = self.context(); ctx['filters']['round'] = '3'
        q, a, _ = pc._cohorts(ctx, d.available_pc_runs(ctx['runs']))
        self.assertEqual(set(a['R0'].step), {1, 3, 10})
        self.assertEqual(len(q['R0']), 6)

    def test_no_mislabelled_initially_perfect_subset(self):
        _, q, _, summaries = self.cohorts()
        t = summaries['R0'].copy()
        t.loc[t.metric == '  of which already 100% in the initial plan', 'All'] = '999'
        pivot = m.pc_report_pivot({'R0': t}, {'R0': q['R0']}, ['R0'], ['All']).set_index('Metric')
        self.assertTrue(pd.isna(pivot.loc['Queries: all PC pass at start', 'All R0']))
        t = t[t.metric != 'Avg PC passed per query - final plan']
        pivot = m.pc_report_pivot({'R0': t}, {'R0': q['R0']}, ['R0'], ['All']).set_index('Metric')
        self.assertTrue(pd.isna(pivot.loc['Avg PC passed: final', 'All R0']))

    def test_failure_kinds_reuse_team_definition_for_difficulty(self):
        runs, q, _, _ = self.cohorts()
        run = runs['R0']
        medium = m.pc_difficulty_queries(q['R0'], 'Medium')
        kinds = m.team_table(medium, 'pc_kinds', d.pc_references(run))
        result = m.pc_failure_table(kinds, 'R0', 'Medium').set_index('PC family')
        self.assertEqual(result.loc['Total budget', 'Failure count'], 1)
        self.assertEqual(result.loc['Total budget', 'Total constraints'], 2)
        self.assertEqual(result.loc['Total budget', 'Failure rate (%)'], 50)

    def test_rounds_and_endpoints_do_not_mix_benchmark_with_loop(self):
        runs, q, a, _ = self.cohorts()
        q['R0'] = q['R0'].assign(pc_share_initial=.99, pc_share_final=.99)
        t = m.pc_round_table(q['R0'], a['R0'], d.checkpoints(runs['R0'])).set_index('Metric')
        self.assertEqual(list(t.columns), ['Initial', 'Round 1', 'Round 3', 'Round 10', 'Final'])
        self.assertEqual(t.loc['Mean PC pass rate (%)', 'Initial'], 50)
        self.assertEqual(t.loc['Mean PC pass rate (%)', 'Final'], 100)
        self.assertTrue(pd.isna(t.loc['Avg # PCs fixed', 'Initial']))
        self.assertTrue(pd.isna(t.loc['Avg # PCs fixed', 'Final']))
        self.assertTrue(pd.isna(t.loc['# queries still active (observed)', 'Final']))
        self.assertEqual(t.loc['# queries still active (observed)', 'Round 3'], 6)
        self.assertEqual(t.loc['# queries still active (observed)', 'Round 10'], 0)

    def test_rejected_candidate_not_counted_as_accepted_round_fix(self):
        runs, q, a, _ = self.cohorts()
        t = m.pc_round_table(q['R2'], a['R2'], d.checkpoints(runs['R2'])).set_index('Metric')
        self.assertEqual(t.loc['Avg # PCs fixed', 'Round 1'], 0)
        self.assertEqual(t.loc['Avg # new PC violations', 'Round 1'], 0)
        self.assertEqual(t.loc['Mean PC pass rate (%)', 'Round 1'], 50)

    def test_round_comparison_pivot_and_chart_share_cells(self):
        runs, q, a, _ = self.cohorts()
        tables = {s: m.pc_round_table(q[s], a[s], d.checkpoints(runs[s])) for s in ('R0', 'R2')}
        tables['R0'] = tables['R0'].drop(columns='Round 3')
        comparison, points = m.pc_round_comparison(tables, 'Avg # PCs fixed')
        self.assertEqual(comparison.columns.tolist(), ['Strategy', 'Initial', 'Round 1', 'Round 3', 'Round 10', 'Final'])
        self.assertTrue(pd.isna(comparison.set_index('Strategy').loc['R0', 'Round 3']))
        figure = pc.round_chart(points, 'Avg # PCs fixed')
        by_strategy = comparison.set_index('Strategy')
        for trace in figure.data:
            self.assertFalse(trace.connectgaps)
            for step, value in zip(trace.x, trace.y):
                expected = by_strategy.loc[trace.name, f'Round {step}']
                if pd.isna(expected):
                    self.assertTrue(pd.isna(value))
                else:
                    self.assertEqual(value, expected)

    def test_download_uses_currently_displayed_dataframe(self):
        _, q, _, summaries = self.cohorts()
        pivot = m.pc_report_pivot(summaries, q, ['R0', 'R2'], ['Medium'])
        with patch('dashboard.components.common.st.download_button') as download, patch('dashboard.components.common.st.dataframe') as display:
            table(pivot, 'PC comparison table')
            pd.testing.assert_frame_equal(display.call_args.args[0].data, pivot)
            self.assertEqual(download.call_args.args[1], pivot.to_csv(index=False).encode())
            exported = pd.read_csv(StringIO(download.call_args.args[1].decode()))
            self.assertEqual(exported.columns.tolist(), ['Metric', 'Med R0', 'Med R2'])

    def test_round_metric_options_and_difficulty_filters(self):
        app = self.app()
        metric = next(x for x in app.selectbox if x.label == 'Metric')
        self.assertEqual(metric.options, list(m.PC_ROUND_COMPARISONS))
        metric.select('New-violation rate').run(timeout=90)
        next(x for x in app.selectbox if x.label == 'Comparison difficulty').select('Human').run(timeout=90)
        self.assertFalse(app.exception)
        comparison = next(frame.value for frame in app.dataframe if 'Strategy' in frame.value and 'Round 10' in frame.value)
        self.assertEqual(set(comparison.Strategy), set(d.STRATEGIES))


if __name__ == '__main__':
    unittest.main()
