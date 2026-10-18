import json
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from chinatravel.evaluation.edit_footprint import compare_edit_footprint, extract_itinerary_slots
from chinatravel.evaluation.repair_attempt import RepairAttemptRecord
from chinatravel.evaluation.repair_metrics import summarize_repair_history
from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
from chinatravel.agent.nesy_verifier.repair_strategies.base import RepairResult


def activity(name="A", kind="attraction"):
    return dict(type=kind, position=name, start_time="09:00", end_time="10:00",
                cost=10, transports={"from": "hotel", "to": name, "mode": "walk"})


def plan(*activities):
    return [{"day": 1, "activities": list(activities)}]


class FootprintTests(unittest.TestCase):
    def count(self, before, after, changed, total):
        result = compare_edit_footprint(before, after)
        self.assertEqual(result, dict(changed_slot_count=changed, total_comparable_slots=total,
                         changed_slot_rate=changed / total if total else None))

    def test_repository_saved_plan_schemas_are_comparable(self):
        paths = list((Path(__file__).resolve().parents[1] / "chinatravel/agent/nesy_agent").glob("plan_for_check*/*.json"))
        self.assertEqual(len(paths), 12)
        for path in paths:
            with self.subTest(path=path):
                saved = json.loads(path.read_text())
                result = compare_edit_footprint(saved, saved)
                self.assertEqual(result["changed_slot_count"], 0)
                self.assertEqual(result["total_comparable_slots"], sum(len(day["activities"]) for day in saved["itinerary"]))

    def test_identical_changed_inserted_removed_multiple(self):
        original = plan(activity(), activity("B", "lunch"))
        self.count(original, deepcopy(original), 0, 2)
        changed = deepcopy(original)
        changed[0]["activities"][0]["cost"] += 1
        self.count(original, changed, 1, 2)
        inserted = deepcopy(original)
        inserted[0]["activities"].append(activity("C"))
        self.count(original, inserted, 1, 3)
        self.count(inserted, original, 1, 3)
        changed[0]["activities"][1]["start_time"] = "11:00"
        self.count(original, changed, 2, 2)

    def test_positional_insert_and_reorder(self):
        original = plan(activity("A"), activity("B"))
        self.count(original, plan(activity("new"), activity("A"), activity("B")), 3, 3)
        self.count(original, plan(activity("B"), activity("A")), 2, 2)

    def test_empty_malformed_and_unavailable(self):
        self.count([], [], 0, 0)
        self.count(plan(), [], 0, 0)
        for malformed in (None, "text", {}, [None], [{"day": 1}], plan({}), plan(activity(), None)):
            with self.subTest(malformed=malformed):
                self.assertTrue(all(value is None for value in compare_edit_footprint([], malformed).values()))
        duplicate_day = plan(activity()) * 2
        self.assertIsNone(compare_edit_footprint([], duplicate_day)["changed_slot_count"])

    def test_canonical_content_formatting_metadata_and_transport(self):
        original = plan(activity())
        candidate = deepcopy(original)
        candidate[0]["debug"] = "trace"
        candidate[0]["activities"][0]["debug"] = "trace"
        candidate[0]["activities"][0]["position"] = " A "
        self.count(original, {"itinerary": candidate, "metadata": "ignored"}, 0, 1)
        candidate[0]["activities"][0]["transports"]["mode"] = "taxi"
        self.count(original, candidate, 1, 1)
        self.assertEqual(list(extract_itinerary_slots(original)), [(1, 0)])

    def test_rejected_candidate_roundtrip_and_summary(self):
        before, candidate = plan(activity()), plan(activity("replacement"))
        strategy = SimpleNamespace(repair=lambda **kw: RepairResult(candidate, {"strategy": "R0"}),
                                   accept=lambda *args: False)
        verification = {"passed": False, "personal_constraints": [False]}
        problem = dict(uid="q", people_number=1, start_city="A", target_city="B", hard_logic_py=["result=True"])
        with patch.object(loop, "verify_plan", return_value=verification):
            outcome = loop.run_repair_loop(problem, before, strategy, {}, SimpleNamespace(), None,
                                           max_steps=1, initial_verification=verification)
        record = RepairAttemptRecord.from_dict(outcome["history"][1]["repair_attempt"])
        self.assertEqual(record.changed_slot_count, 1)
        self.assertEqual(record.accepted_plan_after, before)
        summary = summarize_repair_history(outcome["history"])
        self.assertEqual(summary["mean_changed_slot_count"], 1)
        self.assertEqual(summary["mean_changed_slot_rate"], 1)
        self.assertEqual(summary["footprint_measured_attempts"], 1)
        record.changed_slot_rate = 0
        with self.assertRaises(ValueError):
            record.to_dict()
