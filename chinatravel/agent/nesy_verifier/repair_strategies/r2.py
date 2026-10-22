"""R2: whole-plan repair with rollback protection for satisfied constraints."""

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


class R2ProtectedRepair(BaseRepairStrategy):
    """Generate a plan-level candidate; reject candidates regressing a pass."""

    def __init__(self): #stores the most recent RepairResult
        self._last_result: RepairResult | None = None # initially no repair result generated

    def repair(
        self,
        problem: dict,
        raw_plan: list, # current itinerary plan that needs repair
        verification_results: dict,
        context: dict,
        llm: Any,
    ) -> RepairResult:
        # identify failed and satisfied constraints
        states = verification_results.get("personal_constraints", [])
        targets = [i for i, state in enumerate(states, 1) if state is False] # failed
        protected = [i for i, state in enumerate(states, 1) if state is True] # previously satisfied
        metadata = {
            "strategy": "R2",
            "target_constraint_indices": targets[:1], #R2 repairs one failed personal constraint at a time
            "editable_scope": "plan",
            "protected_constraint_indices": protected,
            "feedback_personal_constraint_indices": targets[:1],
        }

        # R2 repairs one clearly failed personal constraint at a time. If no
        # failed constraints exist, a plan candidate cannot be grounded in feedback.
        if not targets:
            metadata["failure_reason"] = "no_valid_repair_candidate"
            result = RepairResult(deepcopy(raw_plan), metadata)
            self._last_result = result
            return result # return original itinerary, with metadata explaining that no valid repair generated

        target = targets[0]
        all_errors = verification_results.get("error_info", [])
        target_prefix = f"Personal constraint {target} failed:"
        feedback = [
            message for message in all_errors
            if isinstance(message, str) and message.startswith(target_prefix)
        ]
        if not feedback: # doesn't repair without an error message
            metadata["failure_reason"] = "no_valid_repair_candidate"
            result = RepairResult(deepcopy(raw_plan), metadata)
            self._last_result = result
            return result

        query_message = BACK_PROMPT.format(
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

        try: #call LLM to generate candidate plan
            started = time.perf_counter()
            response = llm(
                [{"role": "user", "content": query_message}],
                one_line=False,
            )
            inference_time = time.perf_counter() - started
            # Preserve the response framing expected by the ChinaTravel prompt.
            framed_response = "[{\"day\": 1," + response
            candidate = json.loads(repair_json(framed_response))
            usable_days = ( # validate candidate's structure
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
            if not usable_days:
                raise ValueError("R2 response must contain itinerary days with usable activities")
        except Exception as exc: # handle LLM or parsing failures
            metadata.update({
                "failure_reason": "no_valid_repair_candidate",
                "candidate_error": f"{type(exc).__name__}: {exc}",
            })
            result = RepairResult(deepcopy(raw_plan), metadata)
            self._last_result = result
            return result

        metadata.update({ # return generated candidate
            "prompt": query_message,
            "raw_response": framed_response,
            "llm_inference_time": inference_time,
        })
        result = RepairResult(candidate, metadata)
        self._last_result = result
        return result

    def accept( #rollback protection
        self,
        current_verification: dict,
        candidate_verification: dict,
    ) -> bool:
        """Reject only when a previously passed personal constraint fails."""
        before = current_verification.get("personal_constraints", [])
        after = candidate_verification.get("personal_constraints", [])
        if len(before) != len(after): # check if both results have the same number of constraints
            return self._record_decision(False) # reject candidate if different length

        regressed = any(old is True and new is False for old, new in zip(before, after))
        # if any previously satisfied constraint is regressed, candidate is rejected.
        return self._record_decision(not regressed, regressed=regressed)

    def _record_decision(self, accepted: bool, *, regressed: bool = False) -> bool:
        # records the reason why a candidate was rejected
        # The shared loop normalizes result.metadata after calling accept(), so
        # this reliably records the policy decision alongside the candidate.
        if self._last_result is not None:
            if regressed:
                self._last_result.metadata["decision_reason"] = (
                    "previously_satisfied_constraint_regressed"
                )
            else:
                self._last_result.metadata.pop("decision_reason", None)
        return accepted
