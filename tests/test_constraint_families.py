"""Real-style repository templates, analyzed without DSL execution or DB imports."""

from copy import deepcopy
import json
import unittest

from chinatravel.evaluation.constraint_families import (
    CONSTRAINT_FAMILIES, NORMALIZER_VERSION, classify_constraint, classify_constraints,
)


def classify(code, **source):
    return classify_constraint({"constraint_index": 1, "hard_logic_py": code, **source})


PATTERNS = {
    "trip_specification": [
        "result=(day_count(plan)==3)", "result=(people_count(plan)==2)",
    ],
    "party_resources": [
        "result=True\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity) in ['attraction','train','airplane'] and activity_tickets(activity)!=2: result=False\n"
        "  if innercity_transport_type(activity_transports(activity))=='metro' and metro_tickets(activity_transports(activity))!=2: result=False",
        "result=True\nfor activity in allactivities(plan):\n"
        "  if innercity_transport_type(activity_transports(activity))=='taxi' and taxi_cars(activity_transports(activity))!=1: result=False",
    ],
    "monetary_budget": [
        "total=0\nfor activity in allactivities(plan):\n"
        "  total+=activity_cost(activity)+innercity_transport_cost(activity_transports(activity))\nresult=total<=6000",
        "cost=0\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity) in ['breakfast','lunch','dinner']: cost+=activity_cost(activity)\nresult=cost<=300",
    ],
    "accommodation": [
        "result=True\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity)=='accommodation' and room_count(activity)!=1: result=False\n"
        "  if activity_type(activity)=='accommodation' and room_type(activity)!=2: result=False",
        "names=set()\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity)=='accommodation': names.add(activity_position(activity))\nresult={'Hotel A'}<=names",
        "result=True\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity)=='accommodation' and accommodation_type(activity,target_city(plan))!='泳池': result=False",
    ],
    "dining": [
        "names=set()\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity) in ['breakfast','lunch','dinner']: names.add(activity_position(activity))\nresult={'Restaurant A'}<=names",
        "types=set()\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity) in ['breakfast','lunch','dinner']: types.add(restaurant_type(activity,target_city(plan)))\nresult={'江浙菜'}<=types",
        "types=set()\nfor activity in dayactivities(plan,1):\n"
        "  if activity_type(activity) in ['breakfast','lunch','dinner']: types.add(activity_type(activity))\nresult={'lunch','dinner'}<=types",
    ],
    "attraction": [
        "count=0\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity)=='attraction': count+=1\nresult=count==3",
        "count=0\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity)=='attraction' and activity_cost(activity)==0: count+=1\nresult=count>=2",
        "types=set()\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity)=='attraction': types.add(attraction_type(activity,target_city(plan)))\nresult={'公园'}<=types",
    ],
    "transport_mode": [
        "modes=set()\nfor activity in allactivities(plan):\n"
        "  if activity_transports(activity)!=[]: modes.add(innercity_transport_type(activity_transports(activity)))\nresult=modes<={'metro'}",
        "modes=set()\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity) in ['train','airplane']: modes.add(intercity_transport_type(activity))\nresult=not({'airplane'}&modes)",
        "count=0\nfor activity in allactivities(plan):\n"
        "  if innercity_transport_type(activity_transports(activity))=='metro': count+=1\nresult=count==2",
    ],
    "travel_extent": [
        "distance=0\nfor activity in allactivities(plan):\n"
        "  distance+=innercity_transport_distance(activity_transports(activity),'walk')\nresult=distance<=10",
        "minutes=0\nfor activity in allactivities(plan):\n"
        "  minutes+=innercity_transport_time(activity_transports(activity))\nresult=minutes<=120",
    ],
    "schedule_order": [
        "result=False\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity)=='lunch' and activity_position(activity)=='Restaurant A':\n"
        "    if activity_start_time(activity)>='12:00' and activity_end_time(activity)<='13:00': result=True",
        "seen=False\nresult=False\nfor activity in allactivities(plan):\n"
        "  if activity_type(activity)=='attraction' and activity_position(activity)=='A': seen=True\n"
        "  if activity_type(activity)=='attraction' and activity_position(activity)=='B' and seen: result=True",
        "names=set()\nfor activity in dayactivities(plan,2):\n"
        "  if activity_type(activity)=='attraction': names.add(activity_position(activity))\nresult={'A'}<=names",
    ],
}


class ConstraintFamilyTests(unittest.TestCase):
    def test_repository_patterns_cover_all_families(self):
        self.assertEqual(set(PATTERNS), set(CONSTRAINT_FAMILIES))
        for family, codes in PATTERNS.items():
            for code in codes:
                with self.subTest(family=family, code=code):
                    result = classify(code)
                    self.assertEqual(result["classification_status"], "mapped", result)
                    self.assertEqual(result["family"], family)
                    self.assertIsNotNone(result["matched_pattern_id"])

    def test_threshold_names_and_variables_do_not_define_family(self):
        pairs = [
            (PATTERNS["monetary_budget"][0], {"6000": "831", "total": "amount"}),
            (PATTERNS["dining"][0], {"Restaurant A": "预算泳池公园 metro Hotel", "names": "places"}),
        ]
        for code, substitutions in pairs:
            changed = code
            for old, new in substitutions.items():
                changed = changed.replace(old, new)
            self.assertEqual(classify(code)["family"], classify(changed)["family"])

    def test_unguarded_entity_identity_is_unmapped_even_with_nl_hint(self):
        result = classify(
            "result=False\nfor activity in allactivities(plan):\n"
            "  if activity_position(activity)=='南门涮肉(天坛店)': result=True",
            hard_logic_nl="Eat at this restaurant; dining cuisine hotel budget",
        )
        self.assertEqual(result["classification_status"], "unmapped")
        self.assertIsNone(result["family"])

    def test_cross_family_compounds_and_or_program(self):
        programs = [
            "result=(day_count(plan)==3) and (people_count(plan)==2)",
            "result_list=[]\n" + PATTERNS["trip_specification"][0]
            + "\nresult_list.append(result)\n" + PATTERNS["monetary_budget"][0]
            + "\nresult_list.append(result)\nresult=False\nfor r in result_list:\n  result=result or r",
            "result=True\nfor activity in allactivities(plan):\n"
            "  if room_count(activity)!=1: result=False\n"
            "  if restaurant_type(activity,target_city(plan))!='江浙菜': result=False",
        ]
        self.assertEqual(classify(programs[0])["family"], "trip_specification")
        for code in programs[1:]:
            result = classify(code)
            self.assertEqual(result["classification_status"], "compound", result)
            self.assertIsNone(result["family"])

    def test_direct_cross_family_or_is_not_hidden_by_a_measure(self):
        code = ("for activity in allactivities(plan):\n"
                "  result=(day_count(plan)==3) or (activity_type(activity)=='attraction')")
        result = classify(code)
        self.assertEqual(result["classification_status"], "compound", result)
        self.assertEqual(result["features"]["candidate_families"], ["attraction", "trip_specification"])

    def test_nonbudget_cost_equality_cannot_borrow_an_unrelated_bound(self):
        code = ("for activity in allactivities(plan):\n"
                "  result=activity_cost(activity)==10\nunused=day_count(plan)<=3")
        result = classify(code)
        self.assertEqual(result["classification_status"], "unmapped", result)

    def test_additional_generator_scope_and_sequence_templates(self):
        patterns = [
            ("monetary_budget", "daily=0\nfor activity in dayactivities(plan,2):\n"
             "  daily+=activity_cost(activity)\n  daily+=innercity_transport_cost(activity_transports(activity))\nresult=daily<=999"),
            ("accommodation", "names=set()\nfor activity in allactivities(plan):\n"
             "  if activity_type(activity)=='accommodation': names.add(activity_position(activity))\n"
             "count=0\nfor name in names:\n  count+=1\nresult=count==1"),
            ("attraction", "names=set()\nfor activity in allactivities(plan):\n"
             "  if activity_type(activity)=='attraction': names.add(activity_position(activity))\nresult=not({'A'}&names)"),
            ("schedule_order", "minutes=0\nfor activity in allactivities(plan):\n"
             "  if activity_type(activity)=='attraction': minutes+=activity_time(activity)\nresult=minutes>=60"),
            ("schedule_order", "seen=False\nresult=False\nfor activity in allactivities(plan):\n"
             "  if activity_type(activity)=='attraction' and activity_position(activity)=='A': seen=True\n"
             "  if activity_type(activity)=='lunch' and activity_position(activity)=='B' and seen: result=True"),
        ]
        for family, code in patterns:
            with self.subTest(family=family, code=code):
                self.assertEqual(classify(code)["family"], family)

    def test_mixed_domain_selector_is_ambiguous(self):
        code = "names=set()\nfor activity in allactivities(plan):\n  if activity_type(activity) in ['attraction','lunch']: names.add(activity_position(activity))\nresult={'A'}<=names"
        result = classify(code)
        self.assertEqual(result["classification_status"], "ambiguous")
        self.assertIsNone(result["family"])

    def test_invalid_or_unsupported_dsl_is_unmapped(self):
        for code in ("result=(", "", "result=True", "result=unknown(plan)",
                     "import os\nresult=True", "result=missing<=3", None,
                     "result=day_count(plan)+1"):
            with self.subTest(code=code):
                result = classify(code)
                self.assertEqual(result["classification_status"], "unmapped")
                self.assertIsNone(result["matched_pattern_id"])

    def test_deterministic_preservation_and_json_output(self):
        descriptor = {"constraint_index": 4, "hard_logic_py": PATTERNS["dining"][1],
                      "hard_logic_nl": "必须包含江浙菜。"}
        snapshot = deepcopy(descriptor)
        first = classify_constraint(descriptor)
        self.assertEqual(first, classify_constraint(descriptor))
        self.assertEqual(first, json.loads(json.dumps(first)))
        self.assertEqual(descriptor, snapshot)
        for key, value in descriptor.items():
            self.assertEqual(first[key], value)
        self.assertEqual(first["normalizer_version"], NORMALIZER_VERSION)
        self.assertIn("restaurant_type", first["features"]["concept_functions"])
        self.assertIn("LtE", first["features"]["operators"])
        self.assertNotIn("hard_logic_nl", classify("result=day_count(plan)==3"))

    def test_indices_preserved_not_renumbered(self):
        descriptors = [{"constraint_index": i, "hard_logic_py": "result=day_count(plan)==3"}
                       for i in (5, 1, 3)]
        self.assertEqual([r["constraint_index"] for r in classify_constraints(descriptors)], [5, 1, 3])
        for index in (0, -1, True, "1", None):
            with self.subTest(index=index), self.assertRaises(ValueError):
                classify_constraint({"constraint_index": index, "hard_logic_py": "result=True"})

    def test_unused_cost_does_not_make_attraction_count_a_budget(self):
        code = "irrelevant=0\n" + PATTERNS["attraction"][0]
        code = code.replace("result=count==3", "irrelevant=activity_cost(activity)\nresult=count==3")
        self.assertEqual(classify(code)["family"], "attraction")


if __name__ == "__main__":
    unittest.main()
