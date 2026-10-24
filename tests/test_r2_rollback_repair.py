#!/usr/bin/env python3
"""Offline unit tests for R2: R0 whole-plan regeneration with rollback.

A rewrite that breaks a previously passing personal constraint is rejected,
the shared loop keeps the last accepted plan, and the broken constraint is
remembered and listed in later repair prompts. Mock LLM / verifier only.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

try:
    from chinatravel.agent.nesy_verifier.repair_strategies.r2 import R2ProtectedRepair
    from chinatravel.agent.nesy_verifier.repair_strategies import create_repair_strategy
    from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
    from chinatravel.evaluation.repair_attempt import RepairAttemptRecord

    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - partial env only
    _IMPORT_ERROR = exc


_SKIP = f"could not import r2 (partial env?): {_IMPORT_ERROR}"

CONSTRAINTS = ["result=(cost<=1500)", "result=(hotel=='H')"]


def _ctx():
    keys = ["go_train_info", "go_flight_info", "back_train_info", "back_flight_info",
            "attraction_info", "restaurant_info", "accommodation_info", "innercity_transport_info"]
    return {k: "" for k in keys}


def _problem():
    return {"uid": "r2-case", "people_number": 1, "start_city": "A", "target_city": "B",
            "nature_language": "q", "days": 1, "hard_logic_py": list(CONSTRAINTS)}


def _plan(tag):
    return [{"day": 1, "activities": [{"type": "attraction", "position": tag}]}]


def _continuation(itinerary):
    text = json.dumps(itinerary, ensure_ascii=False)
    return text[len('[{"day": 1,'):]


def _state(personal):
    errors = [f"Personal constraint {i} failed: {CONSTRAINTS[i - 1]}"
              for i, state in enumerate(personal, 1) if state is False]
    return {"personal_constraints": list(personal), "commonsense_errors": [],
            "error_info": errors, "personal_errors": errors, "passed": all(s is True for s in personal)}


class _SequenceLLM:
    """Returns the given responses in order and keeps every prompt."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def __call__(self, messages, one_line=True, **kwargs):
        self.prompts.append(messages[0]["content"])
        return self.responses.pop(0)


@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP)
class R2RollbackTests(unittest.TestCase):
    def test_r2_is_registered(self):
        self.assertIsInstance(create_repair_strategy("R2"), R2ProtectedRepair)

    def test_accept_rejects_only_true_to_false(self):
        s = R2ProtectedRepair()
        self.assertFalse(s.accept(_state([False, True]), _state([True, False])))
        self.assertTrue(s.accept(_state([False, True]), _state([True, True])))
        self.assertTrue(s.accept(_state([False, True]), _state([False, None])))
        self.assertEqual(s._broken_constraints, {2: 1})

    def test_rollback_and_memory_through_shared_loop(self):
        start, broken, fixed = _plan("start"), _plan("broken"), _plan("fixed")
        llm = _SequenceLLM([_continuation(broken), _continuation(fixed)])
        verifications = [_state([False, True]), _state([True, False]), _state([True, True])]
        with patch.object(loop, "verify_plan", side_effect=verifications):
            out = loop.run_repair_loop(_problem(), start, R2ProtectedRepair(), _ctx(), llm, None, max_steps=6)

        first, second = out["history"][1], out["history"][2]
        self.assertFalse(first["accepted"])
        record = RepairAttemptRecord.from_dict(first["repair_attempt"])
        self.assertEqual(record.repair_strategy, "R2")
        self.assertEqual(record.decision_reason, "previously_satisfied_constraint_regressed")
        self.assertEqual(record.protected_constraint_indices, [2])
        self.assertEqual(record.accepted_plan_after, start)
        self.assertEqual(first["metadata"]["rolled_back_constraint_indices"], [2])

        # The second prompt repairs the rolled-back plan and names what broke.
        self.assertIn(json.dumps(start), llm.prompts[1])
        self.assertNotIn("rolled back", llm.prompts[0])
        self.assertIn("broke personal constraint 2", llm.prompts[1])
        self.assertIn(CONSTRAINTS[1], llm.prompts[1])

        self.assertTrue(second["accepted"])
        self.assertIsNone(RepairAttemptRecord.from_dict(second["repair_attempt"]).decision_reason)
        self.assertEqual(out["raw_plan"], fixed)
        self.assertTrue(out["verification"]["passed"])

    def test_case3_unfixed_target_without_regression_is_kept(self):
        start, other = _plan("start"), _plan("other")
        verifications = [_state([False, True]), _state([False, True])]
        with patch.object(loop, "verify_plan", side_effect=verifications):
            out = loop.run_repair_loop(_problem(), start, R2ProtectedRepair(), _ctx(),
                                       _SequenceLLM([_continuation(other)]), None, max_steps=1)
        self.assertTrue(out["history"][1]["accepted"])
        self.assertEqual(out["raw_plan"], other)

    def test_case4_unusable_reply_keeps_current_plan(self):
        start = _plan("start")
        two_days = _plan("x") + [{"day": 2, "activities": [{"type": "attraction"}]}]
        for reply in ("not json at all", _continuation(two_days), ' "activities": []}]'):
            with self.subTest(reply=reply[:20]):
                verifications = [_state([False, True]), _state([False, True])]
                with patch.object(loop, "verify_plan", side_effect=verifications):
                    out = loop.run_repair_loop(_problem(), start, R2ProtectedRepair(), _ctx(),
                                               _SequenceLLM([reply]), None, max_steps=1)
                attempt = out["history"][1]
                record = RepairAttemptRecord.from_dict(attempt["repair_attempt"])
                self.assertIsNone(record.exception)
                self.assertEqual(record.repair_strategy, "R2")
                self.assertEqual(record.target_constraint_indices, [1])
                self.assertEqual(record.protected_constraint_indices, [2])
                self.assertEqual(attempt["metadata"]["failure_reason"], "no_valid_repair_candidate")
                self.assertEqual(out["raw_plan"], start)

    def test_r0_still_raises_on_unparsable_reply(self):
        from chinatravel.agent.nesy_verifier.repair_strategies.r0 import R0WholePlanRepair
        with patch.object(loop, "verify_plan", side_effect=[_state([False, True])]):
            with self.assertRaises(Exception):
                loop.run_repair_loop(_problem(), _plan("start"), R0WholePlanRepair(), _ctx(),
                                     _SequenceLLM(["not json at all"]), None, max_steps=1)


if __name__ == "__main__":
    unittest.main()
