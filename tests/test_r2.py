import unittest
from unittest.mock import Mock, patch

from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
from chinatravel.agent.nesy_verifier.repair_strategies import create_repair_strategy
from chinatravel.agent.nesy_verifier.repair_strategies.r2 import R2ProtectedRepair


class R2ProtectedRepairTests(unittest.TestCase):
    def setUp(self):
        self.problem = {
            "uid": "r2-case",
            "people_number": 1,
            "start_city": "A",
            "target_city": "B",
            "nature_language": "Plan a short trip.",
            "hard_logic_py": ["result=False", "result=True", "result=True"],
        }
        self.context = {key: "travel data" for key in (
            "go_train_info", "go_flight_info", "back_train_info", "back_flight_info",
            "attraction_info", "restaurant_info", "accommodation_info",
            "innercity_transport_info",
        )}
        self.current = [{"day": 1, "activities": [{"position": "Current"}]}]
        self.candidate = [{"day": 1, "activities": [{"position": "Candidate"}]}]

    def test_selects_one_failed_target_and_protects_passed_constraints(self):
        strategy = R2ProtectedRepair()
        llm = Mock(return_value='"activities": [{"position": "Candidate"}]}]')
        verification = {
            "personal_constraints": [False, True, True],
            "error_info": ["Personal constraint 1 failed: result=False", "other feedback"],
        }

        result = strategy.repair(self.problem, self.current, verification, self.context, llm)

        self.assertEqual(result.repaired_plan, [{"day": 1, "activities": [{"position": "Candidate"}]}])
        self.assertEqual(result.metadata["target_constraint_indices"], [1])
        self.assertEqual(result.metadata["feedback_personal_constraint_indices"], [1])
        self.assertEqual(result.metadata["protected_constraint_indices"], [2, 3])
        self.assertEqual(result.metadata["editable_scope"], "plan")
        prompt = llm.call_args.args[0][0]["content"]
        self.assertIn("Personal constraint 1 failed", prompt)
        self.assertNotIn("other feedback", prompt)

    def test_accepts_candidate_when_protected_constraints_remain_passed(self):
        strategy = R2ProtectedRepair()
        strategy._last_result = type("Result", (), {"metadata": {}})()
        self.assertTrue(strategy.accept(
            {"personal_constraints": [False, True, True]},
            {"personal_constraints": [False, True, True]},
        ))
        self.assertNotIn("decision_reason", strategy._last_result.metadata)

    def test_rejects_regression_and_records_reason(self):
        strategy = R2ProtectedRepair()
        strategy._last_result = type("Result", (), {"metadata": {}})()
        self.assertFalse(strategy.accept(
            {"personal_constraints": [False, True, True]},
            {"personal_constraints": [True, False, True]},
        ))
        self.assertEqual(
            strategy._last_result.metadata["decision_reason"],
            "previously_satisfied_constraint_regressed",
        )

    def test_unverifiable_state_is_not_a_false_to_true_or_true_to_false_regression(self):
        strategy = R2ProtectedRepair()
        self.assertTrue(strategy.accept(
            {"personal_constraints": [False, True]},
            {"personal_constraints": [False, None]},
        ))

    def test_unusable_candidate_returns_unchanged_plan_with_failure_reason(self):
        strategy = R2ProtectedRepair()
        llm = Mock(return_value="not valid JSON")
        verification = {
            "personal_constraints": [False, True],
            "error_info": ["Personal constraint 1 failed: result=False"],
        }

        result = strategy.repair(self.problem, self.current, verification, self.context, llm)

        self.assertEqual(result.repaired_plan, self.current)
        self.assertEqual(result.metadata["failure_reason"], "no_valid_repair_candidate")

    def test_shared_loop_retains_rejected_candidate_but_rolls_back_current_plan(self):
        strategy = R2ProtectedRepair()
        initial = {
            "passed": False,
            "personal_constraints": [False, True],
            "error_info": ["Personal constraint 1 failed: result=False"],
        }
        proposed = {"passed": False, "personal_constraints": [True, False], "error_info": []}
        with patch.object(loop, "verify_plan", side_effect=[initial, proposed]):
            result = loop.run_repair_loop(
                self.problem, self.current, strategy, self.context,
                Mock(return_value='"activities": [{"position": "Candidate"}]}]'),
                None, max_steps=1,
            )

        attempt = result["history"][1]
        self.assertFalse(attempt["accepted"])
        self.assertEqual(attempt["candidate_plan"], self.candidate)
        self.assertEqual(result["raw_plan"], self.current)
        self.assertEqual(attempt["repair_attempt"]["decision_reason"],
                         "previously_satisfied_constraint_regressed")
        self.assertEqual(attempt["repair_attempt"]["protected_constraint_indices"], [2])

    def test_strategy_is_registered(self):
        self.assertIsInstance(create_repair_strategy("R2"), R2ProtectedRepair)


if __name__ == "__main__":
    unittest.main()
