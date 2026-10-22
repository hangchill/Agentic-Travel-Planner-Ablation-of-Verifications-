
import unittest
from copy import deepcopy
from chinatravel.agent.nesy_verifier.shared_verifier import (check_personal_constraints,)
from chinatravel.agent.nesy_verifier.repair_strategies.r1 import (R1TargetedRepair,)

class TestR1Integration(unittest.TestCase):

    def test_targeted_repair_fixes_real_constraint(self):
        # a genuine violated constraint: the trip has lunch, but no dinner.
        problem = {"nature_language": "Include both lunch and dinner",
                   "hard_logic_py": [
                       "result = False\n"
                       "for activity in allactivities(plan):\n"
                       "    if activity_type(activity) == 'dinner':\n"
                       "        result = True\n"],}
        itinerary = [{"day": 1,
                      "activities": [
                          {"type": "lunch",
                           "position": "Restaurant A",
                           "start_time": "12:00",
                           "end_time": "13:00",},
                           {"type": "dinner",
                            "position": "Restaurant B",
                            "start_time": "18:00",
                            "end_time": "19:00",},],}]
        # the constraint above is actually satisfied by this plan, so use a violated position requirement instead
        before_plan = {"itinerary": deepcopy(itinerary)}
        before_states, before_errors = check_personal_constraints(
            problem, before_plan)
        self.assertEqual(before_errors, [])
        # simulated verifier failure to test the repair path
        simulated_verification = {"personal_constraints": [False]}
        def mock_llm(messages, one_line=False):
            return ('{"type": "dinner", '
                    '"position": "Restaurant C", '
                    '"start_time": "18:00", '
                    '"end_time": "19:00"}')
        result = R1TargetedRepair().repair(
            problem=problem, raw_plan=itinerary,
            verification_results=simulated_verification,
            context={"restaurant_info": "Restaurant C"},
            llm=mock_llm,)
        after_plan = {"itinerary": result.repaired_plan}
        after_states, after_errors = check_personal_constraints(
            problem, after_plan)
        self.assertEqual(after_errors, [])
        self.assertEqual(after_states, [True])

    def test_real_violation_resolved(self):
        problem = {"nature_language": "Include a dinner at Restaurant B",
                   "hard_logic_py": [
                       "result = False\n"
                       "for activity in allactivities(plan):\n"
                       "    if activity_type(activity) == 'dinner':\n"
                       "        if activity_position(activity) == 'Restaurant B':\n"
                       "            result = True\n"],}
        itinerary = [{"day": 1,
                      "activities": [
                          {"type": "dinner",
                           "position": "Restaurant A",
                           "start_time": "18:00",
                           "end_time": "19:00",},
                           {"type": "attraction",
                            "position": "Museum",
                            "start_time": "15:00",
                            "end_time": "17:00",},],}]
        before_states, before_errors = check_personal_constraints(
            problem, {"itinerary": deepcopy(itinerary)})
        self.assertEqual(before_errors, [])
        self.assertEqual(before_states, [False])

        def mock_llm(messages, one_line=False):
            return ('{"type": "dinner", '
                    '"position": "Restaurant B", '
                    '"start_time": "18:00", '
                    '"end_time": "19:00"}')
        result = R1TargetedRepair().repair(
            problem=problem, raw_plan=itinerary,
            verification_results={"personal_constraints": before_states},
            context={"restaurant_info": "Restaurant B"},
            llm=mock_llm,)
        after_states, after_errors = check_personal_constraints(
            problem, {"itinerary": result.repaired_plan})
        self.assertEqual(after_errors, [])
        self.assertEqual(after_states, [True])
        self.assertEqual(result.repaired_plan[0]["activities"][0]["position"],
                         "Restaurant B",)
        self.assertEqual(result.repaired_plan[0]["activities"][1],
                         itinerary[0]["activities"][1],)


    def test_r1_repair_introduces_budget_regression(self):
        # Constraint 1: Dinner must be at Restaurant B
        # Constraint 2: Total activity cost must be <= 100
        problem = {"nature_language": (
            "Have dinner at Restaurant B, "
            "with a total activity budget of 100."),
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
                      "activities": [
                          {"type": "dinner",
                           "position": "Restaurant A",
                           "start_time": "18:00",
                           "end_time": "19:00",
                           "cost": 50,},],}]
        before_states, before_errors = check_personal_constraints(
            problem, {"itinerary": deepcopy(itinerary)})
        self.assertEqual(before_errors, [])
        self.assertEqual(before_states, [False, True])

        def mock_llm(messages, one_line=False):
            return ('{"type": "dinner", '
                    '"position": "Restaurant B", '
                    '"start_time": "18:00", '
                    '"end_time": "19:00", '
                    '"cost": 150}')
        result = R1TargetedRepair().repair(
            problem=problem, raw_plan=itinerary,
            verification_results={"personal_constraints": before_states},
            context={"restaurant_info": "Restaurant B costs 150"},
            llm=mock_llm,)
        after_states, after_errors = check_personal_constraints(
            problem, {"itinerary": result.repaired_plan})
        self.assertEqual(after_errors, [])
        self.assertEqual(after_states, [True, False])

        # r1 repaired the original violation
        self.assertEqual(result.metadata["target_constraint_indices"], [1],)

        # r1 did not protect the previously satisfied budget
        self.assertEqual(result.repaired_plan[0]["activities"][0]["cost"], 150,)

if __name__ == "__main__":
    unittest.main()
