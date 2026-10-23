"""R2: whole-plan repair that keeps usable candidates and records regressions."""

import json
import time
from copy import deepcopy
from typing import Any

from chinatravel.json_utils import repair_json
from chinatravel.agent.nesy_verifier.prompts.llm_modulo import BACK_PROMPT
from chinatravel.agent.nesy_verifier.repair_strategies.base import (
    BaseRepairStrategy,
    RepairResult,
)


# ---- Small helpers used by the R2 repair flow ----
# These functions keep target discovery, prompt creation, parsing, and
# regression detection separate from the strategy's orchestration method.

def _failed_personal_targets(verification_results: dict) -> list[int]:
    """Return 1-based indices for personal constraints with an exact FAIL state.

    UNKNOWN (None) constraints are excluded: R2 only targets constraints the
    verifier has positively identified as failed.
    """
    states = verification_results.get("personal_constraints", [])
    return [index for index, state in enumerate(states, 1) if state is False]


def _protected_personal_indices(verification_results: dict) -> list[int]:
    """Return 1-based indices for constraints currently passing verification.

    R2 records these as protected so the shared loop can report if its
    whole-plan rewrite later makes one fail. They do not veto the proposal.
    """
    states = verification_results.get("personal_constraints", [])
    return [index for index, state in enumerate(states, 1) if state is True]


def _collect_target_feedback(verification_results: dict, targets: list[int]) -> list[str]:
    """Select error messages for all failed constraints being targeted.

    The verifier prefixes each personal-constraint error with its 1-based
    constraint number; matching those prefixes avoids mixing in unrelated
    commonsense errors or other feedback.
    """
    errors = verification_results.get("error_info", [])
    return [
        message for message in errors
        if isinstance(message, str) and any(
            message.startswith(f"Personal constraint {target} failed:")
            for target in targets
        )
    ]


def _build_plan_prompt(
    problem: dict, raw_plan: list, context: dict, feedback: list[str]
) -> str:
    """Fill the existing ChinaTravel prompt with plan, request, and feedback.

    R2 passes the full current plan and all target feedback because it asks
    the model for a complete revised itinerary rather than a local edit.
    """
    return BACK_PROMPT.format(
        go_train_info=context["go_train_info"],
        go_flight_info=context["go_flight_info"],
        back_train_info=context["back_train_info"],
        back_flight_info=context["back_flight_info"],
        attraction_info=context["attraction_info"],
        restaurant_info=context["restaurant_info"],
        accommodation_info=context["accommodation_info"],
        innercity_transport_info=context["innercity_transport_info"],
        query=problem["nature_language"],
        plan=json.dumps(raw_plan, ensure_ascii=False),
        backprompt="\n".join(feedback),
    )


def _is_usable_candidate(candidate: Any) -> bool:
    """Reject parsed JSON that cannot be treated as a usable itinerary.

    A candidate needs at least one day, every day must have an activities
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


def _parse_candidate_response(response: str) -> tuple[list, str]:
    """Frame and parse the model response, then enforce the itinerary shape.

    The ChinaTravel prompt returns the content after the first day's opening
    fields, so this adds the expected prefix before repairing/parsing JSON.
    Returns both the parsed plan and framed text for attempt logging.
    """
    framed_response = "[{\"day\": 1," + response
    candidate = json.loads(repair_json(framed_response))
    if not _is_usable_candidate(candidate):
        raise ValueError("R2 response must contain itinerary days with usable activities")
    return candidate, framed_response


def _has_protected_regression(current_verification: dict, candidate_verification: dict) -> bool:
    """Detect a True-to-False transition in the personal constraint results.

    If vector lengths differ, there is no reliable index-by-index comparison,
    so this helper does not claim a regression. The proposal is still kept.
    """
    before = current_verification.get("personal_constraints", [])
    after = candidate_verification.get("personal_constraints", [])
    if len(before) != len(after):
        return False
    return any(old is True and new is False for old, new in zip(before, after))


class R2ProtectedRepair(BaseRepairStrategy):
    """Generate full-plan candidates from all failures and keep usable ones.

    The historical class name remains for compatibility. In the current R2
    policy, passing constraints are tracked for regression metadata, not used
    to roll a candidate back.
    """

    def __init__(self):
        # accept() runs after repair() and needs to attach its decision reason
        # to the exact result generated by that repair attempt.
        self._last_result: RepairResult | None = None

    def repair(
        self,
        problem: dict,
        raw_plan: list, # current itinerary plan that needs repair
        verification_results: dict,
        context: dict,
        llm: Any,
    ) -> RepairResult:
        # Stage 1: define this attempt's targets and audit metadata. Indices
        # stay 1-based to match the verifier's constraint numbering.
        targets = _failed_personal_targets(verification_results)
        protected = _protected_personal_indices(verification_results)
        metadata = {
            "strategy": "R2",
            "target_constraint_indices": targets,
            "editable_scope": "plan",
            "protected_constraint_indices": protected,
            "feedback_personal_constraint_indices": targets,
        }

        # Stage 2: if there are no known failures, no grounded proposal can be
        # requested. Return the current plan and explain why in the metadata.
        if not targets:
            metadata["failure_reason"] = "no_valid_repair_candidate"
            result = RepairResult(deepcopy(raw_plan), metadata)
            self._last_result = result
            return result # return original itinerary, with metadata explaining that no valid repair generated

        # Stage 3: gather every verifier message belonging to a target. Without
        # messages, R2 cannot tell the model what to fix, so this is a no-op.
        feedback = _collect_target_feedback(verification_results, targets)
        if not feedback:
            metadata["failure_reason"] = "no_valid_repair_candidate"
            result = RepairResult(deepcopy(raw_plan), metadata)
            self._last_result = result
            return result

        # Stage 4: prepare a whole-plan prompt using current itinerary and all
        # target feedback in one request.
        query_message = _build_plan_prompt(problem, raw_plan, context, feedback)

        # Stage 5: call the model, parse its response, and reject malformed
        # structures. Any failure here falls back to the unchanged plan.
        try:
            started = time.perf_counter()
            response = llm(
                [{"role": "user", "content": query_message}],
                one_line=False,
            )
            inference_time = time.perf_counter() - started
            candidate, framed_response = _parse_candidate_response(response)
        except Exception as exc:
            metadata.update({
                "failure_reason": "no_valid_repair_candidate",
                "candidate_error": f"{type(exc).__name__}: {exc}",
            })
            result = RepairResult(deepcopy(raw_plan), metadata)
            self._last_result = result
            return result

        # Stage 6: retain prompt/response diagnostics and return the usable
        # candidate. Constraint success is assessed by the shared loop later.
        metadata.update({
            "prompt": query_message,
            "raw_response": framed_response,
            "llm_inference_time": inference_time,
        })
        result = RepairResult(candidate, metadata)
        self._last_result = result
        return result

    def accept(
        self,
        current_verification: dict,
        candidate_verification: dict,
    ) -> bool:
        """Keep the proposal and record whether it regressed a passing check.

        The shared loop calls this after verifying the candidate. Returning
        True means the shared loop makes that candidate the next current plan.
        """
        regressed = _has_protected_regression(current_verification, candidate_verification)
        # R2 is a whole-plan rewrite policy: even a regression is returned so
        # later repair steps can work from the latest candidate.
        return self._record_decision(True, regressed=regressed)

    def _record_decision(self, accepted: bool, *, regressed: bool = False) -> bool:
        """Attach the acceptance diagnostic to the most recent repair result."""
        if self._last_result is not None:
            # Only regressions get a reason string. Removing a stale value
            # keeps metadata correct if a strategy instance is reused.
            if regressed:
                self._last_result.metadata["decision_reason"] = (
                    "previously_satisfied_constraint_regressed"
                )
            else:
                self._last_result.metadata.pop("decision_reason", None)
        return accepted
