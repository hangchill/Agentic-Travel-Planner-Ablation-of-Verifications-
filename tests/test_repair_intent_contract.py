"""Phase 4.1 intent, actual R0 feedback, scope aggregation and compatibility."""

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
from chinatravel.agent.nesy_verifier.repair_strategies.r0 import R0WholePlanRepair
from chinatravel.evaluation.repair_attempt import (
    DERIVED_FIELDS, INTENT_FIELDS, RepairAttemptRecord,
)
from chinatravel.evaluation.regression_matrix import build_regression_matrix
from test_regression_matrix import BUDGET, TRIP, cell, contribution, record


NEW_FIELDS = (
    "target_provenance", "editable_scope", "scope_level", "concurrent_failed_constraint_indices",
    "concurrent_commonsense_failure_count", "feedback_personal_constraint_indices",
    "feedback_commonsense_failure_count", "protected_constraint_indices", "escalation_reason", "decision_reason",
)


class IntentContractTests(unittest.TestCase):
    def test_roundtrip_all_fields_and_no_duplicate_debug_intent(self):
        value = record(target_provenance="explicit", editable_scope="slot", scope_level=1,
                       concurrent_commonsense_failure_count=2,
                       feedback_personal_constraint_indices=[1], feedback_commonsense_failure_count=1,
                       protected_constraint_indices=[2], escalation_reason="initial_scope",
                       decision_reason="accepted_proposal")
        payload = value.to_dict()
        restored = RepairAttemptRecord.from_dict(json.loads(json.dumps(payload)))
        self.assertEqual(restored.to_dict(), payload)
        self.assertEqual(restored.concurrent_failed_constraint_indices, [1])
        self.assertTrue(all(name in payload for name in NEW_FIELDS))
        self.assertFalse(set(INTENT_FIELDS) & payload["repair_metadata"].keys())

    def test_old_records_default_to_unavailable_not_fabricated_feedback(self):
        old = record().to_dict()
        for name in NEW_FIELDS:
            old.pop(name)
        restored = RepairAttemptRecord.from_dict(old)
        self.assertIsNone(restored.target_provenance)
        self.assertIsNone(restored.editable_scope)
        self.assertIsNone(restored.concurrent_commonsense_failure_count)
        self.assertIsNone(restored.feedback_personal_constraint_indices)
        self.assertEqual(restored.protected_constraint_indices, [])
        self.assertEqual(restored.concurrent_failed_constraint_indices, [1])

    def test_legacy_metadata_migrates_once_and_direct_fields_win(self):
        old = record().to_dict()
        for name in NEW_FIELDS:
            old.pop(name)
        old["repair_metadata"] = {"scope": "whole_plan", "target_provenance": "legacy",
                                  "feedback_personal_constraint_indices": [1], "prompt": "debug"}
        restored = RepairAttemptRecord.from_dict(old)
        self.assertEqual(restored.editable_scope, "plan")
        self.assertEqual(restored.target_provenance, "legacy")
        self.assertEqual(restored.repair_metadata, {"prompt": "debug"})
        self.assertNotIn("scope", restored.to_dict()["repair_metadata"])
        old["editable_scope"] = "day"
        old["target_provenance"] = None
        self.assertEqual(RepairAttemptRecord.from_dict(old).editable_scope, "day")
        self.assertIsNone(RepairAttemptRecord.from_dict(old).target_provenance)
        old.pop("editable_scope")
        old["repair_metadata"]["scope"] = "plan"
        self.assertEqual(RepairAttemptRecord.from_dict(old).editable_scope, "plan")

    def test_explicit_empty_feedback_is_distinct_from_unavailable(self):
        self.assertIsNone(record().feedback_personal_constraint_indices)
        self.assertEqual(record(feedback_personal_constraint_indices=[]).feedback_personal_constraint_indices, [])

    def test_legacy_nested_targets_and_structured_scope_are_read_safely(self):
        old = record().to_dict()
        old.pop("target_constraint_indices")
        old.pop("target_constraint_labels")
        old.pop("editable_scope")
        old["repair_metadata"] = {"target_constraint_indices": [1], "target_constraint_labels": ["days"],
                                  "editable_scope": {"day": 1}, "raw_response": "debug"}
        migrated = RepairAttemptRecord.from_dict(old)
        self.assertEqual(migrated.target_constraint_indices, [1])
        self.assertEqual(migrated.target_constraint_labels, ["days"])
        self.assertIsNone(migrated.editable_scope)
        self.assertEqual(migrated.repair_metadata["legacy_scope_details"], {"day": 1})
        self.assertEqual(migrated.repair_metadata["raw_response"], "debug")

    def test_concurrent_false_only_and_validation(self):
        value = record([False, True, None, False], [True, False, None, False], [TRIP, BUDGET, TRIP, TRIP])
        self.assertEqual(value.concurrent_failed_constraint_indices, [1, 4])
        invalid = [
            {"editable_scope": "unknown"}, {"editable_scope": "day", "scope_level": 3},
            {"scope_level": True}, {"protected_constraint_indices": [1, 1]},
            {"feedback_personal_constraint_indices": [0]}, {"concurrent_commonsense_failure_count": -1},
            {"feedback_commonsense_failure_count": True}, {"target_provenance": {}},
            {"concurrent_failed_constraint_indices": []},
        ]
        payload = record().to_dict()
        for update in invalid:
            with self.subTest(update=update), self.assertRaises(ValueError):
                RepairAttemptRecord.from_dict({**payload, **update})


class R0IntentTests(unittest.TestCase):
    def run_r0(self, before):
        codes = [TRIP, BUDGET, "result=people_count(plan)==1", BUDGET][:len(before)]
        personal = [f"Personal constraint {i} failed: {codes[i-1]}" for i, state in enumerate(before, 1) if state is False]
        commonsense = ["commonsense A", "commonsense B"]
        verification = {"personal_constraints": before, "commonsense_errors": commonsense,
                        "error_info": commonsense + personal, "passed": False}
        problem = {"uid": "r0-case", "people_number": 1, "start_city": "A", "target_city": "B",
                   "nature_language": "Synthetic request", "hard_logic_py": codes}
        context = {key: "data" for key in (
            "go_train_info", "go_flight_info", "back_train_info", "back_flight_info",
            "attraction_info", "restaurant_info", "accommodation_info", "innercity_transport_info")}
        after = [True if value is False else value for value in before]
        candidate = {"personal_constraints": after, "passed": all(value is True for value in after),
                     "commonsense_errors": [], "error_info": []}
        llm = Mock(return_value='"activities": []}]')
        with patch.object(loop, "verify_plan", side_effect=[verification, candidate]):
            output = loop.run_repair_loop(problem, [], R0WholePlanRepair(), context, llm, None, max_steps=1)
        return output["history"][1], llm.call_args.args[0][0]["content"], personal, codes

    def test_single_failed_r0_target_and_exact_feedback(self):
        entry, prompt, failures, codes = self.run_r0([False, True, None])
        value = RepairAttemptRecord.from_dict(entry["repair_attempt"])
        self.assertEqual(value.target_constraint_indices, [1])
        self.assertEqual(value.target_provenance, "r0_failed_feedback")
        self.assertEqual(value.editable_scope, "plan")
        self.assertEqual(value.feedback_personal_constraint_indices, [1])
        self.assertEqual(value.concurrent_failed_constraint_indices, [1])
        self.assertEqual(value.concurrent_commonsense_failure_count, 2)
        self.assertEqual(value.feedback_commonsense_failure_count, 2)
        self.assertTrue(all(failure in prompt for failure in failures))
        self.assertIn("commonsense A", prompt)
        self.assertNotIn("Personal constraint 3 failed", prompt)
        for metadata in (value.repair_metadata, entry["metadata"]):
            self.assertNotIn("scope", metadata)
            self.assertFalse(set(INTENT_FIELDS + DERIVED_FIELDS) & metadata.keys())
        analysis = build_regression_matrix([value])
        self.assertEqual(cell(analysis)["eligible_count"], 1)
        row = contribution(analysis)
        self.assertEqual(row["editable_scope"], "plan")
        self.assertEqual(row["target_count"], 1)
        self.assertEqual(row["concurrent_failed_count"], 1)
        self.assertEqual(row["feedback_personal_constraint_count"], 1)
        self.assertTrue(row["has_concurrent_commonsense_failure"])
        self.assertTrue(row["is_isolated_personal_target"])

    def test_multi_failed_r0_preserves_every_target_and_primary_excludes(self):
        entry, prompt, failures, _ = self.run_r0([False, True, None, False])
        value = RepairAttemptRecord.from_dict(entry["repair_attempt"])
        self.assertEqual(value.target_constraint_indices, [1, 4])
        self.assertEqual(value.feedback_personal_constraint_indices, [1, 4])
        self.assertTrue(all(failure in prompt for failure in failures))
        analysis = build_regression_matrix([value])
        self.assertEqual(analysis["coverage"]["multi_target_attempts"], 1)
        self.assertFalse(any(row["eligible"] for row in analysis["contributions"]))

    def test_no_false_r0_does_not_target_unknown_or_pass(self):
        entry, _, _, _ = self.run_r0([None, True])
        self.assertEqual(entry["repair_attempt"]["target_constraint_indices"], [])
        self.assertEqual(entry["repair_attempt"]["feedback_personal_constraint_indices"], [])

    def test_shared_loop_uses_before_commonsense_not_candidate_or_strategy_claim(self):
        from chinatravel.agent.nesy_verifier.repair_strategies.base import RepairResult

        strategy = Mock()
        strategy.repair.return_value = RepairResult([], {
            "concurrent_failed_constraint_indices": [2], "concurrent_commonsense_failure_count": 99,
            "step": 99, "accepted": True, "before_personal_constraints": [True],
            "input_tokens_delta": 100, "target_constraint_indices": [1], "prompt": "debug"})
        strategy.accept.return_value = False
        before = {"personal_constraints": [False, None], "commonsense_errors": ["A", "B"], "passed": False}
        after = {"personal_constraints": [True, None], "commonsense_errors": [], "passed": False}
        with patch.object(loop, "verify_plan", side_effect=[before, after]):
            result = loop.run_repair_loop({"people_number": 1, "start_city": "A", "target_city": "B"},
                                          [], strategy, {}, Mock(), None, max_steps=1)
        value = result["history"][1]["repair_attempt"]
        self.assertEqual(value["concurrent_failed_constraint_indices"], [1])
        self.assertEqual(value["concurrent_commonsense_failure_count"], 2)
        self.assertFalse(value["accepted"])
        self.assertEqual(value["step"], 1)
        self.assertEqual(value["before_personal_constraints"], [False, None])
        self.assertIsNone(value["input_tokens_delta"])
        self.assertEqual(value["target_constraint_indices"], [1])
        self.assertEqual(value["repair_metadata"], {"prompt": "debug"})


class ScopeMatrixTests(unittest.TestCase):
    def test_mutating_generator_cannot_hide_conflicting_duplicates(self):
        value = record()

        def records():
            yield value
            value.accepted = False
            yield value

        with self.assertRaisesRegex(ValueError, "Conflicting duplicate"):
            build_regression_matrix(records())

    def test_primary_unchanged_rejection_observed_and_scope_population_separated(self):
        values = [record(step=index, editable_scope=scope, accepted=accepted)
                  for index, (scope, accepted) in enumerate(
                      [("slot", True), ("day", False), ("plan", True), (None, False)], 1)]
        result = build_regression_matrix(values)
        self.assertEqual(cell(result)["regression_rate"], 1)
        self.assertEqual(cell(result)["eligible_count"], 4)
        self.assertEqual(cell(result, "accepted_trajectory")["regression_rate"], 0.5)
        self.assertEqual(cell(result, "accepted_trajectory")["eligible_count"], 4)
        scopes = [row for row in result["aggregate_by_scope"]
                  if row["source_family"] == "trip_specification" and row["destination_family"] == "monetary_budget"]
        self.assertEqual({row["editable_scope"] for row in scopes}, {None, "slot", "day", "plan"})
        self.assertTrue(all(row["eligible_count"] == 1 for row in scopes))
        baseline = deepcopy(values)
        for value in baseline:
            value.editable_scope = None
        self.assertEqual(result["aggregate"], build_regression_matrix(baseline)["aggregate"])

    def test_coverage_breakdowns_and_duplicate_protection(self):
        values = [
            record(step=1, editable_scope="slot", concurrent_commonsense_failure_count=2),
            record([False, True, False], [True, False, False], [TRIP, BUDGET, TRIP],
                   step=2, editable_scope="day"),
            record(step=3, target_provenance=None),
        ]
        result = build_regression_matrix(values + [values[0]])
        coverage = result["coverage"]
        self.assertEqual(coverage["total_repair_attempts"], 3)
        self.assertEqual(coverage["duplicate_records_ignored"], 1)
        self.assertEqual(coverage["isolated_single_target_attempts"], 2)
        self.assertEqual(coverage["single_target_with_other_personal_failures_attempts"], 1)
        self.assertEqual(coverage["concurrent_commonsense_failure_attempts"], 1)
        self.assertEqual(coverage["missing_editable_scope_attempts"], 1)
        self.assertEqual(coverage["missing_target_provenance_attempts"], 1)
        self.assertEqual(len(coverage["by_strategy"]), 1)
        self.assertEqual(len(coverage["by_strategy_scope"]), 3)
        self.assertEqual(sum(group["total_repair_attempts"] for group in coverage["by_strategy_scope"]), 3)


if __name__ == "__main__":
    unittest.main()
