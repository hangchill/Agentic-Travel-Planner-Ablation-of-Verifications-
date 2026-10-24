
import unittest
from copy import deepcopy
from chinatravel.environment.tools.transportation.apis import Transportation
from chinatravel.agent.nesy_verifier.repair_strategies.r1 import (
    repair_commonsense_transport_cost,)
from chinatravel.agent.nesy_verifier.verifier import (
    commonsense_constraint_nl as commonsense)

class TestR1TransportCostIntegration(unittest.TestCase):
    def test_real_sandbox_taxi_cost_repair(self):
        commonsense._set_lang("en")
        self.addCleanup(commonsense._set_lang, "zh")
        problem = {"target_city": "Beijing",
                   "people_number": 2,
                   "lang": "en",}
        transport_tool = Transportation(lang="en")
        route = transport_tool.goto(
            city="Beijing",
            start="Beijing Daxing International Airport",
            end="The Palace Museum",
            start_time="08:33",
            transport_type="taxi",
            verbose=False,)
        self.assertTrue(route)
        correct_cost = route[0]["cost"]
        original_transport = {
            "from": "Beijing Daxing International Airport",
            "to": "The Palace Museum",
            "mode": "taxi",
            "start_time": "08:33",
            "end_time": route[0]["end_time"],
            "cost": correct_cost + 50,}
        itinerary = [{
            "day": 1,
            "activities": [{
                "type": "attraction",
                "position": "The Palace Museum",
                "start_time": "10:30",
                "end_time": "12:00",
                "transports": deepcopy(original_transport),}],}]
        plan = {"people_number": 2,
                "start_city": "Beijing",
                "target_city": "Beijing",
                "itinerary": itinerary,}

        # verify deliberately incorrect cost
        errors_before = commonsense.collect_transport_error(
            problem, plan, verbose=False)
        cost_errors_before = [
            error for error in errors_before
            if "Incorrect cost infomation" in error]
        self.assertEqual(len(cost_errors_before), 1)

        result = repair_commonsense_transport_cost(
            problem, itinerary,
            {"commonsense_errors": errors_before},)
        self.assertIsNotNone(result)
        repaired = result.repaired_plan
        repaired_plan = deepcopy(plan)
        repaired_plan["itinerary"] = repaired
        errors_after = commonsense.collect_transport_error(
            problem, repaired_plan, verbose=False)
        cost_errors_after = [
            error for error in errors_after
            if "Incorrect cost infomation" in error]
        self.assertEqual(cost_errors_after, [])
        repaired_transport = repaired[0]["activities"][0]["transports"]
        self.assertAlmostEqual(repaired_transport["cost"], correct_cost,)
        expected_transport = deepcopy(original_transport)
        expected_transport["cost"] = correct_cost
        self.assertEqual(repaired_transport, expected_transport)
        self.assertEqual(itinerary[0]["activities"][0]["transports"], original_transport,)
        self.assertEqual(result.metadata["repair_source"], "transport_cost_lookup",)

if __name__ == "__main__":
    unittest.main()
