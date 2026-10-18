"""Offline tests: no sandbox imports, network, or model requests."""

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
from chinatravel.agent.nesy_verifier.repair_strategies.base import (
    BaseRepairStrategy, RepairResult,
)
from chinatravel.evaluation.repair_attempt import RepairAttemptRecord


class StubStrategy(BaseRepairStrategy):
    def __init__(self, accepted=True, metadata=None):
        self.accepted = accepted
        self.metadata = metadata or {}

    def repair(self, problem, raw_plan, verification_results, context, llm):
        if hasattr(llm, "input_token_count"):
            llm.input_token_count += 7
            llm.output_token_count += 3
        return RepairResult([{"candidate": True}], self.metadata)

    def accept(self, current_verification, candidate_verification):
        return self.accepted


class RepairAttemptTests(unittest.TestCase):
    def run_loop(self, before, after, strategy=None, llm=None, max_steps=1, query_fields=None):
        initial = [{"initial": True}]
        verifications = [{"passed": False, "personal_constraints": deepcopy(before)}]
        verifications += [
            {"passed": all(v is True for v in after),
             "personal_constraints": deepcopy(after), "evidence": "candidate"}
            for _ in range(max_steps)
        ]
        with patch.object(loop, "verify_plan", side_effect=verifications) as verify:
            result = loop.run_repair_loop(
                {"people_number": 1, "start_city": "A", "target_city": "B",
                 **(query_fields or {})},
                initial, strategy or StubStrategy(), {}, llm or object(),
                translate_fn=None, max_steps=max_steps,
            )
        self.assertEqual(initial, [{"initial": True}])
        self.assertGreaterEqual(verify.call_count, 2)
        return result

    def test_accepted_fix_and_targets_and_usage(self):
        result = self.run_loop(
            [False, True], [True, True],
            StubStrategy(metadata={"strategy": "R0", "target_constraint_indices": [1],
                                   "target_constraint_labels": ["budget"],
                                   "editable_scope": "plan"}),
            SimpleNamespace(input_token_count=10, output_token_count=4),
        )
        entry = result["history"][1]
        record = entry["repair_attempt"]
        self.assertEqual(record["fixed"], [1])
        self.assertEqual(record["still_passed"], [2])
        self.assertEqual(record["target_constraint_indices"], [1])
        self.assertEqual(record["target_constraint_labels"], ["budget"])
        self.assertEqual(record["repair_strategy"], "R0")
        self.assertEqual(record["accepted_plan_after"], result["raw_plan"])
        self.assertEqual(record["input_tokens_before"], 10)
        self.assertEqual(record["input_tokens_after"], 17)
        self.assertEqual(record["input_tokens_delta"], 7)
        self.assertEqual(record["output_tokens_delta"], 3)
        self.assertGreaterEqual(record["repair_time_seconds"], 0)
        self.assertEqual(entry["constraint_transitions"]["fixed"], [1])
        self.assertEqual(entry["metadata"], record["repair_metadata"])
        self.assertTrue(result["verification"]["passed"])
        self.assertEqual(set(result), {"raw_plan", "verification", "history"})

    def test_query_identity_and_ordered_source_descriptors_roundtrip(self):
        query = {
            "uid": "query-17",
            "hard_logic_py": ["result = cost(plan) < 100", "result = True"],
            "hard_logic_nl": ["Keep the cost below 100", "Second source description"],
        }
        record = self.run_loop([False, True], [True, True], query_fields=query)["history"][1]["repair_attempt"]
        self.assertEqual(record["query_uid"], "query-17")
        self.assertEqual(record["constraint_descriptors"], [
            {"constraint_index": 1, "hard_logic_py": query["hard_logic_py"][0],
             "hard_logic_nl": query["hard_logic_nl"][0]},
            {"constraint_index": 2, "hard_logic_py": query["hard_logic_py"][1],
             "hard_logic_nl": query["hard_logic_nl"][1]},
        ])
        self.assertEqual(RepairAttemptRecord.from_dict(json.loads(json.dumps(record))).to_dict(), record)
        query["hard_logic_py"][0] = "changed"
        self.assertEqual(record["constraint_descriptors"][0]["hard_logic_py"], "result = cost(plan) < 100")

    def test_missing_uid_and_optional_descriptions(self):
        for optional in ({}, {"hard_logic_nl": []}, {"hard_logic_nl": None},
                         {"hard_logic_nl": ["First only"]}):
            with self.subTest(optional=optional):
                record = self.run_loop(
                    [False, True], [True, True],
                    query_fields={"hard_logic_py": ["result = False", "result = True"], **optional},
                )["history"][1]["repair_attempt"]
                self.assertIsNone(record["query_uid"])
                expected = [
                    {"constraint_index": 1, "hard_logic_py": "result = False"},
                    {"constraint_index": 2, "hard_logic_py": "result = True"},
                ]
                if optional.get("hard_logic_nl"):
                    expected[0]["hard_logic_nl"] = "First only"
                self.assertEqual(record["constraint_descriptors"], expected)

    def test_old_serialized_records_load_with_independent_defaults(self):
        old = self.run_loop([False], [True])["history"][1]["repair_attempt"]
        old.pop("query_uid")
        old.pop("constraint_descriptors")
        record = RepairAttemptRecord.from_dict(old)
        other = RepairAttemptRecord.from_dict(old)
        self.assertIsNone(record.query_uid)
        self.assertEqual(record.constraint_descriptors, [])
        record.constraint_descriptors.append({"constraint_index": 1, "hard_logic_py": "result = True"})
        self.assertEqual(other.constraint_descriptors, [])

    def test_invalid_identity_fields_rejected(self):
        payload = self.run_loop([False], [True])["history"][1]["repair_attempt"]
        for update in (
            {"query_uid": 42}, {"constraint_descriptors": {}},
            {"constraint_descriptors": ["constraint"]},
            {"constraint_descriptors": [{"constraint_index": 0, "hard_logic_py": "result = True"}]},
            {"constraint_descriptors": [{"constraint_index": 1}]},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                RepairAttemptRecord.from_dict({**payload, **update})

    def test_accepted_regression(self):
        result = self.run_loop([False, True], [True, False])
        record = result["history"][1]["repair_attempt"]
        self.assertTrue(record["accepted"])
        self.assertEqual(record["fixed"], [1])
        self.assertEqual(record["newly_violated"], [2])
        self.assertEqual(record["accepted_plan_after"], record["candidate_plan"])

    def test_rejection_preserves_candidate_and_accepted_state_across_attempts(self):
        result = self.run_loop([False, True], [True, False], StubStrategy(False), max_steps=2)
        self.assertEqual(len(result["history"]), 3)
        for entry in result["history"][1:]:
            record = entry["repair_attempt"]
            self.assertFalse(record["accepted"])
            self.assertEqual(record["newly_violated"], [2])
            self.assertEqual(record["before_personal_constraints"], [False, True])
            self.assertEqual(record["after_personal_constraints"], [True, False])
            self.assertEqual(record["accepted_plan_after"], [{"initial": True}])
            self.assertEqual(record["candidate_plan"], [{"candidate": True}])
            self.assertEqual(entry["verification"]["evidence"], "candidate")
        self.assertEqual(result["raw_plan"], [{"initial": True}])
        self.assertEqual(result["verification"]["personal_constraints"], [False, True])

    def test_unknown_states(self):
        record = self.run_loop([None, True, False, None], [True, None, False, None])["history"][1]["repair_attempt"]
        self.assertEqual(record["unknown"], [1, 2, 4])
        self.assertEqual(record["still_failed"], [3])
        self.assertEqual(record["fixed"], [])
        self.assertEqual(record["newly_violated"], [])
        self.assertIsNone(record["before_personal_constraints"][0])

    def test_missing_metadata_and_counters(self):
        record = self.run_loop([False], [True])["history"][1]["repair_attempt"]
        self.assertEqual(record["target_constraint_indices"], [])
        self.assertEqual(record["target_constraint_labels"], [])
        self.assertEqual(record["repair_strategy"], "StubStrategy")
        for name in ("input_tokens_before", "input_tokens_after", "input_tokens_delta",
                     "output_tokens_before", "output_tokens_after", "output_tokens_delta", "exception"):
            self.assertIsNone(record[name])

    def test_json_roundtrip_and_detached_snapshots(self):
        result = self.run_loop([False], [True])
        payload = result["history"][1]["repair_attempt"]
        record = RepairAttemptRecord.from_dict(json.loads(json.dumps(payload)))
        self.assertEqual(record.to_dict(), payload)
        exported = record.to_dict()
        exported["fixed"].clear()
        self.assertEqual(record.fixed, [1])
        result["raw_plan"][0]["candidate"] = False
        self.assertEqual(payload["accepted_plan_after"], [{"candidate": True}])

    def test_invalid_records_rejected(self):
        payload = self.run_loop([False, True], [True, False])["history"][1]["repair_attempt"]
        invalid = [
            {"step": 0}, {"accepted": 1}, {"fixed": [0]}, {"fixed": [1, 1]},
            {"newly_violated": []}, {"unknown": [1]},
            {"after_personal_constraints": [True]},
            {"before_personal_constraints": [0, True]},
            {"target_constraint_indices": [3]}, {"target_constraint_labels": [1]},
            {"input_tokens_before": 2, "input_tokens_after": 3, "input_tokens_delta": 5},
            {"repair_time_seconds": -1}, {"candidate_plan": object()},
            {"unexpected": True},
        ]
        for update in invalid:
            with self.subTest(update=update), self.assertRaises((ValueError, TypeError)):
                RepairAttemptRecord.from_dict({**payload, **update})

    def test_before_snapshot_survives_strategy_mutation(self):
        class MutatingStrategy(StubStrategy):
            def repair(self, **kwargs):
                kwargs["verification_results"]["personal_constraints"][0] = True
                return super().repair(**kwargs)

        result = self.run_loop([False], [True], MutatingStrategy())
        record = result["history"][1]["repair_attempt"]
        self.assertEqual(record["before_personal_constraints"], [False])
        self.assertEqual(record["fixed"], [1])
        self.assertEqual(result["history"][0]["verification"]["personal_constraints"], [False])
        from chinatravel.evaluation.repair_metrics import summarize_repair_history

        self.assertEqual(summarize_repair_history(result["history"])["final_failed_count"], 0)

    def test_accept_cannot_mutate_shared_verification_or_query(self):
        class MutatingStrategy(StubStrategy):
            def repair(self, **kwargs):
                kwargs["problem"]["hard_logic_py"][0] = "result=True"
                return super().repair(**kwargs)

            def accept(self, current_verification, candidate_verification):
                current_verification["personal_constraints"][0] = True
                candidate_verification["personal_constraints"][0] = False
                candidate_verification["passed"] = False
                return True

        result = self.run_loop([False], [True], MutatingStrategy(),
                               query_fields={"hard_logic_py": ["result=False"]})
        self.assertEqual(result["history"][0]["verification"]["personal_constraints"], [False])
        self.assertEqual(result["verification"]["personal_constraints"], [True])
        self.assertTrue(result["verification"]["passed"])
        record = result["history"][1]["repair_attempt"]
        self.assertEqual(record["constraint_descriptors"][0]["hard_logic_py"], "result=False")
        self.assertEqual(record["after_personal_constraints"], [True])

    def test_initial_pass_produces_no_attempt_record(self):
        strategy = StubStrategy()
        with patch.object(loop, "verify_plan", return_value={"passed": True, "personal_constraints": [True]}), patch.object(strategy, "repair") as repair:
            result = loop.run_repair_loop(
                {"people_number": 1, "start_city": "A", "target_city": "B"},
                [], strategy, {}, object(), None,
            )
        repair.assert_not_called()
        self.assertEqual(len(result["history"]), 1)
        self.assertNotIn("repair_attempt", result["history"][0])


if __name__ == "__main__":
    unittest.main()
