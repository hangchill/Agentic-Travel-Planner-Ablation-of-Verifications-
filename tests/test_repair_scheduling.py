"""Deterministic shared 5+1 scheduling, no external resources."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
from chinatravel.agent.nesy_verifier.repair_strategies.base import RepairResult
from chinatravel.evaluation.repair_attempt import RepairAttemptRecord
from chinatravel.evaluation.regression_matrix import build_regression_matrix
from chinatravel.evaluation.repair_metrics import summarize_repair_history


def verification(personal=False, commonsense=True):
    return dict(personal_constraints=[personal, True], commonsense_errors=['transport failure'] if commonsense else [],
                passed=personal is True and not commonsense, error_info=[])


class SchedulingTests(unittest.TestCase):
    def run_loop(self, states, initial=None, budget=6, reject=False, noop=False, name='R0', reported_phase=None):
        phases = []
        class Strategy:
            def repair(self, **kwargs):
                phases.append(kwargs['context']['repair_phase'])
                return RepairResult(deepcopy(kwargs['raw_plan']) if noop else [{'day': len(phases)}],
                                    {'strategy': name, 'target_constraint_indices': [1], **({'repair_phase': reported_phase} if reported_phase else {})})
            def accept(self, *args): return not reject
        problem = dict(uid='q', people_number=1, start_city='A', target_city='B',
                       hard_logic_py=['result=day_count(plan)==2',
                        'cost=0\nfor activity in allactivities(plan):\n  cost+=activity_cost(activity)\nresult=cost<=1000'])
        with patch.object(loop, 'verify_plan', side_effect=states):
            result = loop.run_repair_loop(problem, [{'day': 0}], Strategy(), {}, SimpleNamespace(), None,
                                          max_steps=budget, initial_verification=initial or verification())
        self.phases = phases
        return result

    def test_early_personal_success(self):
        result = self.run_loop([verification(), verification(), verification(True), verification(True, False)])
        self.assertEqual(self.phases, ['personal'] * 3 + ['commonsense'])
        self.assertEqual(summarize_repair_history(result['history'])['attempts'], 4)

    def test_full_five_plus_one_and_large_budget_clamped(self):
        self.run_loop([verification()] * 6, budget=100)
        self.assertEqual(self.phases, ['personal'] * 5 + ['commonsense'])

    def test_regression_recovery(self):
        self.run_loop([verification(), verification(True), verification(False, False), verification(True, False)])
        self.assertEqual(self.phases, ['personal', 'personal', 'commonsense', 'personal'])

    def test_no_commonsense_stops_without_attempt(self):
        self.run_loop([], initial=verification(True, False))
        self.assertEqual(self.phases, [])
        self.run_loop([verification(True, False)], initial=verification(False, False))
        self.assertEqual(self.phases, ['personal'])

    def test_unknown_is_not_satisfied(self):
        self.run_loop([verification(None)] * 6, initial=verification(None))
        self.assertEqual(self.phases, ['personal'] * 5 + ['commonsense'])

    def test_r1_noop_preserves_reserved_opportunity(self):
        self.run_loop([verification()] * 6, name='R1', noop=True)
        self.assertEqual(self.phases, ['personal'] * 5 + ['commonsense'])
        self.run_loop([verification(False, False)], initial=verification(False, False), name='R1', noop=True)
        self.assertEqual(self.phases, ['personal'])

    def test_rejection_consumes_budget(self):
        result = self.run_loop([verification(True, False)] * 6, reject=True)
        self.assertEqual(len(result['history']) - 1, 6)
        self.assertEqual(self.phases, ['personal'] * 5 + ['commonsense'])

    def test_commonsense_matrix_exclusion_and_historical_reading(self):
        result = self.run_loop([verification(False, False), verification(True, False)], initial=verification(True))
        payload = result['history'][1]['repair_attempt']
        self.assertEqual(payload['repair_phase'], 'commonsense')
        self.assertEqual(payload['target_constraint_indices'], [])
        self.assertEqual(payload['target_commonsense_errors'], ['transport failure'])
        analysis = build_regression_matrix([payload])
        self.assertTrue(all(row['eligible_count'] == 0 for row in analysis['aggregate']))
        payload.pop('repair_phase'); payload.pop('target_commonsense_errors')
        self.assertIsNone(RepairAttemptRecord.from_dict(payload).repair_phase)

    def test_recovery_can_use_all_remaining_personal_budget(self):
        self.run_loop([verification(), verification(), verification(True),
                       verification(False, False), verification(False, False), verification(True, False)])
        self.assertEqual(self.phases, ['personal'] * 3 + ['commonsense', 'personal', 'personal'])

    def test_r1_explicit_commonsense_overrides_concurrent_personal_failure(self):
        from chinatravel.agent.nesy_verifier.repair_strategies.r1 import R1TargetedRepair
        with patch('chinatravel.agent.nesy_verifier.repair_strategies.r1.repair_commonsense_transport',
                   return_value=RepairResult([], {'target_constraint_indices': []})) as commonsense:
            result = R1TargetedRepair().repair({}, [], verification(), {'repair_phase': 'commonsense'}, None)
        commonsense.assert_called_once()
        self.assertEqual(result.metadata['target_constraint_indices'], [])

    def test_no_repeat_commonsense_and_unknown_recovery(self):
        self.run_loop([verification(True)], initial=verification(True))
        self.assertEqual(self.phases, ['commonsense'])
        self.run_loop([verification(None, False), verification(True, False)], initial=verification(True))
        self.assertEqual(self.phases, ['commonsense', 'personal'])

    def test_reported_phase_mismatch_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, 'disagrees with scheduled'):
            self.run_loop([], reported_phase='commonsense')

    def test_explicit_small_budget(self):
        self.run_loop([verification()] * 2, budget=2)
        self.assertEqual(self.phases, ['personal', 'personal'])
        self.run_loop([], budget=0)
        self.assertEqual(self.phases, [])
