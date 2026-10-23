import unittest
from copy import deepcopy
from unittest.mock import patch
from chinatravel.agent.nesy_verifier.shared_repair_loop import (
    run_repair_loop,)
from chinatravel.agent.nesy_verifier.shared_verifier import (
    check_personal_constraints,)
from chinatravel.agent.nesy_verifier.repair_strategies.r1 import (
    R1TargetedRepair,)

class TestR1SharedLoop(unittest.TestCase):

    def test_shared_loop_records_budget_regression(self):
        problem = {"uid": "offline_r1_regression",
                   "people_number": 1,
                   "start_city": "Beijing",
                   "target_city": "Beijing",
                   "nature_language": "Have dinner at Restaurant B within 100 yuan.",
                   "hard_logic_py": [
                       ("result = False\n"
                        "for activity in allactivities(plan):\n"
                        "    if activity_type(activity) == 'dinner':\n"
                        "        if activity_position(activity) == 'Restaurant B':\n"
                        "            result = True\n"),
                        ("total = 0\n"
                        "for activity in allactivities(plan):\n"
                        "    total += activity_cost(activity)\n"
                        "result = total <= 100\n"),],}
        itinerary = [{"day": 1,
                      "activities": [{
                          "type": "dinner",
                          "position": "Restaurant A",
                          "start_time": "18:00",
                          "end_time": "19:00",
                          "cost": 50,}],}]
        def mock_verifier(problem, plan, translate_fn=None):
            states, errors = check_personal_constraints(
                problem, plan)
            return {"personal_constraints": states,
                    "commonsense_errors": [],
                    "personal_errors": [],
                    "evaluation_errors": errors,
                    "passed": all(state is True for state in states)
                          and not errors,}
        def mock_llm(messages, one_line=False, json_mode=False):
            return ('{"type": "dinner", '
                    '"position": "Restaurant B", '
                    '"start_time": "18:00", '
                    '"end_time": "19:00", '
                    '"cost": 150}')
        with patch("chinatravel.agent.nesy_verifier.shared_repair_loop.verify_plan",
                   side_effect=mock_verifier,):
             output = run_repair_loop(
                 problem=problem, raw_plan=deepcopy(itinerary),
                 strategy=R1TargetedRepair(),
                 context={},
                 llm=mock_llm,
                translate_fn=None,
                max_steps=1,)

        self.assertEqual(len(output["history"]), 2)
        record = output["history"][1]["repair_attempt"]
        self.assertEqual(record["repair_strategy"], "R1")
        self.assertEqual(record["target_constraint_indices"], [1])
        self.assertEqual(record["before_personal_constraints"],
            [False, True],)
        self.assertEqual(
            record["after_personal_constraints"],
            [True, False],)
        self.assertEqual(record["fixed"], [1])
        self.assertEqual(record["newly_violated"], [2])
        self.assertEqual(record["editable_scope"], "slot")
        self.assertEqual(record["changed_slot_count"], 1)

    def test_r1_stops_after_no_progress(self):
        problem = {"uid": "offline_no_progress",
                   "people_number": 1,
                   "start_city": "Beijing",
                   "target_city": "Beijing",
                   "hard_logic_py": [],}
        itinerary = [{
            "day": 1,
            "activities": [{
                "type": "attraction",
                "position": "Museum",
                "start_time": "10:00",
                "end_time": "11:00",}],}]

        def mock_verifier(problem, plan, translate_fn=None):
            return {"personal_constraints": [],
                    "commonsense_errors": ["Unlocalizable error"],
                    "passed": False,}
        with patch(
            "chinatravel.agent.nesy_verifier.shared_repair_loop.verify_plan",
            side_effect=mock_verifier,):
            output = run_repair_loop(
                problem=problem, raw_plan=itinerary,
                strategy=R1TargetedRepair(),
                context={}, llm=None,
                translate_fn=None, max_steps=5,)

        # initial state + one no-progress attempt
        self.assertEqual(len(output["history"]), 2)
        attempt = output["history"][1]["repair_attempt"]
        self.assertEqual(attempt["changed_slot_count"], 0)
        self.assertEqual(
            attempt["repair_metadata"]["failure_reason"],
            "no_localizable_failure",)
        self.assertEqual(attempt["target_constraint_indices"], [])
        self.assertEqual(attempt["fixed"], [])
        self.assertEqual(attempt["newly_violated"], [])
        self.assertEqual(output["raw_plan"], itinerary)

if __name__ == "__main__":
    unittest.main()
