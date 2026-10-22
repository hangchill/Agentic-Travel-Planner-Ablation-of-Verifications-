#!/usr/bin/env python3
"""Offline unit tests for the R3 adaptive-scope repair strategy.

These exercise R3 in isolation (no sandbox DB, no API): the ladder, slot
localization, the slot-freeze merge, contract-conforming metadata, and the
end-to-end repair-attempt record produced by the shared loop - all with a mock
LLM / verifier. R3 imports only json_utils / prompts / base / repair_attempt, so
no sandbox data is needed; the import is still guarded so a partial env skips.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

try:
    from chinatravel.agent.nesy_verifier.repair_strategies.r3 import (
        PROTECT_HEADER,
        R3AdaptiveScopeRepair,
    )
    from chinatravel.agent.nesy_verifier.repair_strategies import create_repair_strategy
    from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
    from chinatravel.evaluation.repair_attempt import (
        INTENT_FIELDS, DERIVED_FIELDS, RepairAttemptRecord,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - partial env only
    _IMPORT_ERROR = exc


_SKIP = f"could not import r3 (partial env?): {_IMPORT_ERROR}"


def _ctx():
    keys = [
        "go_train_info",
        "go_flight_info",
        "back_train_info",
        "back_flight_info",
        "attraction_info",
        "restaurant_info",
        "accommodation_info",
        "innercity_transport_info",
    ]
    return {k: "" for k in keys}


class _MockLLM:
    """Returns a fixed string; records that it was called."""

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def __call__(self, messages, one_line=True, **kwargs):
        self.calls += 1
        return self.response


def _continuation(itinerary):
    """Build the string the planner is expected to return: the plan JSON with the
    leading '[{"day": 1,' stripped (R3 re-primes that prefix, mirroring R0)."""
    text = json.dumps(itinerary, ensure_ascii=False)
    prefix = '[{"day": 1,'
    assert text.startswith(prefix), text[:20]
    return text[len(prefix):]


@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP)
class RegistrationTests(unittest.TestCase):
    def test_r3_is_registered_as_zero_arg_factory(self):
        strategy = create_repair_strategy("R3")
        self.assertIsInstance(strategy, R3AdaptiveScopeRepair)


@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP)
class ScheduleTests(unittest.TestCase):
    def test_fixed_schedule_two_rounds_per_rung(self):
        # Default schedule: iters 1-2 slot, 3-4 day, 5+ plan (capped at the top).
        s = R3AdaptiveScopeRepair()
        rungs = []
        for _ in range(7):
            s._advance_scope()
            rungs.append(s._scope)
        self.assertEqual(
            rungs,
            ["slot", "slot", "day", "day", "plan", "plan", "plan"],
        )

    def test_advance_scope_returns_previous_rung_index(self):
        s = R3AdaptiveScopeRepair(rounds_per_rung=1)
        self.assertEqual(s._advance_scope(), 0)   # iter1: slot, previous slot(0)
        self.assertEqual(s._scope, "slot")
        self.assertEqual(s._advance_scope(), 0)   # iter2: widened slot(0) -> day(1)
        self.assertEqual(s._scope_idx, 1)
        self.assertEqual(s._advance_scope(), 1)   # iter3: widened day(1) -> plan(2)
        self.assertEqual(s._scope_idx, 2)

    def test_rounds_per_rung_is_configurable(self):
        s = R3AdaptiveScopeRepair(rounds_per_rung=1)
        rungs = []
        for _ in range(4):
            s._advance_scope()
            rungs.append(s._scope)
        self.assertEqual(rungs, ["slot", "day", "plan", "plan"])


@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP)
class LocalizationAndRegionTests(unittest.TestCase):
    def _plan(self):
        return [
            {
                "day": 1,
                "activities": [
                    {"type": "attraction", "position": "A", "cost": 10},
                    {"type": "lunch", "position": "B", "cost": 20},
                    {"type": "accommodation", "position": "Hotel", "cost": 400},
                ],
            }
        ]

    def test_personal_quoted_poi_localizes_to_that_slot(self):
        s = R3AdaptiveScopeRepair()
        plan = self._plan()
        targets = [{"kind": "personal", "ref": "personal:0", "index": 0,
                    "dsl": "result = (activity_position(a) == 'B')"}]
        localized = s._localize_targets(targets, plan)
        self.assertEqual(localized, [{(0, 1)}])

    def test_global_constraint_is_global(self):
        s = R3AdaptiveScopeRepair()
        plan = self._plan()
        targets = [{"kind": "personal", "ref": "personal:0", "index": 0,
                    "dsl": "total=0\nfor a in allactivities(plan): total+=activity_cost(a)\nresult=(total<=100)"}]
        localized = s._localize_targets(targets, plan)
        self.assertEqual(localized, ["global"])

    def test_anchors_frozen_until_plan_scope(self):
        s = R3AdaptiveScopeRepair()
        plan = self._plan()
        # A failing constraint on the whole day (day-only message).
        localized = [{(0, 0), (0, 1), (0, 2)}]
        day_editable, _ = s._editable_region("day", plan, localized)
        # accommodation (0,2) is a trip-level anchor -> frozen at day scope.
        self.assertIn((0, 0), day_editable)
        self.assertIn((0, 1), day_editable)
        self.assertNotIn((0, 2), day_editable)
        # At plan scope everything (incl. the anchor) is editable.
        plan_editable, _ = s._editable_region("plan", plan, localized)
        self.assertIn((0, 2), plan_editable)

    def test_global_heuristic_picks_highest_cost_nonanchor(self):
        s = R3AdaptiveScopeRepair()
        plan = self._plan()
        editable, global_present = s._editable_region("slot", plan, ["global"])
        self.assertTrue(global_present)
        # highest-cost non-anchor is the lunch (20) over attraction (10); hotel excluded.
        self.assertIn((0, 1), editable)
        self.assertNotIn((0, 2), editable)


@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP)
class MergeAndMetadataTests(unittest.TestCase):
    def _plan(self):
        return [
            {
                "day": 1,
                "activities": [
                    {"type": "attraction", "position": "A", "cost": 10,
                     "start_time": "09:00", "end_time": "10:00"},
                    {"type": "lunch", "position": "B", "cost": 20,
                     "start_time": "12:00", "end_time": "13:00"},
                ],
            }
        ]

    def test_merge_locks_frozen_slots(self):
        s = R3AdaptiveScopeRepair()
        current = self._plan()
        proposal = [
            {
                "day": 1,
                "activities": [
                    {"type": "attraction", "position": "A_CHANGED", "cost": 999},
                    {"type": "lunch", "position": "B_CHANGED", "cost": 30},
                ],
            }
        ]
        merged, changed = s._merge(current, proposal, editable={(0, 1)})
        # frozen attraction untouched; only the editable lunch changed.
        self.assertEqual(merged[0]["activities"][0]["position"], "A")
        self.assertEqual(merged[0]["activities"][1]["position"], "B_CHANGED")
        self.assertEqual(changed, 1)

    def test_repair_emits_contract_intent_and_freezes(self):
        s = R3AdaptiveScopeRepair()
        current = self._plan()
        new_attr = {"type": "attraction", "position": "A2", "cost": 5,
                    "start_time": "09:00", "end_time": "10:00"}
        new_lunch = {"type": "lunch", "position": "B2", "cost": 30,
                     "start_time": "12:00", "end_time": "13:00"}
        llm = _MockLLM(_continuation([{"day": 1, "activities": [new_attr, new_lunch]}]))

        problem = {
            "nature_language": "q",
            "hard_logic_py": ["result = (activity_position(a) == 'B')"],
        }
        verification = {
            "personal_constraints": [False],
            "commonsense_errors": [],
            "schema_errors": [],
            "error_info": ["Personal constraint 1 failed"],
        }

        result = s.repair(problem, current, verification, _ctx(), llm)
        self.assertEqual(llm.calls, 1)

        meta = result.metadata
        self.assertEqual(meta["strategy"], "R3")
        # Contract: scope is reported as string editable_scope + agreeing int level.
        self.assertEqual(meta["editable_scope"], "slot")
        self.assertEqual(meta["scope_level"], 1)
        # Targets are 1-based hard_logic_py indices of current False personals.
        self.assertEqual(meta["target_constraint_indices"], [1])
        self.assertEqual(meta["target_provenance"], "r3_adaptive_scope")
        # Feedback is measured from the error_info lines actually supplied.
        self.assertEqual(meta["feedback_personal_constraint_indices"], [1])
        self.assertEqual(meta["feedback_commonsense_failure_count"], 0)
        self.assertFalse(meta["parse_failed"])
        self.assertNotIn("escalation_reason", meta)   # no widening on step 1
        # only the lunch slot was editable -> attraction frozen, lunch replaced.
        self.assertEqual(result.repaired_plan[0]["activities"][0]["position"], "A")
        self.assertEqual(result.repaired_plan[0]["activities"][1]["position"], "B2")
        self.assertEqual(meta["changed_slots"], 1)
        self.assertEqual(
            [(d["day"], d["activity_index"]) for d in meta["editable_slots"]],
            [(0, 1)],
        )
        # debug components for the later matrix build are present.
        for key in ("scope_fraction", "targeted_constraints", "per_target_edits"):
            self.assertIn(key, meta)
        self.assertIn("personal:1", meta["per_target_edits"])

    def test_multi_failure_feedback_fields(self):
        s = R3AdaptiveScopeRepair()
        problem = {"nature_language": "q",
                   "hard_logic_py": ["result=True", "result=False", "result=False"]}
        verification = {
            "personal_constraints": [True, False, False],
            "commonsense_errors": ["c-a", "c-b"],
            "schema_errors": [],
            "error_info": ["c-a", "c-b",
                           "Personal constraint 2 failed: result=False",
                           "Personal constraint 3 failed: result=False"],
        }
        meta = s.repair(problem, self._plan(), verification, _ctx(),
                        _MockLLM("not json")).metadata
        self.assertEqual(meta["target_constraint_indices"], [2, 3])
        self.assertEqual(meta["feedback_personal_constraint_indices"], [2, 3])
        self.assertEqual(meta["feedback_commonsense_failure_count"], 2)

    def test_commonsense_count_unavailable_is_none(self):
        s = R3AdaptiveScopeRepair()
        problem = {"nature_language": "q", "hard_logic_py": ["result=False"]}
        verification = {"personal_constraints": [False], "schema_errors": [],
                        "error_info": ["Personal constraint 1 failed: result=False"]}
        meta = s.repair(problem, self._plan(), verification, _ctx(),
                        _MockLLM("not json")).metadata
        self.assertIsNone(meta["feedback_commonsense_failure_count"])
        self.assertEqual(meta["feedback_personal_constraint_indices"], [1])

    def test_escalation_reason_reported_on_widen(self):
        s = R3AdaptiveScopeRepair(rounds_per_rung=1)
        plan = self._plan()
        # With one iteration per rung, the schedule widens slot -> day on the
        # second repair, which must be reported in escalation_reason.
        problem = {"nature_language": "q",
                   "hard_logic_py": ["total=0\nresult=(total<=1)"]}
        verification = {"personal_constraints": [False], "commonsense_errors": [],
                        "schema_errors": [], "error_info": ["budget failed"]}
        llm = _MockLLM("not json")   # parse failure -> no-op, violations persist
        first = s.repair(problem, plan, verification, _ctx(), llm)
        self.assertEqual(first.metadata["editable_scope"], "slot")
        self.assertNotIn("escalation_reason", first.metadata)
        second = s.repair(problem, plan, verification, _ctx(), llm)
        self.assertEqual(second.metadata["editable_scope"], "day")
        self.assertEqual(second.metadata["scope_level"], 2)
        self.assertIn("escalation_reason", second.metadata)
        self.assertIn("slot_to_day", second.metadata["escalation_reason"])


@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP)
class PlanScopeStructureGuardTests(unittest.TestCase):
    """At L3 the whole proposal replaces the plan, so a truncated/partial reply
    must not be allowed to drop days or empty them."""

    def _plan(self):
        return [
            {"day": 1, "activities": [
                {"type": "attraction", "position": "A", "cost": 10},
                {"type": "lunch", "position": "B", "cost": 20}]},
            {"day": 2, "activities": [
                {"type": "dinner", "position": "C", "cost": 30}]},
        ]

    def _third_repair(self, proposal):
        """Run 3 repairs with one iteration per rung; the third is at plan scope."""
        s = R3AdaptiveScopeRepair(rounds_per_rung=1)
        problem = {"nature_language": "q", "hard_logic_py": ["result=False"]}
        verification = {"personal_constraints": [False], "commonsense_errors": [],
                        "schema_errors": [],
                        "error_info": ["Personal constraint 1 failed: result=False"]}
        llm = _MockLLM(_continuation(proposal))
        for _ in range(2):
            s.repair(problem, self._plan(), verification, _ctx(), llm)
        result = s.repair(problem, self._plan(), verification, _ctx(), llm)
        self.assertEqual(result.metadata["editable_scope"], "plan")
        return result

    def test_day_count_mismatch_keeps_current_plan(self):
        result = self._third_repair([self._plan()[0]])   # 1 day for a 2-day trip
        self.assertEqual(result.repaired_plan, self._plan())
        self.assertEqual(result.metadata["proposal_rejected_reason"], "day_count_mismatch")
        self.assertEqual(result.metadata["changed_slots"], 0)

    def test_empty_day_keeps_current_plan(self):
        proposal = self._plan()
        proposal[0]["activities"] = []
        result = self._third_repair(proposal)
        self.assertEqual(result.repaired_plan, self._plan())
        self.assertEqual(result.metadata["proposal_rejected_reason"], "missing_activities")

    def test_well_formed_proposal_is_taken(self):
        proposal = self._plan()
        proposal[1]["activities"][0]["position"] = "C2"
        result = self._third_repair(proposal)
        self.assertEqual(result.repaired_plan, proposal)
        self.assertIsNone(result.metadata["proposal_rejected_reason"])
        self.assertEqual(result.metadata["changed_slots"], 1)


@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP)
class PhasedR3PTests(unittest.TestCase):
    """R3P: personal-only phase on the ladder, then a protected slot-scope
    commonsense phase."""

    CS_ALPHA = "The attraction, Alpha in day 1, is closed when you visiting."
    CS_BRAVO = "Incorrect price information of Bravo."

    def _plan(self):
        return [{"day": 1, "activities": [
            {"type": "attraction", "position": "Alpha", "cost": 10},
            {"type": "lunch", "position": "Bravo", "cost": 20}]}]

    def _personal_failing(self):
        problem = {"nature_language": "q",
                   "hard_logic_py": ["result = (x == 'Bravo')"]}
        verification = {"personal_constraints": [False],
                        "commonsense_errors": [self.CS_ALPHA], "schema_errors": [],
                        "error_info": [self.CS_ALPHA,
                                       "Personal constraint 1 failed: result = (x == 'Bravo')"]}
        return problem, verification

    def test_r3p_is_registered_and_named(self):
        s = create_repair_strategy("R3P")
        self.assertIsInstance(s, R3AdaptiveScopeRepair)
        problem, verification = self._personal_failing()
        meta = s.repair(problem, self._plan(), verification, _ctx(), _MockLLM("not json")).metadata
        self.assertEqual(meta["strategy"], "R3P")
        # Plain R3 is unchanged: no phase keys, all feedback shown.
        meta_r3 = create_repair_strategy("R3").repair(
            problem, self._plan(), verification, _ctx(), _MockLLM("not json")).metadata
        self.assertEqual(meta_r3["strategy"], "R3")
        self.assertNotIn("repair_phase", meta_r3)
        self.assertIn(self.CS_ALPHA, meta_r3["prompt"])

    def test_personal_phase_hides_commonsense(self):
        problem, verification = self._personal_failing()
        meta = R3AdaptiveScopeRepair(phased=True).repair(
            problem, self._plan(), verification, _ctx(), _MockLLM("not json")).metadata
        self.assertEqual(meta["repair_phase"], "personal")
        self.assertNotIn(self.CS_ALPHA, meta["prompt"])
        self.assertIn("Personal constraint 1 failed", meta["prompt"])
        # Only the personal constraint's slot (Bravo); the commonsense error's
        # day-1 localization is not opened.
        self.assertEqual([(d["day"], d["activity_index"]) for d in meta["editable_slots"]],
                         [(0, 1)])
        self.assertEqual(meta["target_constraint_indices"], [1])
        self.assertEqual(meta["protected_constraint_indices"], [])
        self.assertEqual(meta["feedback_personal_constraint_indices"], [1])
        self.assertEqual(meta["feedback_commonsense_failure_count"], 0)

    def test_switches_to_protected_commonsense_when_personal_pass(self):
        problem = {"nature_language": "q",
                   "hard_logic_py": ["result=(a<=1500)", "result=(b==1)", "result=(c==2)"]}
        verification = {"personal_constraints": [True, None, True],
                        "commonsense_errors": [self.CS_ALPHA, self.CS_BRAVO],
                        "schema_errors": [],
                        "error_info": [self.CS_ALPHA, self.CS_BRAVO]}
        meta = R3AdaptiveScopeRepair(phased=True).repair(
            problem, self._plan(), verification, _ctx(), _MockLLM("not json")).metadata
        self.assertEqual(meta["repair_phase"], "commonsense")
        self.assertEqual(meta["editable_scope"], "slot")
        self.assertEqual(meta["scope_level"], 1)
        self.assertEqual(meta["target_constraint_indices"], [])
        self.assertEqual(meta["protected_constraint_indices"], [1, 3])
        self.assertIn(PROTECT_HEADER, meta["prompt"])
        self.assertIn("Personal constraint 1 (satisfied): result=(a<=1500)", meta["prompt"])
        self.assertIn("Personal constraint 3 (satisfied): result=(c==2)", meta["prompt"])
        self.assertNotIn("Personal constraint 2", meta["prompt"])
        self.assertEqual(meta["feedback_personal_constraint_indices"], [])
        self.assertEqual(meta["feedback_commonsense_failure_count"], 2)
        self.assertEqual(meta["personal_iteration"], 0)   # ladder did not move

    def test_commonsense_forced_after_personal_budget(self):
        s = R3AdaptiveScopeRepair(phased=True)
        problem, verification = self._personal_failing()
        llm = _MockLLM("not json")
        metas = [s.repair(problem, self._plan(), verification, _ctx(), llm).metadata
                 for _ in range(6)]
        self.assertEqual([m["repair_phase"] for m in metas], ["personal"] * 5 + ["commonsense"])
        self.assertEqual([m["editable_scope"] for m in metas],
                         ["slot", "slot", "day", "day", "plan", "slot"])
        self.assertNotIn("Personal constraint 1 failed", metas[5]["prompt"])
        self.assertIn(self.CS_ALPHA, metas[5]["prompt"])
        self.assertEqual(metas[5]["target_constraint_indices"], [])

    def test_returns_to_personal_after_a_break(self):
        s = R3AdaptiveScopeRepair(phased=True)
        problem, failing = self._personal_failing()
        passing = dict(failing, personal_constraints=[True], error_info=[self.CS_ALPHA])
        llm = _MockLLM("not json")
        first = s.repair(problem, self._plan(), passing, _ctx(), llm).metadata
        second = s.repair(problem, self._plan(), failing, _ctx(), llm).metadata
        self.assertEqual(first["repair_phase"], "commonsense")
        self.assertEqual(first["protected_constraint_indices"], [1])
        self.assertEqual(second["repair_phase"], "personal")
        self.assertEqual(second["personal_iteration"], 1)
        self.assertEqual(second["editable_scope"], "slot")
        self.assertNotIn("escalation_reason", second)

    def test_commonsense_phase_record_through_shared_loop(self):
        problem = {"uid": "r3p-case", "people_number": 1, "start_city": "A",
                   "target_city": "B", "nature_language": "q",
                   "hard_logic_py": ["result=(a<=1500)", "result=(b==1)"]}
        plan = self._plan()
        before = {"personal_constraints": [True, True], "commonsense_errors": [self.CS_BRAVO],
                  "error_info": [self.CS_BRAVO], "passed": False}
        after = {"personal_constraints": [False, True], "commonsense_errors": [],
                 "error_info": ["Personal constraint 1 failed: result=(a<=1500)"],
                 "passed": False}
        with patch.object(loop, "verify_plan", side_effect=[before, after]):
            out = loop.run_repair_loop(problem, plan, R3AdaptiveScopeRepair(phased=True),
                                       _ctx(), _MockLLM(_continuation(plan)), None,
                                       max_steps=1)
        record = RepairAttemptRecord.from_dict(out["history"][1]["repair_attempt"])
        self.assertEqual(record.repair_strategy, "R3P")
        self.assertEqual(record.target_constraint_indices, [])
        self.assertEqual(record.protected_constraint_indices, [1, 2])
        self.assertEqual(record.editable_scope, "slot")
        self.assertEqual(record.newly_violated, [1])
        self.assertEqual(record.repair_metadata["repair_phase"], "commonsense")


@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP)
class SharedLoopContractTests(unittest.TestCase):
    """R3 run through the real loop must yield a valid RepairAttemptRecord with the
    canonical intent promoted and no canonical keys left in repair_metadata."""

    def _problem(self):
        return {"uid": "r3-case", "people_number": 1, "start_city": "A",
                "target_city": "B", "nature_language": "q",
                "hard_logic_py": ["result = (activity_position(a) == 'B')"]}

    def test_record_validates_with_canonical_scope_and_targets(self):
        plan = [{"day": 1, "activities": [
            {"type": "attraction", "position": "A", "cost": 10},
            {"type": "lunch", "position": "B", "cost": 20}]}]
        fixed_lunch = {"type": "lunch", "position": "B2", "cost": 20}
        llm = _MockLLM(_continuation([{"day": 1, "activities": [
            {"type": "attraction", "position": "A", "cost": 10}, fixed_lunch]}]))

        before = {"personal_constraints": [False], "commonsense_errors": ["c1"],
                  "error_info": ["Personal constraint 1 failed"], "passed": False}
        after = {"personal_constraints": [True], "commonsense_errors": [],
                 "error_info": [], "passed": True}
        with patch.object(loop, "verify_plan", side_effect=[before, after]):
            out = loop.run_repair_loop(self._problem(), plan,
                                       R3AdaptiveScopeRepair(), _ctx(), llm, None,
                                       max_steps=1)

        entry = out["history"][1]
        record = RepairAttemptRecord.from_dict(entry["repair_attempt"])
        self.assertEqual(record.repair_strategy, "R3")
        self.assertEqual(record.editable_scope, "slot")
        self.assertEqual(record.scope_level, 1)
        self.assertEqual(record.target_constraint_indices, [1])
        # loop derives concurrent context authoritatively from the BEFORE vector.
        self.assertEqual(record.concurrent_failed_constraint_indices, [1])
        self.assertEqual(record.concurrent_commonsense_failure_count, 1)
        # no canonical/intent key leaks into the debug payload.
        self.assertFalse(set(INTENT_FIELDS + DERIVED_FIELDS) & record.repair_metadata.keys())
        self.assertNotIn("scope", record.repair_metadata)
        # R3-specific debug survives in repair_metadata.
        self.assertIn("scope_fraction", record.repair_metadata)
        self.assertIn("per_target_edits", record.repair_metadata)

    def _multi_problem(self):
        return {"uid": "r3-multi", "people_number": 1, "start_city": "A",
                "target_city": "B", "nature_language": "q",
                "hard_logic_py": [f"result = (c{i} == 1)" for i in range(1, 7)]}

    def _run_multi(self, after_states):
        """Run one R3 attempt where #2 and #5 fail together (plus one
        commonsense error) and the verifier returns ``after_states``."""
        plan = [{"day": 1, "activities": [
            {"type": "attraction", "position": "A", "cost": 10},
            {"type": "lunch", "position": "B", "cost": 20}]}]
        llm = _MockLLM(_continuation(plan))
        before = {
            "personal_constraints": [True, False, True, True, False, True],
            "commonsense_errors": ["c1"],
            "error_info": ["c1",
                           "Personal constraint 2 failed: result = (c2 == 1)",
                           "Personal constraint 5 failed: result = (c5 == 1)"],
            "passed": False,
        }
        after = {"personal_constraints": after_states, "commonsense_errors": [],
                 "error_info": [], "passed": False}
        with patch.object(loop, "verify_plan", side_effect=[before, after]):
            out = loop.run_repair_loop(self._multi_problem(), plan,
                                       R3AdaptiveScopeRepair(), _ctx(), llm, None,
                                       max_steps=1)
        entry = out["history"][1]["repair_attempt"]
        return RepairAttemptRecord.from_dict(entry), entry

    def test_multi_target_record_pairs_targets_with_breaks(self):
        record, entry = self._run_multi([True, True, False, True, False, True])
        # What R3 tried to fix (all failures together) ...
        self.assertEqual(record.target_constraint_indices, [2, 5])
        # ... and what the repair broke / fixed, measured by the loop.
        self.assertEqual(record.newly_violated, [3])
        self.assertEqual(record.fixed, [2])
        self.assertEqual(record.still_failed, [5])
        self.assertEqual(record.feedback_personal_constraint_indices, [2, 5])
        self.assertEqual(record.feedback_commonsense_failure_count, 1)
        self.assertEqual(record.editable_scope, "slot")
        self.assertEqual(record.scope_level, 1)
        self.assertFalse(set(INTENT_FIELDS + DERIVED_FIELDS) & record.repair_metadata.keys())
        # Serialized form round-trips unchanged.
        self.assertEqual(RepairAttemptRecord.from_dict(record.to_dict()).to_dict(), entry)

    def test_unknown_after_state_is_not_a_break(self):
        record, _ = self._run_multi([True, True, None, True, False, True])
        self.assertEqual(record.newly_violated, [])
        self.assertEqual(record.unknown, [3])
        self.assertEqual(record.target_constraint_indices, [2, 5])


if __name__ == "__main__":
    unittest.main()
