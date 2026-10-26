"""Table 3 source parity, token coverage, classification and process rounds."""
from io import StringIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard import data_loader as d, metrics as m
from dashboard.components import repair_process, reporting
from dashboard.components.common import table
from dashboard.tests.fixtures import Repository


class ProcessReportingTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(size=6, steps=(1, 3, 9))
        self.addCleanup(self.repo.close)
        guard = patch.multiple(d, ROOT=self.repo.root, ANALYSIS=self.repo.analysis, TEST_TABLES=self.repo.reporting)
        guard.start(); self.addCleanup(guard.stop)
        for strategy in d.STRATEGIES:
            rows, _ = self.repo.rows[('TEST', strategy)]
            for i, row in enumerate(rows):
                row['group'] = ['easy', 'medium', 'human'][i % 3]
        self.repo.write_reporting()
        from scripts.result_analysis import build_test_result_tables as team
        for name in ('score_plans', 'build_queries'):
            blocked = patch.object(team, name, side_effect=AssertionError('No scoring/model calls'))
            blocked.start(); self.addCleanup(blocked.stop)

    def cohorts(self):
        from dashboard.tests.test_dashboard import context
        ctx = context('TEST', 'R0'); runs = d.available_reporting_runs(ctx['runs'])
        q, a, summaries = repair_process._cohorts(ctx, runs)
        return runs, q, a, summaries

    def app(self, standalone=True):
        module = 'dashboard.components.repair_process' if standalone else 'dashboard.pages.test_results'
        return AppTest.from_string(f"from dashboard.tests.test_dashboard import context\nfrom {module} import render\nrender(context('TEST', 'R0'))").run(timeout=90)

    def main(self, app):
        return next(frame.value for frame in app.dataframe if 'Metric' in frame.value
                    and frame.value.Metric.eq('Queries with complete token data').any())

    def test_pivot_exact_table3_values_and_order(self):
        runs, q, _, summaries = self.cohorts()
        pivot = m.process_report_pivot(summaries, q, list(runs), ['Easy', 'Medium', 'Human', 'All'])
        self.assertEqual(pivot.columns.tolist(), ['Metric'] + [f'{g} {s}' for g in ['Easy', 'Med', 'Human', 'All'] for s in d.STRATEGIES])
        pivot = pivot.set_index('Metric')
        for s in runs:
            source = summaries[s].set_index('metric')
            for displayed, label in m.PROCESS_REPORT_ROWS.items():
                for prefix, group in [('Easy','Easy'),('Med','Medium'),('Human','Human'),('All','All')]:
                    if label:
                        self.assertEqual(pivot.loc[displayed, f'{prefix} {s}'], float(source.loc[label, group]))
                    else:
                        self.assertTrue(pd.isna(pivot.loc[displayed, f'{prefix} {s}']))

    def test_filters_and_csv_dataframe(self):
        app = self.app(); self.assertFalse(app.exception)
        app.multiselect(key='process_report_strategies').set_value(['R2', 'R4']).run(timeout=90)
        app.selectbox(key='process_report_difficulty').select('Medium').run(timeout=90)
        pivot = self.main(app)
        self.assertEqual(pivot.columns.tolist(), ['Metric', 'Med R2', 'Med R4'])
        with patch('dashboard.components.common.st.download_button') as download, patch('dashboard.components.common.st.dataframe') as display:
            table(pivot, 'Table 3 process comparison')
            pd.testing.assert_frame_equal(display.call_args.args[0].data, pivot)
            self.assertEqual(download.call_args.args[1], pivot.to_csv(index=False).encode())
            self.assertEqual(pd.read_csv(StringIO(download.call_args.args[1].decode())).columns.tolist(), pivot.columns.tolist())

    def test_missing_and_future_r0_r1(self):
        self.repo.write_reporting(['R2', 'R3', 'R4'])
        app = self.app(standalone=False); self.assertFalse(app.exception)
        self.assertNotIn('All R0', self.main(app)); self.assertNotIn('All R1', self.main(app))
        self.repo.write_reporting()
        app = self.app(); self.assertFalse(app.exception)
        self.assertIn('All R0', self.main(app)); self.assertIn('All R1', self.main(app))

    def test_arbitrary_cohort_sizes(self):
        for size in (1, 13, 37):
            fixture = Repository(size=size, strategies=('R1',))
            try:
                run = next(r for r in d.discover_runs(fixture.root) if r.partition == 'TEST')
                folder = d.test_folder(run, fixture.reporting)
                q = {'R1': d.read_csv(folder / 'per_query.csv')}
                summaries = {'R1': d.read_csv(folder / 'table3_repair_process.csv')}
                pivot = m.process_report_pivot(summaries, q, ['R1'], ['All']).set_index('Metric')
                self.assertEqual(pivot.loc['Queries with complete token data', 'All R1'], size)
            finally:
                fixture.close()

    def test_token_coverage_and_lower_bound_preserve_missingness(self):
        _, q, _, _ = self.cohorts()
        frame = q['R0'].iloc[:2].copy()
        frame['tokens_spent'] = [100., None]; frame['tokens_spent_known'] = [100, 40]
        frame['rounds_missing_tokens'] = [0, 2]
        summary = m.team_table(frame, 'process')
        costs = m.process_cost_detail({'R0': frame}, {'R0': summary}, ['R0'], 'All').iloc[0]
        self.assertEqual(costs['Queries'], 2); self.assertEqual(costs['Complete-token queries'], 1)
        self.assertEqual(costs['Token completeness (%)'], 50)
        self.assertEqual(costs['Avg tokens/query (complete)'], 100)
        self.assertEqual(costs['Avg tokens/query lower bound'], 70)
        self.assertEqual(costs['Missing-token rounds'], 2)
        frame['tokens_spent'] = [0., None]
        costs = m.process_cost_detail({'R0': frame}, {'R0': m.team_table(frame, 'process')}, ['R0'], 'All').iloc[0]
        self.assertEqual(costs['Avg tokens/query (complete)'], 0)
        self.assertEqual(costs['Complete-token queries'], 1)

    def test_low_completeness_warning(self):
        rows, _ = self.repo.rows[('TEST', 'R0')]
        for r in rows[1:]:
            r.update(tokens_spent=None, tokens_spent_known=20, rounds_missing_tokens=2)
        self.repo.write_reporting()
        app = self.app(); self.assertFalse(app.exception)
        self.assertTrue(any('Low token completeness' in w.value for w in app.warning))

    def configured_events(self):
        runs, q, a, _ = self.cohorts()
        frame = q['R0'].iloc[:1].copy(); uid = frame.query_uid.iloc[0]
        bundles = json.loads(json.dumps(d.checkpoints(runs['R0'])))
        cp = bundles[uid]['checkpoints'][0]
        initial = cp['initial_verification']['translated_plan']
        for i, entry in enumerate(cp['repair_history'][1:]):
            entry['repair_attempt']['failed_model_calls'] = 1 if i == 2 else 0
            entry['repair_attempt']['total_tokens_delta'] = None if i == 1 else 100
            entry['verification']['translated_plan'] = initial if i < 2 else {'changed': True}
            entry['repair_attempt']['repair_metadata']['llm_cache_hits'] = 0 if i == 1 else 1
        frame['rounds'] = 3; frame['changed'] = 1; frame['unchanged_cache'] = 1; frame['unchanged_other'] = 1
        return frame, m.process_round_events(frame, a['R0'], bundles)

    def test_exact_cache_vs_other_classification_and_overlapping_failure(self):
        frame, events = self.configured_events()
        self.assertEqual(events['plan changed'].tolist(), [0, 0, 1])
        self.assertEqual(events['unchanged cache'].tolist(), [1, 0, 0])
        self.assertEqual(events['unchanged new request'].tolist(), [0, 1, 0])
        result = m.process_outcomes(frame, events).set_index('Outcome')
        self.assertEqual(result.loc['Model call failed (overlapping)', 'Count'], 1)
        self.assertAlmostEqual(result['% of rounds'].iloc[:3].sum(), 100)
        self.assertGreater(result['% of rounds'].sum(), 100)

    def test_round_tokens_missing_are_not_zero(self):
        _, events = self.configured_events()
        result = m.process_round_table(events).set_index('Metric')
        self.assertEqual(result.columns.tolist(), ['Round 1', 'Round 3', 'Round 9'])
        self.assertTrue(pd.isna(result.loc['Avg tokens (known counts only)', 'Round 3']))
        self.assertEqual(result.loc['Missing token counts', 'Round 3'], 1)
        self.assertEqual(result.loc['Avg tokens (known counts only)', 'Round 1'], 100)
        self.assertEqual(result.loc['% model call failures', 'Round 9'], 100)

    def test_changed_effect_uses_candidate_even_if_rejected(self):
        runs, q, a, _ = self.cohorts()
        frame = q['R0'].iloc[:1]; uid = frame.query_uid.iloc[0]
        bundles = json.loads(json.dumps(d.checkpoints(runs['R0'])))
        cp = bundles[uid]['checkpoints'][0]
        cp['repair_history'][1]['accepted'] = False
        events = m.process_round_events(frame, a['R0'], bundles)
        self.assertEqual(events.iloc[0]['PC delta changed'], 1)
        self.assertEqual(events.iloc[0]['CS delta changed'], -1)
        self.assertEqual(events.iloc[1]['PC delta changed'], 1)  # Rejection preserves the original before state.
        self.assertEqual(events.iloc[1]['CS delta changed'], -1)

    def test_unknown_to_true_counts_toward_existing_pc_delta(self):
        runs, q, a, _ = self.cohorts()
        frame = q['R0'].iloc[:1]; uid = frame.query_uid.iloc[0]
        bundles = json.loads(json.dumps(d.checkpoints(runs['R0'])))
        cp = bundles[uid]['checkpoints'][0]
        cp['repair_history'][0]['verification']['personal_constraints'] = [None, False]
        events = m.process_round_events(frame, a['R0'], bundles)
        self.assertEqual(events.iloc[0]['PC delta changed'], 2)

    def test_missing_classification_or_failure_counter_is_unavailable(self):
        frame, events = self.configured_events()
        events.loc[0, 'failed model calls'] = None
        result = m.process_outcomes(frame, events).set_index('Outcome')
        self.assertTrue(pd.isna(result.loc['Model call failed (overlapping)', 'Count']))
        events.loc[0, 'plan changed'] = None
        detail = m.process_round_table(events).set_index('Metric')
        self.assertTrue(pd.isna(detail.loc['# plan changed', 'Round 1']))
        _, q, _, summaries = self.cohorts()
        result = m.process_report_pivot(summaries, q, ['R0'], ['All']).set_index('Metric')
        self.assertTrue(pd.isna(result.loc['% rounds: model call failed', 'All R0']))

    def test_missing_verification_does_not_invent_unchanged(self):
        runs, q, a, _ = self.cohorts(); frame = q['R0'].iloc[:1]; uid = frame.query_uid.iloc[0]
        bundles = json.loads(json.dumps(d.checkpoints(runs['R0'])))
        bundles[uid]['checkpoints'][0]['repair_history'][1]['verification'].pop('translated_plan')
        events = m.process_round_events(frame, a['R0'], bundles)
        self.assertTrue(pd.isna(events.iloc[0]['unchanged new request']))

    def test_round_comparison_is_round_only_and_chart_matches_cells(self):
        _, events = self.configured_events()
        tables = {'R0': m.process_round_table(events), 'R2': m.process_round_table(events[events.step != 3])}
        comparison, points = m.process_round_comparison(tables, 'Plan-change rate')
        self.assertEqual(comparison.columns.tolist(), ['Strategy', 'Round 1', 'Round 3', 'Round 9'])
        figure = reporting.round_chart(points, 'Plan-change rate', '% plan changed')
        for trace in figure.data:
            for step, value in zip(trace.x, trace.y):
                expected = comparison.set_index('Strategy').loc[trace.name, f'Round {step}']
                self.assertTrue(pd.isna(value)) if pd.isna(expected) else self.assertEqual(value, expected)

    def test_incompatible_populations_block_process_comparison(self):
        runs, _, _, _ = self.cohorts()
        p = Path(runs['R1'].path) / 'run_manifest.json'; manifest = d.read_json(p)
        manifest['query_uids'] = manifest['query_uids'][:-1]; p.write_text(json.dumps(manifest))
        rows, refs = self.repo.rows[('TEST', 'R1')]; self.repo.rows[('TEST', 'R1')] = (rows[:-1], refs)
        self.repo.write_reporting()
        app = self.app(); self.assertFalse(app.exception)
        self.assertTrue(any('different query populations' in w.value for w in app.warning))
        self.assertFalse(any('Metric' in x.value and x.value.Metric.eq('Queries with complete token data').any() for x in app.dataframe))

    def test_secondary_counters_require_complete_query_coverage(self):
        _, q, a, _ = self.cohorts()
        diagnostics = m.process_additional_diagnostics(q['R0'], a['R0'][a['R0'].step == 1]).set_index('Metric')
        self.assertTrue(pd.isna(diagnostics.loc['Mean recorded model calls/query', 'Value']))

    def test_pc_cs_tables_remain_present_and_unchanged(self):
        app = self.app(standalone=False); self.assertFalse(app.exception)
        for metric in ('Avg PC per query', 'Avg CS per query', 'Queries with complete token data'):
            self.assertTrue(any('Metric' in x.value and x.value.Metric.eq(metric).any() for x in app.dataframe))


if __name__ == '__main__':
    unittest.main()
