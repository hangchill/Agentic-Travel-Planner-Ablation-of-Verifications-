"""Deterministic shared-loop scheduling, no external resources.

Rule: up to 6 rounds; stop early only on a pass or when every personal
constraint passes with no commonsense errors. Personal rounds first (at most 5),
then commonsense rounds while errors remain, back to personal if a commonsense
round breaks a personal constraint and budget is left."""
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
                unchanged = noop is True or (isinstance(noop, (list, tuple, set)) and len(phases) in noop)
                return RepairResult(deepcopy(kwargs['raw_plan']) if unchanged else [{'day': len(phases)}],
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
        # R1 no-ops no longer end the run: with no commonsense errors, every round stays personal.
        result = self.run_loop([verification(False, False)] * 6, initial=verification(False, False),
                               name='R1', noop=True)
        self.assertEqual(self.phases, ['personal'] * 6)
        self.assertEqual(len(result['history']) - 1, 6)

    def test_r1_recovery_noop_does_not_stop_remaining_recovery(self):
        result = self.run_loop([verification(), verification(True), verification(False, False),
                                verification(False, False), verification(True, False)],
                               name='R1', noop=[4])
        self.assertEqual(self.phases, ['personal', 'personal', 'commonsense', 'personal', 'personal'])
        self.assertEqual(result['history'][4]['candidate_plan'], result['history'][3]['candidate_plan'])
        self.assertEqual(summarize_repair_history(result['history'])['attempts'], 5)

    def test_repeated_r1_recovery_noops_exhaust_budget(self):
        for state in (False, None):
            with self.subTest(state=state):
                result = self.run_loop([verification(), verification(True), verification(state, False)] +
                                       [verification(state, False)] * 3, name='R1', noop=[4, 5, 6], budget=100)
                self.assertEqual(self.phases, ['personal', 'personal', 'commonsense'] + ['personal'] * 3)
                self.assertEqual(len(result['history']) - 1, 6)
                self.assertEqual(self.phases.count('personal'), 5)

    def test_r1_commonsense_noop_still_allows_recovery(self):
        self.run_loop([verification(True), verification(False, False), verification(True, False)],
                      name='R1', noop=[2])
        self.assertEqual(self.phases, ['personal', 'commonsense', 'personal'])

    def test_r1_last_commonsense_regression_cannot_expand_budget(self):
        result = self.run_loop([verification()] * 5 + [verification(False, False)], name='R1', noop=[6])
        self.assertEqual(self.phases, ['personal'] * 5 + ['commonsense'])
        self.assertEqual(len(result['history']) - 1, 6)

    def test_rejection_consumes_budget(self):
        result = self.run_loop([verification(True, False)] * 6, reject=True)
        self.assertEqual(len(result['history']) - 1, 6)
        self.assertEqual(self.phases, ['personal'] * 5 + ['commonsense'])

    def test_commonsense_matrix_capture_and_historical_reading(self):
        result = self.run_loop([verification(False, False), verification(True, False)], initial=verification(True))
        payload = result['history'][1]['repair_attempt']
        self.assertEqual(payload['repair_phase'], 'commonsense')
        self.assertEqual(payload['target_constraint_indices'], [])
        self.assertEqual(payload['target_commonsense_errors'], ['transport failure'])
        # The changed commonsense attempt regressed a previously-passing personal
        # family and is now captured under the commonsense_repair source row.
        analysis = build_regression_matrix([payload])
        eligible = [row for row in analysis['aggregate'] if row['eligible_count']]
        self.assertTrue(eligible)
        self.assertTrue(all(row['source_family'] == 'commonsense_repair' for row in eligible))
        regressed = next(row for row in eligible if row['perspective'] == 'candidate'
                         and row['destination_family'] == 'trip_specification')
        self.assertEqual(regressed['regression_count'], 1)
        self.assertEqual(regressed['support_count'], 1)
        self.assertEqual(regressed['regression_rate'], 1.0)
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

    def test_commonsense_repeats_until_budget_and_unknown_recovery(self):
        result = self.run_loop([verification(True)] * 6, initial=verification(True))
        self.assertEqual(self.phases, ['commonsense'] * 6)
        self.assertEqual(len(result['history']) - 1, 6)
        self.run_loop([verification(None, False), verification(True, False)], initial=verification(True))
        self.assertEqual(self.phases, ['commonsense', 'personal'])

    def test_commonsense_stops_once_errors_are_gone(self):
        self.run_loop([verification(True), verification(True, False)], initial=verification(True))
        self.assertEqual(self.phases, ['commonsense', 'commonsense'])

    def test_broken_personal_returns_to_personal_then_commonsense_again(self):
        self.run_loop([verification(True), verification(False), verification(True),
                       verification(True), verification(True), verification(True)], initial=verification(True))
        self.assertEqual(self.phases, ['commonsense', 'commonsense', 'personal',
                                       'commonsense', 'commonsense', 'commonsense'])

    def test_break_on_last_round_ends_run(self):
        result = self.run_loop([verification(True)] * 5 + [verification(False)], initial=verification(True))
        self.assertEqual(self.phases, ['commonsense'] * 6)
        self.assertEqual(result['verification']['personal_constraints'][0], False)

    def test_personal_failing_without_commonsense_uses_all_rounds(self):
        self.run_loop([verification(False, False)] * 6, initial=verification(False, False))
        self.assertEqual(self.phases, ['personal'] * 6)

    def test_nothing_to_target_stops_even_if_not_passed(self):
        technical = dict(verification(True, False), passed=False)
        self.run_loop([], initial=technical)
        self.assertEqual(self.phases, [])

    def test_r1_noops_run_full_budget(self):
        for initial in (verification(True), verification()):
            with self.subTest(initial=initial):
                result = self.run_loop([deepcopy(initial)] * 6, initial=initial, name='R1', noop=True)
                self.assertEqual(len(result['history']) - 1, 6)

    def test_reported_phase_mismatch_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, 'disagrees with scheduled'):
            self.run_loop([], reported_phase='commonsense')

    def test_explicit_small_budget(self):
        self.run_loop([verification()] * 2, budget=2)
        self.assertEqual(self.phases, ['personal', 'personal'])
        self.run_loop([], budget=0)
        self.assertEqual(self.phases, [])
