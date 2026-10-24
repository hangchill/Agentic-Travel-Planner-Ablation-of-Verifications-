"""R2: R0 whole-plan regeneration with rollback on regressions."""

import time
from copy import deepcopy
from typing import Any

from chinatravel.agent.nesy_verifier.repair_strategies.base import RepairResult
from chinatravel.agent.nesy_verifier.repair_strategies.r0 import R0WholePlanRepair


def _is_usable_candidate(candidate: Any) -> bool:
    """A candidate needs at least one day, every day must have an activities
    list of activity objects, and at least one activity must exist overall.
    This is a structural check; the shared verifier checks the constraints.
    """
    return (
        isinstance(candidate, list)
        and bool(candidate)
        and all(
            isinstance(day, dict)
            and isinstance(day.get("activities"), list)
            and all(isinstance(activity, dict) for activity in day["activities"])
            for day in candidate
        )
        and any(day["activities"] for day in candidate)
    )


def _has_expected_days(candidate: list, problem: dict) -> bool:
    """Reject a rewrite whose day count differs from the requested trip length.

    A whole-plan reply cut off by the token limit can still parse into a
    shorter plan. Queries without an integer ``days`` field are not checked.
    """
    days = problem.get("days")
    return not isinstance(days, int) or isinstance(days, bool) or len(candidate) == days


def _passing_personal_indices(verification_results: dict) -> list[int]:
    """Return 1-based indices for personal constraints that currently pass."""
    states = verification_results.get("personal_constraints", [])
    return [index for index, state in enumerate(states, 1) if state is True]


def _regressed_personal_indices(current_verification: dict, candidate_verification: dict) -> list[int]:
    """Return 1-based indices that went from True (pass) to False (fail).

    UNKNOWN (None) results are not regressions, matching the shared loop's
    ``compare_constraint_results``. If the vector lengths differ there is no
    reliable index-by-index comparison, so no regression is claimed.
    """
    before = current_verification.get("personal_constraints", [])
    after = candidate_verification.get("personal_constraints", [])
    if len(before) != len(after):
        return []
    return [index for index, (old, new) in enumerate(zip(before, after), 1) if old is True and new is False]


## R2: Regenerate the entire itinerary exactly as R0 does, but reject any
## candidate that breaks a previously passing personal constraint. The shared
## loop then keeps the last accepted plan (rollback). Constraints broken by a
## rejected rewrite are remembered for the rest of the query and listed in
## every later repair prompt, so the LLM is told what it broke.
class R2ProtectedRepair(R0WholePlanRepair):

    def __init__(self):
        # accept() runs after repair() and attaches its decision to the exact
        # result produced by that attempt.
        self._last_result: RepairResult | None = None
        # 1-based constraint index -> number of rejected rewrites that broke it.
        # A new strategy instance is created per query, so this is per query.
        self._broken_constraints: dict[int, int] = {}

    def repair(
        self,
        problem,
        raw_plan,
        verification_results,
        context,
        llm,
    ) -> RepairResult:
        r2_metadata = {
            "strategy": "R2",
            "target_provenance": "r2_failed_feedback",
            "protected_constraint_indices": _passing_personal_indices(verification_results),
            "remembered_broken_constraint_indices": sorted(self._broken_constraints),
        }
        # R2 has no skip rule of its own: an exact repeat request is served by
        # the shared loop's per-query cache, the same for every strategy.
        # Case 4: R0 raises on an unparsable reply. R2 instead keeps the
        # current plan for this attempt, as does a candidate that is not a
        # usable itinerary of the requested length.
        started = time.perf_counter()
        try:
            result = super().repair(problem, raw_plan, verification_results, context, llm)
            candidate = result.repaired_plan
            if not _is_usable_candidate(candidate):
                raise ValueError("R2 response must contain itinerary days with usable activities")
            if not _has_expected_days(candidate, problem):
                raise ValueError(f"R2 candidate has {len(candidate)} days; the query asks for {problem.get('days')}")
        except Exception as exc:
            failed_indices, _ = self._build_feedback(problem, verification_results, context)
            result = RepairResult(deepcopy(raw_plan), {
                **r2_metadata,
                "target_constraint_indices": failed_indices,
                "editable_scope": "plan",
                "failure_reason": "no_valid_repair_candidate",
                "candidate_error": f"{type(exc).__name__}: {exc}",
                "llm_inference_time": time.perf_counter() - started,
            })
            self._last_result = result
            return result
        result.metadata.update(r2_metadata)
        self._last_result = result
        return result

    ## Add the remembered regressions to R0's feedback for this phase.
    def _build_feedback(self, problem, verification_results, context):
        failed_indices, feedback = super()._build_feedback(problem, verification_results, context)
        constraints = problem.get("hard_logic_py") or []
        notes = [
            f"A previous rewrite was rejected and rolled back because it broke personal constraint "
            f"{index} ({count} time(s)), which the current plan satisfies; keep it satisfied: "
            f"{constraints[index - 1]}"
            for index, count in sorted(self._broken_constraints.items())
            if 0 < index <= len(constraints)
        ]
        return failed_indices, list(feedback) + notes

    def accept(
        self,
        current_verification: dict,
        candidate_verification: dict,
    ) -> bool:
        regressed = _regressed_personal_indices(current_verification, candidate_verification)
        for index in regressed:
            self._broken_constraints[index] = self._broken_constraints.get(index, 0) + 1
        if self._last_result is not None:
            # Removing a stale value keeps metadata correct if a result is reused.
            if regressed:
                self._last_result.metadata["decision_reason"] = "previously_satisfied_constraint_regressed"
                self._last_result.metadata["rolled_back_constraint_indices"] = regressed
            else:
                if self._last_result.metadata.get("decision_reason") == "previously_satisfied_constraint_regressed":
                    self._last_result.metadata.pop("decision_reason")
                self._last_result.metadata.pop("rolled_back_constraint_indices", None)
        return not regressed
