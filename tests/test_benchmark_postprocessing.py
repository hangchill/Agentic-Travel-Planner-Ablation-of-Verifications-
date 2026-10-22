"""Offline integration of accepted-final export and benchmark scoring."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chinatravel.evaluation.repair_comparison import _component, _save, _rebuild_indexes
from chinatravel.evaluation.export_final_plans import evaluate_repair_run


class BenchmarkPostprocessingTests(unittest.TestCase):
    def test_exact_train_population_accepted_plan_language_and_failed_population(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save(root / 'run_manifest.json', dict(run_id='train', query_uids=['train1', 'failed'],
                  repair_strategies_requested=['R0'], language='en', partition='train'))
            problem = dict(uid='train1', hard_logic_py=['result=True'])
            query = root / 'queries' / _component('train1')
            _save(query / 'initial_state.json', {'state': {'problem': problem}})
            accepted = dict(people_number=1, start_city='Beijing', target_city='Shanghai', itinerary=[])
            _save(query / (_component('R0') + '.json'), dict(
                  execution_status='completed', final_verification={'translated_plan': accepted},
                  candidate_plan={'rejected': True}))
            seen = []
            def evaluator(queries, plans, directory, **kwargs):
                seen.append((queries, plans, kwargs))
                self.assertEqual(plans, {'train1': accepted, 'failed': {}})
                self.assertEqual(kwargs['lang'], 'en')
                self.assertEqual(list(queries), ['train1', 'failed'])
                _save(directory / 'benchmark_summary.json', {'schema_pass_rate': 50})
                return {'schema_pass_rate': 50}
            evaluate_repair_run(root, {'failed': {'uid': 'failed', 'hard_logic_py': []},
                                     'test1': {'uid': 'test1'}}, evaluator=evaluator)
            self.assertEqual(len(seen), 1)
            output = root / 'benchmark_eval' / _component('R0')
            self.assertEqual(json.loads((output / 'plans/train1.json').read_text()), accepted)
            population = json.loads((output / 'evaluation_population.json').read_text())
            self.assertEqual(population['partition'], 'train')
            self.assertEqual(population['statuses']['failed'], 'initial_generation_failed')
            self.assertTrue((output / 'benchmark_summary.json').exists())

    def test_initial_failures_have_summary_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save(root / 'run_manifest.json', dict(run_id='run', query_uids=['q'],
                  repair_strategies_requested=['R0', 'R1']))
            _save(root / 'queries' / _component('q') / 'initial_failure.json', {'exception': 'failed'})
            _rebuild_indexes(root)
            with (root / 'summaries.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(r['execution_status'] == 'initial_generation_failed' for r in rows))
            self.assertEqual((root / 'attempts.jsonl').read_text(), '')

    def test_benchmark_aggregate_schema_and_checker_reuse(self):
        import pandas as pd
        from eval_exp import evaluate_final_plans
        rows = pd.DataFrame([{'data_id': 'q', 'result': 1}])
        with tempfile.TemporaryDirectory() as tmp, \
             patch('chinatravel.evaluation.schema_constraint.evaluate_schema_constraints', return_value=(100, rows, ['q'])), \
             patch('chinatravel.evaluation.commonsense_constraint.evaluate_commonsense_constraints', return_value=(20, 30, rows, ['q'])) as comm, \
             patch('chinatravel.evaluation.hard_constraint.evaluate_hard_constraints_v2', return_value=(40, 50, 60, 70, rows, ['q'])):
            result = evaluate_final_plans({'q': {'hard_logic_py': []}}, {'q': {}}, tmp, lang='zh')
            self.assertEqual(result['conditional_lpr'], 70)
            self.assertEqual(result['all_pass_ratio'], 100)
            self.assertEqual(comm.call_args.kwargs['lang'], 'zh')
            self.assertEqual(json.loads((Path(tmp) / 'benchmark_summary.json').read_text()), result)
            for filename in ('schema.csv', 'commonsense.csv', 'logical_py.csv'):
                self.assertTrue((Path(tmp) / filename).exists())
