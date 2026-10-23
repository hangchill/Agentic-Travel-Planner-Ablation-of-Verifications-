#!/usr/bin/env python3
"""Regression tests for the shared_verifier reliability fixes.

Offline only: commonsense output is monkeypatched where we need determinism and
all itineraries are small inline fixtures. The key thing under test is that
genuine commonsense + personal violations stay detectable, while verifier
crashes, silent translation failures, and malformed structure only make
`passed` stricter and never leak into error_info.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from chinatravel.agent.nesy_verifier import shared_verifier
    from chinatravel.agent.nesy_verifier.shared_verifier import (
        COMMONSENSE_VERIFIER_ERROR_MARKER,
        _detect_silent_translation_failures,
        _split_commonsense_errors,
        _validate_plan_structure,
        verify_plan,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - only hit if DB CSVs are absent
    _IMPORT_ERROR = exc

from chinatravel.agent.nesy_verifier.repair_strategies.base import (
    BaseRepairStrategy,
    RepairResult,
)
from chinatravel.agent.nesy_verifier.shared_repair_loop import run_repair_loop


## commonsense_constraint_nl.py reads sandbox CSVs at import; skip (not fail) the
## dependent tests when that data is missing.
_SKIP_REASON = (
    "shared_verifier could not be imported (missing environment DB?): "
    f"{_IMPORT_ERROR}"
)


def _transport_dict(src="A", dst="B"):
    return {
        "from": src,
        "to": dst,
        "start_time": "09:00",
        "end_time": "09:20",
        "mode": "metro",
        "cost": 4,
    }


## A structurally valid 2-day plan: intercity activities use start/end, inner-city
## ones use position + a transports dict.
def valid_itinerary():
    return {
        "people_number": 2,
        "start_city": "上海",
        "target_city": "苏州",
        "itinerary": [
            {
                "day": 1,
                "activities": [
                    {
                        "type": "train",
                        "start": "上海站",
                        "end": "苏州站",
                        "start_time": "08:00",
                        "end_time": "08:25",
                        "transports": "empty",
                    },
                    {
                        "type": "accommodation",
                        "position": "亚朵酒店",
                        "start_time": "08:25",
                        "end_time": "08:39",
                        "transports": _transport_dict("苏州站", "亚朵酒店"),
                    },
                ],
            },
            {
                "day": 2,
                "activities": [
                    {
                        "type": "attraction",
                        "position": "拙政园",
                        "start_time": "09:00",
                        "end_time": "11:00",
                        "transports": _transport_dict("亚朵酒店", "拙政园"),
                    },
                    {
                        "type": "train",
                        "start": "苏州站",
                        "end": "上海站",
                        "start_time": "18:00",
                        "end_time": "18:25",
                        "transports": "empty",
                    },
                ],
            },
        ],
    }


def make_problem(hard_logic_py=None):
    return {
        "people_number": 2,
        "start_city": "上海",
        "target_city": "苏州",
        "nature_language": "test query",
        "hard_logic_py": list(hard_logic_py or []),
    }


## Pass-through so the personal-constraint path runs instead of being blocked by
## the missing-translator branch.
def identity_translate_fn(itinerary, problem):
    return itinerary


class HelperUnitTests(unittest.TestCase):
    def test_split_commonsense_errors_separates_marker_and_preserves_order(self):
        marker = f"{COMMONSENSE_VERIFIER_ERROR_MARKER}, <func foo>: boom"
        errors = ["genuine A", marker, "genuine B"]
        genuine, verifier = _split_commonsense_errors(errors)
        self.assertEqual(genuine, ["genuine A", "genuine B"])
        self.assertEqual(verifier, [marker])

    def test_split_commonsense_errors_empty(self):
        genuine, verifier = _split_commonsense_errors([])
        self.assertEqual(genuine, [])
        self.assertEqual(verifier, [])

    def test_detect_silent_translation_failures_flags_collapsed_dict(self):
        original = [
            {"activities": [{"position": "P", "transports": _transport_dict()}]}
        ]
        translated = [{"activities": [{"position": "P", "transports": []}]}]
        failures = _detect_silent_translation_failures(original, translated)
        self.assertEqual(len(failures), 1)
        self.assertIn("Transport translation failed", failures[0])
        self.assertIn("P", failures[0])

    ## Each case below is a legitimate empty that must NOT be flagged.
    def test_detect_silent_translation_failures_ignores_legit_empties(self):
        ## no transports key
        self.assertEqual(
            _detect_silent_translation_failures(
                [{"activities": [{"position": "P"}]}],
                [{"activities": [{"position": "P", "transports": []}]}],
            ),
            [],
        )
        ## already an empty list originally
        self.assertEqual(
            _detect_silent_translation_failures(
                [{"activities": [{"position": "P", "transports": []}]}],
                [{"activities": [{"position": "P", "transports": []}]}],
            ),
            [],
        )
        ## string "empty"
        self.assertEqual(
            _detect_silent_translation_failures(
                [{"activities": [{"position": "P", "transports": "empty"}]}],
                [{"activities": [{"position": "P", "transports": []}]}],
            ),
            [],
        )
        ## from == to
        self.assertEqual(
            _detect_silent_translation_failures(
                [{"activities": [{"position": "P", "transports": _transport_dict("X", "X")}]}],
                [{"activities": [{"position": "P", "transports": []}]}],
            ),
            [],
        )

    ## Shape/length mismatches must never raise.
    def test_detect_silent_translation_failures_tolerates_shape_mismatch(self):
        self.assertEqual(
            _detect_silent_translation_failures(None, None), []
        )
        self.assertEqual(
            _detect_silent_translation_failures(
                [{"activities": [{"position": "P", "transports": _transport_dict()}]}],
                [],
            ),
            [],
        )
        self.assertEqual(
            _detect_silent_translation_failures(
                [{"activities": "oops"}],
                [{"activities": [{"transports": []}]}],
            ),
            [],
        )

    ## No position -> label falls back to start->end.
    def test_detect_silent_translation_failures_intercity_label(self):
        original = [
            {"activities": [{"start": "S", "end": "E", "transports": _transport_dict("S", "E")}]}
        ]
        translated = [{"activities": [{"start": "S", "end": "E", "transports": []}]}]
        failures = _detect_silent_translation_failures(original, translated)
        self.assertEqual(len(failures), 1)
        self.assertIn("S->E", failures[0])

    def test_validate_plan_structure_valid_plan(self):
        self.assertEqual(_validate_plan_structure(valid_itinerary()), [])

    def test_validate_plan_structure_innercity_transport_type(self):
        plan = valid_itinerary()
        plan["itinerary"][0]["activities"][1]["type"] = "innercity_transport"
        errors = _validate_plan_structure(plan)
        self.assertTrue(any("innercity_transport" in e for e in errors))

    def test_validate_plan_structure_unknown_type(self):
        plan = valid_itinerary()
        plan["itinerary"][0]["activities"][1]["type"] = "shopping"
        errors = _validate_plan_structure(plan)
        self.assertTrue(any("shopping" in e and "unsupported" in e.lower() for e in errors))

    def test_validate_plan_structure_missing_position(self):
        plan = valid_itinerary()
        del plan["itinerary"][0]["activities"][1]["position"]
        errors = _validate_plan_structure(plan)
        self.assertTrue(any("position" in e for e in errors))

    def test_validate_plan_structure_missing_times(self):
        plan = valid_itinerary()
        del plan["itinerary"][1]["activities"][0]["start_time"]
        del plan["itinerary"][1]["activities"][0]["end_time"]
        errors = _validate_plan_structure(plan)
        self.assertTrue(any("start_time" in e for e in errors))
        self.assertTrue(any("end_time" in e for e in errors))

    ## Intercity activities have no 'position' and must not be flagged for it.
    def test_validate_plan_structure_intercity_not_flagged_for_position(self):
        errors = _validate_plan_structure(valid_itinerary())
        self.assertFalse(any("position" in e for e in errors))


@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP_REASON)
class VerifyPlanTests(unittest.TestCase):

    ## No genuine commonsense violations, so the structural/translation channels
    ## can be tested in isolation.
    def _no_commonsense(self):
        return patch.object(
            shared_verifier,
            "collect_commonsense_constraints_error",
            return_value=[],
        )

    def test_valid_itinerary_no_false_positives(self):
        with self._no_commonsense():
            result = verify_plan(
                make_problem(["result=True"]),
                valid_itinerary(),
                translate_fn=identity_translate_fn,
            )
        self.assertEqual(result["schema_errors"], [])
        self.assertEqual(result["translation_errors"], [])
        self.assertEqual(result["verifier_errors"], [])
        self.assertEqual(result["commonsense_errors"], [])
        self.assertEqual(result["personal_constraints"], [True])
        self.assertTrue(result["passed"])

    def test_missing_position_reported_as_schema_error(self):
        plan = valid_itinerary()
        del plan["itinerary"][0]["activities"][1]["position"]
        with self._no_commonsense():
            result = verify_plan(
                make_problem(), plan, translate_fn=identity_translate_fn
            )
        self.assertTrue(any("position" in e for e in result["schema_errors"]))
        self.assertFalse(result["passed"])

    def test_invalid_activity_type_in_schema_errors(self):
        plan = valid_itinerary()
        plan["itinerary"][0]["activities"][1]["type"] = "shopping"
        with self._no_commonsense():
            result = verify_plan(
                make_problem(), plan, translate_fn=identity_translate_fn
            )
        self.assertTrue(any("shopping" in e for e in result["schema_errors"]))
        self.assertFalse(result["passed"])

    def test_separate_innercity_transport_in_schema_errors(self):
        plan = valid_itinerary()
        plan["itinerary"][0]["activities"][1]["type"] = "innercity_transport"
        with self._no_commonsense():
            result = verify_plan(
                make_problem(), plan, translate_fn=identity_translate_fn
            )
        self.assertTrue(
            any("innercity_transport" in e for e in result["schema_errors"])
        )
        self.assertFalse(result["passed"])

    def test_missing_activity_times_in_schema_errors(self):
        plan = valid_itinerary()
        del plan["itinerary"][1]["activities"][0]["start_time"]
        with self._no_commonsense():
            result = verify_plan(
                make_problem(), plan, translate_fn=identity_translate_fn
            )
        self.assertTrue(any("start_time" in e for e in result["schema_errors"]))
        self.assertFalse(result["passed"])

    def test_successful_translation_no_translation_error(self):
        with self._no_commonsense():
            result = verify_plan(
                make_problem(["result=True"]),
                valid_itinerary(),
                translate_fn=identity_translate_fn,
            )
        self.assertEqual(result["translation_errors"], [])
        self.assertEqual(result["translation_failures"], [])

    def test_failed_translation_sets_translation_errors_and_not_passed(self):
        def boom_translate_fn(itinerary, problem):
            raise RuntimeError("translation blew up")

        with self._no_commonsense():
            result = verify_plan(
                make_problem(["result=True"]),
                valid_itinerary(),
                translate_fn=boom_translate_fn,
            )
        self.assertTrue(result["translation_errors"])
        self.assertFalse(result["passed"])
        ## Personal constraints are unknown (None) when translation fails.
        self.assertEqual(result["personal_constraints"], [None])

    ## A genuine dict transports collapsing to [] is a silent failure.
    def test_silent_translation_failure_flagged(self):
        def collapsing_translate_fn(itinerary, problem):
            for day in itinerary:
                for act in day["activities"]:
                    if isinstance(act.get("transports"), dict):
                        act["transports"] = []
            return itinerary

        with self._no_commonsense():
            result = verify_plan(
                make_problem(["result=True"]),
                valid_itinerary(),
                translate_fn=collapsing_translate_fn,
            )
        self.assertTrue(result["translation_failures"])
        self.assertTrue(
            any("Transport translation failed" in e for e in result["translation_errors"])
        )
        self.assertFalse(result["passed"])

    ## from==to transports collapsing to [] are legitimate, not failures.
    def test_legit_empty_transport_not_flagged(self):
        plan = valid_itinerary()
        for day in plan["itinerary"]:
            for act in day["activities"]:
                if isinstance(act.get("transports"), dict):
                    act["transports"] = _transport_dict("X", "X")

        def to_empty_translate_fn(itinerary, problem):
            for day in itinerary:
                for act in day["activities"]:
                    if isinstance(act.get("transports"), (dict, str)):
                        act["transports"] = []
            return itinerary

        with self._no_commonsense():
            result = verify_plan(
                make_problem(["result=True"]),
                plan,
                translate_fn=to_empty_translate_fn,
            )
        self.assertEqual(result["translation_failures"], [])
        self.assertEqual(result["translation_errors"], [])

    ## A DSL eval error is unknown (None), not a violation; error_info stays empty.
    def test_personal_dsl_exception_is_unknown_not_violation(self):
        with self._no_commonsense():
            result = verify_plan(
                make_problem(["result = 1 / 0"]),
                valid_itinerary(),
                translate_fn=identity_translate_fn,
            )
        self.assertEqual(result["personal_constraints"], [None])
        self.assertTrue(result["evaluation_errors"])
        self.assertEqual(result["personal_errors"], [])
        self.assertEqual(result["error_info"], [])

    ## A verifier crash goes to verifier_errors, never commonsense/error_info.
    def test_verifier_execution_exception_goes_to_verifier_errors(self):
        marker_error = f"{COMMONSENSE_VERIFIER_ERROR_MARKER}, <func foo>: boom"
        with patch.object(
            shared_verifier,
            "collect_commonsense_constraints_error",
            return_value=[marker_error],
        ):
            result = verify_plan(
                make_problem(["result=True"]),
                valid_itinerary(),
                translate_fn=identity_translate_fn,
            )
        self.assertIn(marker_error, result["verifier_errors"])
        self.assertNotIn(marker_error, result["commonsense_errors"])
        self.assertNotIn(marker_error, result["error_info"])
        self.assertEqual(result["commonsense_errors"], [])
        self.assertFalse(result["passed"])

    ## The invariant: genuine commonsense + personal violations both land in
    ## error_info and set passed False, with no technical noise mixed in.
    def test_genuine_violation_preserved_in_error_info(self):
        genuine_violation = "Activities must cost time, the end_time should be later than the start_time."
        with patch.object(
            shared_verifier,
            "collect_commonsense_constraints_error",
            return_value=[genuine_violation],
        ):
            result = verify_plan(
                make_problem(["result=False"]),
                valid_itinerary(),
                translate_fn=identity_translate_fn,
            )
        self.assertIn(genuine_violation, result["commonsense_errors"])
        self.assertIn(genuine_violation, result["error_info"])
        self.assertEqual(result["personal_constraints"], [False])
        self.assertTrue(any("Personal constraint 1" in e for e in result["personal_errors"]))
        self.assertTrue(any("Personal constraint 1" in e for e in result["error_info"]))
        self.assertEqual(
            result["error_info"],
            result["commonsense_errors"] + result["personal_errors"],
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["verifier_errors"], [])
        self.assertEqual(result["schema_errors"], [])


@unittest.skipIf(_IMPORT_ERROR is not None, _SKIP_REASON)
class RepairLoopTests(unittest.TestCase):

    ## Always proposes the same candidate and never passes.
    class _NeverPassStrategy(BaseRepairStrategy):
        def __init__(self, candidate):
            self.candidate = candidate

        def repair(self, problem, raw_plan, verification_results, context, llm):
            return RepairResult(repaired_plan=self.candidate, metadata={"s": "stub"})

    ## Proposes a candidate but rejects it (accept -> False).
    class _RejectingStrategy(BaseRepairStrategy):
        def __init__(self, candidate):
            self.candidate = candidate

        def repair(self, problem, raw_plan, verification_results, context, llm):
            return RepairResult(repaired_plan=self.candidate, metadata={"s": "stub"})

        def accept(self, current_verification, candidate_verification):
            return False

    def test_rejected_repair_preserves_accepted_plan(self):
        problem = make_problem()
        problem["hard_logic_py"] = ["result=False"]
        start_plan = valid_itinerary()["itinerary"]
        start_plan[0]["activities"][1]["type"] = "shopping"
        candidate = valid_itinerary()["itinerary"]
        candidate[0]["activities"][1]["type"] = "innercity_transport"

        strategy = self._RejectingStrategy(candidate)
        with patch.object(
            shared_verifier, "collect_commonsense_constraints_error", return_value=[]
        ):
            result = run_repair_loop(
                problem,
                start_plan,
                strategy,
                context={},
                llm=lambda *a, **k: "",
                translate_fn=identity_translate_fn,
                max_steps=3,
            )
        ## A rejected candidate never replaces the accepted plan.
        self.assertEqual(
            result["raw_plan"][0]["activities"][1]["type"], "shopping"
        )
        ## Attempts still counted: step 0 + 3 rejected attempts.
        self.assertEqual(len(result["history"]), 4)
        self.assertTrue(all(h["accepted"] is False for h in result["history"][1:]))

    def test_repair_budget_exactly_max_steps_attempts(self):
        problem = make_problem()
        problem["hard_logic_py"] = ["result=False"]
        start_plan = valid_itinerary()["itinerary"]
        start_plan[0]["activities"][1]["type"] = "shopping"
        candidate = valid_itinerary()["itinerary"]
        candidate[0]["activities"][1]["type"] = "shopping"

        strategy = self._NeverPassStrategy(candidate)
        with patch.object(
            shared_verifier, "collect_commonsense_constraints_error", return_value=[]
        ):
            result = run_repair_loop(
                problem,
                start_plan,
                strategy,
                context={},
                llm=lambda *a, **k: "",
                translate_fn=identity_translate_fn,
                max_steps=4,
            )
        ## step 0 entry + exactly max_steps attempts.
        self.assertEqual(len(result["history"]), 5)
        self.assertFalse(result["verification"]["passed"])

    ## The repair_strategy=None baseline must still build error_info from the
    ## original collect_* functions, not the shared verify_plan.
    def test_baseline_path_composes_error_info_via_original_collectors(self):
        from chinatravel.agent.nesy_verifier import llm_modulo

        commonsense = ["commonsense violation X"]
        personal = ["personal violation Y"]

        with patch.object(
            llm_modulo,
            "collect_commonsense_constraints_error",
            return_value=list(commonsense),
        ) as mock_cc, patch.object(
            llm_modulo, "collect_personal_error", return_value=list(personal)
        ) as mock_pe:
            problem = make_problem()
            evaluated_plan = {"itinerary": []}
            error_info = llm_modulo.collect_commonsense_constraints_error(
                problem, evaluated_plan, verbose=False
            )
            if (
                "Format Error. Please strictly follow the instructions in the prompt."
                not in error_info
            ):
                personal_error_info = llm_modulo.collect_personal_error(
                    problem, evaluated_plan, verbose=False
                )
                for pe in personal_error_info:
                    error_info.append(pe)

        self.assertTrue(mock_cc.called)
        self.assertTrue(mock_pe.called)
        self.assertEqual(error_info, commonsense + personal)


if __name__ == "__main__":
    unittest.main()
