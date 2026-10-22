import unittest
from chinatravel.agent.nesy_verifier.repair_strategies.r1 import (
    find_editable_slot, classify_failed_constraint, find_editable_slot, 
    replace_activity_slot, generate_replacement, R1TargetedRepair,
    find_candidate_slots, select_editable_slot, find_transport_slots, 
    replace_transport_slot, select_repair_target, localise_transport_error,
    lookup_transport_options, convert_transport_option,)
import json
from unittest.mock import patch


class TestR1(unittest.TestCase):
    def test_unique_restaurant(self):
        plan = [{"day": 1,
                 "activities": [
                    {"type": "attraction", "position": "Museum"},
                    {"type": "lunch", "position": "Restaurant A"},],}]
        self.assertEqual(find_editable_slot(plan, "dining"), (0, 1),)

    def test_multiple_restaurants(self):
        plan = [{"day": 1,
                 "activities": [
                    {"type": "lunch", "position": "Restaurant A"},
                    {"type": "dinner", "position": "Restaurant B"},],}]
        self.assertIsNone(find_editable_slot(plan, "dining"))
 
    def test_classify_malformed_constraint(self):
        problem = {"hard_logic_py": ["    result = True"]}
        family = classify_failed_constraint(problem, 1)
        self.assertIsNone(family)

    def test_classify_supported_dining_constraint(self):
        problem = {
            "hard_logic_py": [
                "result = False\n"
                "for activity in allactivities(plan):\n"
                "    if activity_type(activity) == 'lunch':\n"
                "        result = True\n"]}
        family = classify_failed_constraint(problem, 1)
        self.assertEqual(family, "dining")


    def test_replace_only_selected_slot(self):
        plan = [{"day": 1,
                 "activities": [
                     {"type": "attraction", "position": "Museum"},
                     {"type": "lunch", "position": "Restaurant A"},
                     {"type": "attraction", "position": "Park"},],}]
        replacement = {"type": "lunch",
                       "position": "Restaurant B",
                       "start_time": "12:00",
                       "end_time": "13:00",}    
        result = replace_activity_slot(plan, (0, 1), replacement,)
        self.assertEqual(
            result[0]["activities"][1]["position"], "Restaurant B",)
        self.assertEqual(result[0]["activities"][0],
                         plan[0]["activities"][0],)
        self.assertEqual(result[0]["activities"][2],
                         plan[0]["activities"][2],)
        self.assertEqual(plan[0]["activities"][1]["position"],
                          "Restaurant A",)

    def test_generate_replacement(self):
        plan = [{"day": 1,
                 "activities": [
                    {"type": "lunch", "position": "Restaurant A"}],}]
        def mock_llm(messages, one_line=False):
            return '{"type": "lunch", "position": "Restaurant B"}'
        replacement = generate_replacement(
            problem={"nature_language": "Find vegetarian food"},
            raw_plan=plan,
            slot=(0, 0),
            constraint_text="Restaurant must be vegetarian",
            context={"restaurant_info": "Restaurant B"},
            llm=mock_llm,)
        self.assertEqual(replacement["position"], "Restaurant B")
        self.assertEqual(replacement["type"], "lunch")

    def test_r1_complete_targeted_repair(self):
        plan = [{"day": 1, "activities": [
            {"type": "attraction", "position": "Museum"},
            {"type": "lunch", "position": "Restaurant A"},
            {"type": "attraction", "position": "Park"},],}]
        problem = {"nature_language": "Include lunch in the itinerary",
                   "hard_logic_py": ["result = False\n"
                                     "for activity in allactivities(plan):\n"
                                     "    if activity_type(activity) == 'lunch':\n"
                                     "        result = True\n"],}
        verification_results = {"personal_constraints": [False],}

        def mock_llm(messages, one_line=False):
            return json.dumps({"type": "lunch",
                               "position": "Restaurant B",
                               "start_time": "12:00","end_time": "13:00",})
        result = R1TargetedRepair().repair(
            problem=problem,
            raw_plan=plan,
            verification_results=verification_results,
            context={"restaurant_info": "Restaurant B"},
            llm=mock_llm,)
        self.assertEqual(
            result.repaired_plan[0]["activities"][1]["position"],
            "Restaurant B",)
        self.assertEqual(
            result.repaired_plan[0]["activities"][0],
            plan[0]["activities"][0],)
        self.assertEqual(
            result.repaired_plan[0]["activities"][2],
            plan[0]["activities"][2],)
        self.assertEqual(
            result.metadata["target_constraint_indices"],
            [1],)
        self.assertEqual(result.metadata["editable_scope"], 
                         "slot",)

    def test_find_multiple_candidate_slots(self):
        plan = [{"day": 1, 
                 "activities": [
                     {"type": "attraction", "position": "Museum"},
                     {"type": "lunch", "position": "Restaurant A"},
                     {"type": "dinner", "position": "Restaurant B"},],}]
        candidates = find_candidate_slots(plan, "dining")
        self.assertEqual(candidates, [(0, 1), (0, 2)])

    def test_select_editable_slot(self):
        plan = [{"day": 1,
                 "activities": [
                     {"type": "lunch", "position": "Restaurant A"},
                     {"type": "dinner", "position": "Restaurant B"},],}]
        candidates = [(0, 0), (0, 1)]
        def mock_llm(messages, one_line=False):
            return '{"day_index": 0, "activity_index": 1}'
        selected = select_editable_slot(
            problem={"nature_language": "Find a suitable dinner"},
            raw_plan=plan, candidates=candidates,
            constraint_text="Dinner must satisfy dietary requirements",
            llm=mock_llm,)
        self.assertEqual(selected, (0, 1))

    def test_reject_invalid_slot_selection(self):
        plan = [{"day": 1,
                 "activities": [
                     {"type": "lunch", "position": "Restaurant A"},
                     {"type": "dinner", "position": "Restaurant B"},],}]
        candidates = [(0, 0), (0, 1)]
        def mock_llm(messages, one_line=False):
            return '{"day_index": 5, "activity_index": 3}'
        selected = select_editable_slot(
            problem={"nature_language": "Find suitable food"},
            raw_plan=plan, candidates=candidates,
            constraint_text="Restaurant requirement",
            llm=mock_llm,)
        self.assertIsNone(selected)

    # full mock test 
    def test_r1_multiple_slots_complete_repair(self):
        plan = [{"day": 1,
                 "activities": [
                     {"type": "lunch", "position": "Restaurant A"},
                     {"type": "dinner", "position": "Restaurant B"},
                     {"type": "attraction", "position": "Museum"},],}]
        problem = {"nature_language": "Find a suitable dinner",
                   "hard_logic_py": [
                       "result = False\n"
                       "for activity in allactivities(plan):\n"
                       "    if activity_type(activity) == 'dinner':\n"
                       "        result = True\n"],}
        verification_results = {"personal_constraints": [False],}
        responses = iter([
            '{"day_index": 0, "activity_index": 1}',
            json.dumps({"type": "dinner",
                        "position": "Restaurant C",
                        "start_time": "18:00",
                        "end_time": "19:00",}),])
        def mock_llm(messages, one_line=False):
            return next(responses)
        result = R1TargetedRepair().repair(
            problem=problem, raw_plan=plan,
            verification_results=verification_results,
            context={"restaurant_info": "Restaurant C"},
            llm=mock_llm,) 
        self.assertEqual(result.repaired_plan[0]["activities"][1]["position"],
                         "Restaurant C",)
        self.assertEqual(result.repaired_plan[0]["activities"][0],
                         plan[0]["activities"][0],)
        self.assertEqual(result.repaired_plan[0]["activities"][2],
                         plan[0]["activities"][2],)
        self.assertEqual(result.metadata["target_constraint_indices"], [1],)
        self.assertEqual(result.metadata["editable_scope"], "slot")

    def test_malformed_slot_selection(self):
        plan = [{"day": 1,
                 "activities": [
                     {"type": "lunch", "position": "Restaurant A"},
                     {"type": "dinner", "position": "Restaurant B"},],}]
        def mock_llm(messages, one_line=False):
            return "not valid json"
        result = select_editable_slot(
            problem={"nature_language": "Find dinner"},
            raw_plan=plan, candidates=[(0, 0), (0, 1)],
            constraint_text="Dinner requirement", llm=mock_llm,)
        self.assertIsNone(result)

    def test_invalid_slot_selection_type(self):
        plan = [{"day": 1,
                 "activities": [
                     {"type": "lunch", "position": "Restaurant A"},
                     {"type": "dinner", "position": "Restaurant B"},],}]
        def mock_llm(messages, one_line=False):
            return '[0, 1]'
        result = select_editable_slot(
            problem={"nature_language": "Find dinner"},
            raw_plan=plan, candidates=[(0, 0), (0, 1)],
            constraint_text="Dinner requirement", llm=mock_llm,)
        self.assertIsNone(result)

    def test_invalid_replacement_preserves_plan(self):
        plan = [{"day": 1,
                 "activities": [
                     {"type": "lunch", "position": "Restaurant A"},],}]
        problem = {"nature_language": "Include a suitable lunch",
                   "hard_logic_py": [
                       "result = False\n"
                       "for activity in allactivities(plan):\n"
                       "    if activity_type(activity) == 'lunch':\n"
                       "        result = True\n"],}
        def mock_llm(messages, one_line=False):
            return "invalid json"
        result = R1TargetedRepair().repair(
            problem=problem, raw_plan=plan,
            verification_results={"personal_constraints": [False]},
            context={"restaurant_info": "Restaurant B"}, llm=mock_llm,)
        self.assertEqual(result.repaired_plan, plan)
        self.assertEqual(result.metadata["failure_reason"],
                         "invalid_replacement",)

    def test_find_transport_slots(self):
        plan = [{"day": 1,
                "activities": [
                    {"type": "lunch", "position": "Restaurant A"},
                    {"type": "attraction", 
                    "position": "Museum",
                    "transports": {"from": "Hotel",
                                    "to": "Museum",
                                    "start_time": "09:00",
                                    "end_time": "09:30",
                                    "mode": "taxi",
                                    "cost": 30,},},],}]
        self.assertEqual(find_transport_slots(plan), [(0, 1)])

    def test_replace_transport_only(self):
        plan = [{"day": 1,
                "activities": [{
                    "type": "attraction",
                    "position": "Museum",
                    "start_time": "10:00",
                    "end_time": "12:00",
                    "transports": {"from": "Hotel",
                                    "to": "Museum",
                                    "start_time": "09:00",
                                    "end_time": "09:30",
                                    "mode": "taxi",
                                    "cost": 30,},}],}]
        replacement = {"from": "Hotel",
                    "to": "Museum",
                    "start_time": "09:00",
                    "end_time": "09:40",
                    "mode": "metro",
                    "cost": 5,}
        result = replace_transport_slot(plan, (0, 0), replacement)
        self.assertEqual(result[0]["activities"][0]["transports"]["mode"], "metro",)
        self.assertEqual(result[0]["activities"][0]["position"], "Museum",)
        self.assertEqual(plan[0]["activities"][0]["transports"]["mode"], "taxi",)

    def test_r1_transport_repair(self):
        plan = [{"day": 1,
                 "activities": [{
                     "type": "attraction",
                     "position": "Museum",
                     "start_time": "10:00",
                     "end_time": "12:00",
                     "transports": {
                         "from": "Hotel",
                         "to": "Museum",
                         "start_time": "09:00",
                         "end_time": "09:30",
                         "mode": "taxi",
                         "cost": 30,},}],}]
        problem = {"nature_language": "Use metro instead of taxi",
                   "hard_logic_py": [
                       "result = False\n"
                       "for activity in allactivities(plan):\n"
                       "    if innercity_transport_type(activity_transports(activity)) == 'metro':\n"                       
                       "        result = True\n"],}
        verification_results = {"personal_constraints": [False]}
        def mock_llm(messages, one_line=False):
            return json.dumps({"from": "Hotel",
                               "to": "Museum",
                               "start_time": "09:00",
                               "end_time": "09:40",
                               "mode": "metro",
                               "cost": 5,})
        result = R1TargetedRepair().repair(
            problem=problem, raw_plan=plan,
            verification_results=verification_results,
            context={"innercity_transport_info": "metro available"},
            llm=mock_llm,)
        self.assertEqual(result.repaired_plan[0]["activities"][0]["transports"]["mode"], "metro",)
        self.assertEqual(result.repaired_plan[0]["activities"][0]["position"], "Museum",)

    def test_reject_missing_required_fields(self):
        plan = [{"day": 1,
                 "activities": [{
                     "type": "lunch",
                     "position": "Restaurant A",
                     "start_time": "12:00",
                     "end_time": "13:00",}],}]
        replacement = {"type": "lunch",
                       "position": "Restaurant B",}
        with self.assertRaises(ValueError):
            replace_activity_slot(plan, (0, 0), replacement)

    def test_skip_unlocalizable_constraint(self):
        plan = [{"day": 1,
                 "activities": [
                     {"type": "lunch", "position": "Restaurant A"},],}]
        problem = {"hard_logic_py": [
            "result = False",  
            "result = False\n"
            "for activity in allactivities(plan):\n"
            "    if activity_type(activity) == 'lunch':\n"
            "        result = True\n",],}
        target_idx, family, candidates = select_repair_target(
            problem, plan, [1, 2],)
        self.assertEqual(target_idx, 2)
        self.assertEqual(family, "dining")
        self.assertEqual(candidates, [(0, 0)])

    def test_localise_commonsense_transport_error(self):
        plan = [{"day": 1,
                 "activities": [{
                 "type": "attraction",
                 "position": "Nanjing Museum",
                 "transports": {
                     "from": "Nanjing South Railway Station",
                     "to": "Nanjing Museum",
                     "start_time": "10:27",
                     "end_time": "11:10",
                     "mode": "metro",
                     "cost": 5,},}],}]
        error = ("Unavailable Inner-City Transport information in 1, "
                 "from Nanjing South Railway Station to Nanjing Museum, "
                 "start_time 10:27, transport_type metro")
        slot = localise_transport_error(plan, error)
        self.assertEqual(slot, (0, 0))

    def test_lookup_transport_options(self):
        from unittest.mock import patch
        class FakeTransportation:
            def __init__(self, lang):
                self.lang = lang
            def goto(self, city, start, end, start_time, transport_type):
                if transport_type == "metro":
                    return "No solution"
                return [{"start": start,
                         "end": end,
                         "mode": transport_type,
                         "start_time": start_time,
                         "end_time": "10:30",
                         "cost": 5,}]
        with patch("chinatravel.environment.tools.transportation.apis.Transportation",
                   FakeTransportation,):
            options = lookup_transport_options(
                city="Nanjing",
                origin="Hotel",
                destination="Museum",
                start_time="10:00",)                   
            options = lookup_transport_options(
                city="Nanjing",
                origin="Hotel",
                destination="Museum",
                start_time="10:00",)
        self.assertEqual(len(options), 2)
        self.assertEqual([option["mode"] for option in options],
                         ["walk", "taxi"],)

    def test_convert_transport_option(self):
        original = {"from": "Hotel",
                    "to": "Museum",
                    "mode": "metro",
                    "start_time": "10:00",
                    "end_time": "10:40",
                    "cost": 5,}
        option = {"mode": "taxi",
                  "segments": [{
                      "start": "Hotel",
                      "end": "Museum",
                      "mode": "taxi",
                      "start_time": "10:00",
                      "end_time": "10:20",
                      "cost": 25,}],}
        replacement = convert_transport_option(option, original)
        self.assertEqual(replacement["mode"], "taxi")
        self.assertEqual(replacement["cost"], 25)
        self.assertEqual(replacement["from"], "Hotel")
        self.assertEqual(replacement["to"], "Museum")

    def test_commonsense_transport_repair(self):
        plan = [{"day": 1,
                 "activities": [{
                     "type": "attraction",
                     "position": "Museum",
                     "start_time": "10:30",
                     "end_time": "12:00",
                     "transports": {
                         "from": "Hotel",
                         "to": "Museum",
                         "start_time": "10:00",
                         "end_time": "10:30",
                         "mode": "metro",
                         "cost": 5,},}],}]
        problem = {"target_city": "Nanjing",
                   "lang": "en",
                   "hard_logic_py": [],}
        verification_results = {
            "personal_constraints": [],
            "commonsense_errors": [
                "Unavailable Inner-City Transport information in 1, "
                "from Hotel to Museum, start_time 10:00, "
                "transport_type metro"],}
        fake_options = [{
            "mode": "taxi",
            "segments": [{
                "start": "Hotel",
                "end": "Museum",
                "mode": "taxi",
                "start_time": "10:00",
                "end_time": "10:20",
                "cost": 25,}],}]
        with patch("chinatravel.agent.nesy_verifier.repair_strategies.r1.lookup_transport_options",
                   return_value=fake_options,):
            result = R1TargetedRepair().repair(
                problem=problem, raw_plan=plan,
                verification_results=verification_results,
                context={}, llm=None,)
        transport = result.repaired_plan[0]["activities"][0]["transports"]
        self.assertEqual(transport["mode"], "taxi")
        self.assertEqual(transport["cost"], 25)
        self.assertEqual(result.metadata["target_constraint_indices"], [])
        self.assertEqual(result.metadata["repair_source"], "transport_lookup")

if __name__ == "__main__":
    unittest.main()