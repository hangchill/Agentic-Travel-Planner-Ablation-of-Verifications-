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

    def _two_day_plan(self):
        return [
            {"day": 1, "activities": [
                {"type": "attraction", "position": "Museum", "cost": 10},
                {"type": "lunch", "position": "Noodle House", "cost": 20},
                {"type": "attraction", "position": "Park", "cost": 0}]},
            {"day": 2, "activities": [
                {"type": "attraction", "position": "Tower", "cost": 30},
                {"type": "lunch", "position": "Noodle House", "cost": 20}]},
        ]

    def _localize(self, message, plan):
        from chinatravel.agent.nesy_verifier.repair_strategies import r3
        pos_to_slots, _ = r3._index_plan(plan)
        return r3._localize_message(message, plan, pos_to_slots)

    def test_named_poi_with_day_opens_only_that_slot(self):
        plan = self._two_day_plan()
        loc = self._localize("The attraction, Museum in day 1, is closed when you visiting.", plan)
        self.assertEqual(loc, {(0, 0)})

    def test_named_poi_repeated_on_another_day_is_not_opened(self):
        plan = self._two_day_plan()
        loc = self._localize("The restaurant, Noodle House in day 2, is closed when you visiting.", plan)
        self.assertEqual(loc, {(1, 1)})

    def test_day_without_name_or_activity_opens_whole_day(self):
        plan = self._two_day_plan()
        loc = self._localize("The activities in day 1 overlap.", plan)
        self.assertEqual(loc, {(0, 0), (0, 1), (0, 2)})

    def test_day_and_activity_number_opens_that_activity(self):
        plan = self._two_day_plan()
        loc = self._localize("Day 2 activity 1 has an invalid time.", plan)
        self.assertEqual(loc, {(1, 0)})

    def test_name_without_day_keeps_all_matches(self):
        plan = self._two_day_plan()
        loc = self._localize("Incorrect price information of Noodle House.", plan)
        self.assertEqual(loc, {(0, 1), (1, 1)})

    def test_global_heuristic_picks_highest_cost_nonanchor(self):
        s = R3AdaptiveScopeRepair()
        plan = self._plan()
        editable, global_present = s._editable_region("slot", plan, ["global"])
        self.assertTrue(global_present)
        # highest-cost non-anchor is the lunch (20) over attraction (10); hotel excluded.
        self.assertIn((0, 1), editable)
        self.assertNotIn((0, 2), editable)


@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP)
class BookingUnlockTests(unittest.TestCase):
    """Commonsense errors about a booking open it below the plan rung."""

    HOTEL = "Atour Hotel"

    def _plan(self):
        leg = lambda src, dst: {"from": src, "to": dst, "mode": "metro",
                                "start_time": "18:00", "end_time": "18:30", "cost": 6}
        return [
            {"day": 1, "activities": [
                {"type": "train", "TrainID": "G1", "start": "S", "end": "T", "cost": 300},
                {"type": "attraction", "position": "Museum", "cost": 10},
                {"type": "accommodation", "position": self.HOTEL, "cost": 400, "rooms": 1,
                 "start_time": "19:00", "end_time": "24:00", "transports": leg("Museum", self.HOTEL)}]},
            {"day": 2, "activities": [
                {"type": "attraction", "position": "Tower", "cost": 30},
                {"type": "airplane", "FlightID": "F9", "start": "T", "end": "S", "cost": 900}]},
        ]

    def _unlocks(self, *messages, kind="commonsense"):
        from chinatravel.agent.nesy_verifier.repair_strategies import r3
        s = R3AdaptiveScopeRepair()
        plan = self._plan()
        key = "dsl" if kind == "personal" else "message"
        targets = [{"kind": kind, "ref": f"x{i}", key: m} for i, m in enumerate(messages)]
        localized = s._localize_targets(targets, plan)
        return s._booking_unlocks(targets, localized, plan), localized

    def test_accommodation_error_unlocks_hotel_fully(self):
        unlocked, localized = self._unlocks("Incorrect cost information of accommodation. [cost = price * rooms]")
        self.assertEqual(localized, [{(0, 2)}])       # not "global" any more
        self.assertEqual(unlocked, {(0, 2): "all"})

    def test_accommodation_error_with_day_unlocks_only_that_day(self):
        unlocked, _ = self._unlocks(f"Incorrect price infomation of accommodation ,{self.HOTEL} in day 2.")
        self.assertEqual(unlocked, {})                 # no hotel on day 2
        unlocked, _ = self._unlocks(f"Incorrect price infomation of accommodation ,{self.HOTEL} in day 1.")
        self.assertEqual(unlocked, {(0, 2): "all"})

    def test_intercity_errors_unlock_go_and_back_bookings(self):
        go, _ = self._unlocks("Incorrect duration information of given intercity transport "
                              "from origin to destination G1 [start_time -> end_time].")
        back, _ = self._unlocks("Incorrect cost information of given intercity airplane (Back) "
                                "[cost = price * tickets].")
        self.assertEqual(go, {(0, 0): "all"})
        self.assertEqual(back, {(1, 1): "all"})

    def test_leg_into_hotel_unlocks_only_leg_fields(self):
        unlocked, _ = self._unlocks(f"Incorrect cost infomation of innercity transport in day 1, "
                                    f"from Museum to {self.HOTEL}, metro. [cost = price * people_number]")
        self.assertEqual(unlocked, {(0, 2): "legs"})

    def test_whole_day_fallback_does_not_unlock_bookings(self):
        unlocked, localized = self._unlocks("The activities in day 1 overlap.")
        self.assertEqual(localized, [{(0, 0), (0, 1), (0, 2)}])
        self.assertEqual(unlocked, {})

    # ---- personal constraints (the priority) ----
    ROOM_DSL = ("result=True\nfor activity in allactivities(plan):\n"
                "  if activity_type(activity)=='accommodation' and room_type(activity)!=1: result=False")
    INTERCITY_DSL = ("intercity_transport_set=set()\nfor activity in allactivities(plan):\n"
                     "  if activity_type(activity) in ['train', 'airplane']: "
                     "intercity_transport_set.add(intercity_transport_type(activity))\n"
                     "result=({'airplane'}==intercity_transport_set)")
    METRO_DSL = ("result=True\nfor activity in allactivities(plan):\n"
                 "  if innercity_transport_type(activity_transports(activity))!='metro': result=False")
    BUDGET_DSL = ("total_cost=0\nfor activity in allactivities(plan):\n"
                  "    total_cost+=activity_cost(activity)\n"
                  "    total_cost += innercity_transport_cost(activity_transports(activity))\n"
                  "result=(total_cost<=1000)")

    def test_personal_hotel_constraint_unlocks_hotel_fully(self):
        unlocked, localized = self._unlocks(self.ROOM_DSL, kind="personal")
        self.assertEqual(localized, [{(0, 2)}])
        self.assertEqual(unlocked, {(0, 2): "all"})

    def test_personal_intercity_constraint_unlocks_go_and_back(self):
        unlocked, _ = self._unlocks(self.INTERCITY_DSL, kind="personal")
        self.assertEqual(unlocked, {(0, 0): "all", (1, 1): "all"})

    def test_personal_quoted_booking_name_unlocks_it(self):
        unlocked, _ = self._unlocks(
            f"result=True\nfor activity in allactivities(plan):\n"
            f"  if activity_type(activity)=='accommodation' and activity_position(activity)!='{self.HOTEL}': "
            f"result=False", kind="personal")
        self.assertEqual(unlocked, {(0, 2): "all"})

    def test_personal_leg_constraint_opens_legs_and_hotel_leg_fields(self):
        unlocked, localized = self._unlocks(self.METRO_DSL, kind="personal")
        self.assertEqual(localized, [{(0, 2)}])     # the only activity with a leg here
        self.assertEqual(unlocked, {(0, 2): "legs"})

    def test_personal_budget_unlocks_costliest_bookings(self):
        unlocked, localized = self._unlocks(self.BUDGET_DSL, kind="personal")
        self.assertEqual(localized, ["global"])
        # Costs: airplane 900, hotel 400, train 300 are the 3 most expensive.
        self.assertEqual(unlocked, {(1, 1): "all", (0, 2): "all", (0, 0): "all"})

    def test_personal_non_booking_constraint_unlocks_nothing(self):
        unlocked, _ = self._unlocks("result=(day_count(plan)==2)", kind="personal")
        self.assertEqual(unlocked, {})
        unlocked, _ = self._unlocks(
            "result=True\nfor activity in allactivities(plan):\n"
            "  if activity_type(activity)=='attraction' and activity_cost(activity)>50: result=False",
            kind="personal")
        self.assertEqual(unlocked, {})

    def test_personal_step1_at_slot_can_change_the_hotel(self):
        plan = self._plan()
        verification = {"personal_constraints": [False], "commonsense_errors": [],
                        "schema_errors": [],
                        "error_info": [f"Personal constraint 1 failed: {self.ROOM_DSL}"]}
        problem = {"nature_language": "q", "hard_logic_py": [self.ROOM_DSL]}
        fixed = json.loads(json.dumps(plan))
        fixed[0]["activities"][2]["room_type"] = 1
        meta = R3AdaptiveScopeRepair().repair(
            problem, plan, verification, dict(_ctx(), repair_phase="personal"),
            _MockLLM(_continuation(fixed))).metadata
        self.assertEqual(meta["editable_scope"], "slot")
        self.assertEqual([(b["day"], b["activity_index"], b["fields"]) for b in meta["unlocked_bookings"]],
                         [(0, 2, "all")])
        self.assertEqual(meta["changed_slots"], 1)

    def test_slot_region_includes_unlocked_booking(self):
        s = R3AdaptiveScopeRepair()
        plan = self._plan()
        editable, _ = s._editable_region("slot", plan, [{(0, 2)}], {(0, 2): "all"})
        self.assertIn((0, 2), editable)
        frozen, _ = s._editable_region("slot", plan, [{(0, 2)}])
        self.assertNotIn((0, 2), frozen)

    def test_leg_only_merge_keeps_the_booking(self):
        plan = self._plan()
        proposal = json.loads(json.dumps(plan))
        hotel = proposal[0]["activities"][2]
        hotel["transports"]["cost"] = 12
        hotel["start_time"] = "19:30"
        hotel["position"] = "Other Hotel"   # must be ignored
        hotel["cost"] = 1                   # must be ignored
        merged, changed = R3AdaptiveScopeRepair._merge(plan, proposal, {(0, 2)}, frozenset({(0, 2)}))
        got = merged[0]["activities"][2]
        self.assertEqual(changed, 1)
        self.assertEqual(got["transports"]["cost"], 12)
        self.assertEqual(got["start_time"], "19:30")
        self.assertEqual(got["position"], self.HOTEL)
        self.assertEqual(got["cost"], 400)

    def test_commonsense_step_at_slot_opens_hotel_and_logs_it(self):
        plan = self._plan()
        error = "Incorrect cost information of accommodation. [cost = price * rooms]"
        leg_error = (f"Incorrect cost infomation of innercity transport in day 1, "
                     f"from Museum to {self.HOTEL}, metro. [cost = price * people_number]")
        verification = {"personal_constraints": [True], "commonsense_errors": [error],
                        "schema_errors": [], "error_info": [error]}
        problem = {"nature_language": "q", "hard_logic_py": ["result=True"]}
        fixed = json.loads(json.dumps(plan))
        fixed[0]["activities"][2]["cost"] = 380
        meta = R3AdaptiveScopeRepair().repair(
            problem, plan, verification, dict(_ctx(), repair_phase="commonsense"),
            _MockLLM(_continuation(fixed))).metadata
        self.assertEqual(meta["editable_scope"], "slot")
        self.assertFalse(meta["global_targets"])
        self.assertEqual(meta["unlocked_bookings"],
                         [{"day": 0, "activity_index": 2, "type": "accommodation",
                           "position": self.HOTEL, "fields": "all"}])
        self.assertIn(f"Day 1 activity 3: {self.HOTEL}", meta["prompt"])
        self.assertEqual(meta["changed_slots"], 1)
        # A leg-only unlock is spelled out in the prompt.
        verification = dict(verification, commonsense_errors=[leg_error], error_info=[leg_error])
        meta = R3AdaptiveScopeRepair().repair(
            problem, plan, verification, dict(_ctx(), repair_phase="commonsense"),
            _MockLLM("not json")).metadata
        self.assertIn("only its transports, start_time and end_time", meta["prompt"])
        self.assertEqual(meta["unlocked_bookings"][0]["fields"], "legs")

    def test_plan_scope_reports_no_unlock(self):
        s = R3AdaptiveScopeRepair(rounds_per_rung=1)
        plan = self._plan()
        error = "Incorrect cost information of accommodation. [cost = price * rooms]"
        verification = {"personal_constraints": [True], "commonsense_errors": [error],
                        "schema_errors": [], "error_info": [error]}
        problem = {"nature_language": "q", "hard_logic_py": ["result=True"]}
        for _ in range(3):
            meta = s.repair(problem, plan, verification, dict(_ctx(), repair_phase="commonsense"),
                            _MockLLM("not json")).metadata
        self.assertEqual(meta["editable_scope"], "plan")
        self.assertEqual(meta["unlocked_bookings"], [])


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
class R3PhaseTests(unittest.TestCase):
    """R3 follows the phase the shared loop supplies. Every iteration, whatever
    its phase, climbs the ladder; the commonsense iteration is protected and uses
    the current rung."""

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

    @staticmethod
    def _phase_ctx(phase):
        return dict(_ctx(), repair_phase=phase)

    def test_r3p_is_not_registered(self):
        with self.assertRaises(ValueError):
            create_repair_strategy("R3P")
        # A direct call without a shared phase: no phase keys, all feedback shown.
        problem, verification = self._personal_failing()
        meta = create_repair_strategy("R3").repair(
            problem, self._plan(), verification, _ctx(), _MockLLM("not json")).metadata
        self.assertEqual(meta["strategy"], "R3")
        self.assertNotIn("repair_phase", meta)
        self.assertIn(self.CS_ALPHA, meta["prompt"])

    def test_unknown_phase_is_rejected(self):
        problem, verification = self._personal_failing()
        with self.assertRaises(ValueError):
            R3AdaptiveScopeRepair().repair(problem, self._plan(), verification,
                                           self._phase_ctx("bogus"), _MockLLM("not json"))

    def test_personal_phase_hides_commonsense(self):
        problem, verification = self._personal_failing()
        meta = R3AdaptiveScopeRepair().repair(
            problem, self._plan(), verification, self._phase_ctx("personal"),
            _MockLLM("not json")).metadata
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

    def test_commonsense_phase_is_protected(self):
        problem = {"nature_language": "q",
                   "hard_logic_py": ["result=(a<=1500)", "result=(b==1)", "result=(c==2)"]}
        verification = {"personal_constraints": [True, None, True],
                        "commonsense_errors": [self.CS_ALPHA, self.CS_BRAVO],
                        "schema_errors": [],
                        "error_info": [self.CS_ALPHA, self.CS_BRAVO]}
        meta = R3AdaptiveScopeRepair().repair(
            problem, self._plan(), verification, self._phase_ctx("commonsense"),
            _MockLLM("not json")).metadata
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
        self.assertEqual(meta["iteration"], 1)   # the commonsense step moved the ladder
        self.assertNotIn("personal_iteration", meta)

    def test_ladder_over_five_personal_then_commonsense(self):
        s = R3AdaptiveScopeRepair()
        problem, verification = self._personal_failing()
        llm = _MockLLM("not json")
        phases = ["personal"] * 5 + ["commonsense"]
        metas = [s.repair(problem, self._plan(), verification, self._phase_ctx(p), llm).metadata
                 for p in phases]
        self.assertEqual([m["repair_phase"] for m in metas], phases)
        self.assertEqual([m["editable_scope"] for m in metas],
                         ["slot", "slot", "day", "day", "plan", "plan"])
        self.assertNotIn("Personal constraint 1 failed", metas[5]["prompt"])
        self.assertIn(self.CS_ALPHA, metas[5]["prompt"])
        self.assertEqual(metas[5]["target_constraint_indices"], [])
        # Plan scope: no limited-scope block, the whole plan is editable.
        self.assertNotIn("LIMITED EDIT SCOPE", metas[5]["prompt"])
        self.assertEqual(metas[5]["scope_fraction"], 1.0)

    def test_commonsense_advances_ladder(self):
        s = R3AdaptiveScopeRepair()
        problem, failing = self._personal_failing()
        passing = dict(failing, personal_constraints=[True], error_info=[self.CS_ALPHA])
        llm = _MockLLM("not json")
        first = s.repair(problem, self._plan(), passing, self._phase_ctx("commonsense"), llm).metadata
        second = s.repair(problem, self._plan(), failing, self._phase_ctx("personal"), llm).metadata
        third = s.repair(problem, self._plan(), failing, self._phase_ctx("personal"), llm).metadata
        self.assertEqual(first["repair_phase"], "commonsense")
        self.assertEqual(first["protected_constraint_indices"], [1])
        self.assertEqual([m["iteration"] for m in (first, second, third)], [1, 2, 3])
        self.assertEqual([m["editable_scope"] for m in (first, second, third)],
                         ["slot", "slot", "day"])
        self.assertEqual(third["escalation_reason"], "scheduled_widen_slot_to_day_at_iteration_3")

    def test_commonsense_step_crossing_a_rung_reports_escalation(self):
        s = R3AdaptiveScopeRepair()
        problem, failing = self._personal_failing()
        passing = dict(failing, personal_constraints=[True], error_info=[self.CS_ALPHA])
        llm = _MockLLM("not json")
        for _ in range(2):
            s.repair(problem, self._plan(), failing, self._phase_ctx("personal"), llm)
        meta = s.repair(problem, self._plan(), passing, self._phase_ctx("commonsense"), llm).metadata
        self.assertEqual(meta["repair_phase"], "commonsense")
        self.assertEqual(meta["editable_scope"], "day")
        self.assertEqual(meta["scope_level"], 2)
        self.assertEqual(meta["escalation_reason"], "scheduled_widen_slot_to_day_at_iteration_3")

    def test_commonsense_phase_record_through_shared_loop(self):
        problem = {"uid": "r3-cs-case", "people_number": 1, "start_city": "A",
                   "target_city": "B", "nature_language": "q",
                   "hard_logic_py": ["result=(a<=1500)", "result=(b==1)"]}
        plan = self._plan()
        before = {"personal_constraints": [True, True], "commonsense_errors": [self.CS_BRAVO],
                  "error_info": [self.CS_BRAVO], "passed": False}
        after = {"personal_constraints": [False, True], "commonsense_errors": [],
                 "error_info": ["Personal constraint 1 failed: result=(a<=1500)"],
                 "passed": False}
        with patch.object(loop, "verify_plan", side_effect=[before, after]):
            out = loop.run_repair_loop(problem, plan, R3AdaptiveScopeRepair(),
                                       _ctx(), _MockLLM(_continuation(plan)), None,
                                       max_steps=1)
        record = RepairAttemptRecord.from_dict(out["history"][1]["repair_attempt"])
        self.assertEqual(record.repair_strategy, "R3")
        self.assertEqual(record.target_constraint_indices, [])
        self.assertEqual(record.protected_constraint_indices, [1, 2])
        self.assertEqual(record.editable_scope, "slot")
        self.assertEqual(record.newly_violated, [1])
        self.assertEqual(record.repair_phase, "commonsense")


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
        self.assertEqual(record.feedback_commonsense_failure_count, 0)
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




@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP)
class SharedR3SchedulingTests(unittest.TestCase):
    """Exercise R3 under the authoritative shared scheduler."""

    def run_scheduled(self, initial, outcomes, schema_errors=None):
        problem = dict(uid="scheduled-r3", people_number=1, start_city="A", target_city="B",
                       nature_language="q", hard_logic_py=["result=day_count(plan)==1"])
        plan = [{"day": 1, "activities": [{"type": "attraction", "position": "Alpha", "cost": 10}]}]
        def state(values):
            personal, cs = values
            errors = [R3PhaseTests.CS_ALPHA] if cs else []
            return dict(personal_constraints=[personal], commonsense_errors=errors, schema_errors=list(schema_errors or []),
                        error_info=errors + list(schema_errors or []) + (["Personal constraint 1 failed: result=day_count(plan)==1"] if personal is False else []),
                        passed=personal is True and not cs and not schema_errors)
        strategy = R3AdaptiveScopeRepair()
        executed = []
        feedback = strategy._feedback_lines
        def capture(problem, verification, phase):
            executed.append(phase)
            return feedback(problem, verification, phase)
        with patch.object(strategy, '_feedback_lines', side_effect=capture), \
             patch.object(loop, 'verify_plan', side_effect=[state(value) for value in outcomes]):
            output = loop.run_repair_loop(problem, plan, strategy, _ctx(), _MockLLM('not json'), None,
                                          max_steps=6, initial_verification=state(initial))
        records = [RepairAttemptRecord.from_dict(entry['repair_attempt']) for entry in output['history'][1:]]
        self.assertEqual([r.repair_phase for r in records], executed)
        rung_for_step = ['slot', 'slot', 'day', 'day', 'plan', 'plan']
        for record in records:
            self.assertNotIn('repair_phase', record.repair_metadata)
            # One ladder clock: the rung follows the loop's step in both phases.
            self.assertEqual(record.editable_scope, rung_for_step[record.step - 1])
            self.assertEqual(record.repair_metadata['iteration'], record.step)
            targets = record.repair_metadata['targeted_constraints']
            if record.repair_phase == 'commonsense':
                self.assertEqual(record.target_constraint_indices, [])
                self.assertEqual(record.target_commonsense_errors, [R3PhaseTests.CS_ALPHA])
                self.assertFalse(any(t['kind'] == 'personal' for t in targets))
            else:
                self.assertFalse(any(t['kind'] == 'commonsense' for t in targets))
                self.assertEqual(record.feedback_commonsense_failure_count, 0)
                self.assertEqual(record.target_commonsense_errors, [])
        self.last_output = output
        return executed, records

    def test_scheduled_commonsense_excludes_schema_objective_but_preserves_evidence(self):
        from chinatravel.evaluation.regression_matrix import build_regression_matrix
        schema_errors = ['GLOBAL_SCHEMA_FAILURE unrelated to commonsense']
        phases, records = self.run_scheduled((True, True), [(True, False)], schema_errors)
        self.assertEqual(phases, ['commonsense'])
        record = records[0]
        self.assertEqual([t['kind'] for t in record.repair_metadata['targeted_constraints']], ['commonsense'])
        self.assertFalse(record.repair_metadata['global_targets'])
        self.assertNotIn(schema_errors[0], record.repair_metadata['prompt'])
        self.assertEqual(record.target_constraint_indices, [])
        self.assertEqual(record.protected_constraint_indices, [1])
        self.assertEqual(self.last_output['history'][0]['verification']['schema_errors'], schema_errors)
        self.assertEqual(self.last_output['verification']['schema_errors'], schema_errors)
        analysis = build_regression_matrix([record])
        self.assertTrue(all(r['eligible_count'] == 0 and r['regression_count'] == 0 for r in analysis['aggregate']))

    def test_direct_calls_keep_historical_schema_targets(self):
        from copy import deepcopy
        problem = dict(nature_language='q', hard_logic_py=['result=True'])
        verification = dict(personal_constraints=[True], commonsense_errors=[R3PhaseTests.CS_ALPHA],
                            schema_errors=['GLOBAL_SCHEMA_FAILURE'], error_info=[R3PhaseTests.CS_ALPHA])
        before = deepcopy(verification)
        result = R3AdaptiveScopeRepair().repair(
            problem, R3PhaseTests()._plan(), verification, _ctx(), _MockLLM('not json'))
        self.assertIn('schema', [t['kind'] for t in result.metadata['targeted_constraints']])
        self.assertEqual(verification, before)

    def test_returned_metadata_identifies_executed_shared_objective(self):
        problem = dict(nature_language='q', hard_logic_py=['result=True'])
        verification = dict(personal_constraints=[False],
                            commonsense_errors=[R3PhaseTests.CS_ALPHA],
                            schema_errors=['SCHEMA_ONLY'],
                            error_info=[R3PhaseTests.CS_ALPHA, 'Personal constraint 1 failed: result=True'])
        for phase in ('personal', 'commonsense'):
            with self.subTest(phase=phase):
                context = dict(_ctx(), repair_phase=phase)
                result = R3AdaptiveScopeRepair().repair(problem, R3PhaseTests()._plan(), verification,
                                                        context, _MockLLM('not json'))
                self.assertEqual(result.metadata['repair_phase'], phase)
                self.assertEqual(result.metadata['target_constraint_indices'], [1] if phase == 'personal' else [])
                self.assertEqual(result.metadata['target_commonsense_errors'],
                                 [R3PhaseTests.CS_ALPHA] if phase == 'commonsense' else [])
                self.assertNotIn('schema', [t['kind'] for t in result.metadata['targeted_constraints']])

    def test_shared_unknown_and_early_commonsense(self):
        phases, records = self.run_scheduled((None, True), [(None, True), (True, True), (True, False)])
        self.assertEqual(phases, ['personal', 'personal', 'commonsense'])
        self.assertIn('Personal constraint 1 is UNKNOWN', records[0].repair_metadata['prompt'])

    def test_forced_commonsense_with_concurrent_personal_failure(self):
        phases, records = self.run_scheduled((False, True), [(False, True)] * 6)
        self.assertEqual(phases, ['personal'] * 5 + ['commonsense'])
        self.assertEqual(records[-1].concurrent_failed_constraint_indices, [1])
        # Step 6 commonsense runs at the widest rung (plan), not slot.
        self.assertEqual([r.editable_scope for r in records],
                         ['slot', 'slot', 'day', 'day', 'plan', 'plan'])

    def test_recovery_then_second_commonsense(self):
        # Commonsense at step 2 breaks the personal constraint -> personal recovery
        # at steps 3-4 -> commonsense errors remain, so commonsense again at 5-6.
        phases, records = self.run_scheduled((False, True),
            [(True, True), (False, True), (False, True), (True, True), (True, True), (True, True)])
        self.assertEqual(phases, ['personal', 'commonsense', 'personal', 'personal',
                                  'commonsense', 'commonsense'])
        self.assertEqual([r.editable_scope for r in records],
                         ['slot', 'slot', 'day', 'day', 'plan', 'plan'])

    def test_commonsense_at_step_three_then_recovery(self):
        # Personal passes after step 2 -> step 3 commonsense at day scope; it
        # breaks the personal constraint -> steps 4-6 personal at day, plan, plan.
        phases, records = self.run_scheduled((False, True),
            [(False, True), (True, True), (False, True), (False, True), (False, True), (False, True)])
        self.assertEqual(phases, ['personal', 'personal', 'commonsense',
                                  'personal', 'personal', 'personal'])
        self.assertEqual([r.editable_scope for r in records],
                         ['slot', 'slot', 'day', 'day', 'plan', 'plan'])

    def test_commonsense_only_from_start_climbs_ladder(self):
        # Personal passes from the start and commonsense errors never clear:
        # six commonsense rounds, widening slot -> day -> plan.
        phases, records = self.run_scheduled((True, True), [(True, True)] * 6)
        self.assertEqual(phases, ['commonsense'] * 6)
        self.assertEqual([r.editable_scope for r in records],
                         ['slot', 'slot', 'day', 'day', 'plan', 'plan'])


if __name__ == "__main__":
    unittest.main()
