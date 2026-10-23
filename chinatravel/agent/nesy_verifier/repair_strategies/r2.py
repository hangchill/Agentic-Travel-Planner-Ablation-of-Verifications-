"""R2: whole-plan repair that keeps usable candidates and records regressions."""

import json
import re
import time
from copy import deepcopy
from typing import Any

from chinatravel.json_utils import repair_json
from chinatravel.symbol_verification.concept_func import func_dict
from chinatravel.symbol_verification.dsl import execute_dsl_code
from chinatravel.symbol_verification.hard_constraint import (
    _normalize_legacy_hard_logic_py,
)
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


def _format_value(value: Any) -> str | None:
    """Render a scalar or a flat collection of scalars; skip anything else."""
    scalar = (str, int, float, bool)
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, scalar):
        return repr(value)
    if isinstance(value, (set, frozenset, list, tuple)) and all(isinstance(v, scalar) for v in value):
        items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else list(value)
        text = repr(items) if not isinstance(value, (set, frozenset)) else "{" + ", ".join(map(repr, items)) + "}"
        return text if len(text) <= 300 else text[:297] + "..."
    return None


def _evaluated_values(problem: dict, verification_results: dict, index: int) -> str | None:
    """Re-run one personal constraint on the verified plan and report its values.

    The verifier keeps only the final boolean, so the model sees DSL code but
    not what it computed (e.g. the plan's total cost). This repeats the shared
    verifier's evaluation read-only and lists the scalar variables the snippet
    bound. Returns None when the values cannot be computed.
    """
    try:
        plan =verification_results.get("translated_plan")
        constraint = (problem.get("hard_logic_py") or [])[index - 1]
        if not isinstance(plan, dict):
            return None
        variables = deepcopy(func_dict)
        variables["plan"] = deepcopy(plan)
        execute_dsl_code(
            _normalize_legacy_hard_logic_py(constraint),
            variables,
            allowed_builtins={"set": set},
        )
    except Exception:
        return None
    shown = []
    for name, value in variables.items():
        if name in func_dict or name == "plan":
            continue
        text = _format_value(value)
        if text is not None:
            shown.append(f"{name} = {text}")
    return ", ".join(shown) or None


def _collect_target_feedback(
    problem: dict, verification_results: dict, targets: list[int]
) -> list[str]:
    """Select error messages for all failed constraints being targeted.

    The verifier prefixes each personal-constraint error with its 1-based
    constraint number; matching those prefixes avoids mixing in unrelated
    commonsense errors or other feedback. Each message is followed by the
    values the constraint evaluated to on the current plan, when available.
    """
    errors = verification_results.get("error_info", [])
    feedback = []
    for target in targets:
        prefix = f"Personal constraint {target} failed:"
        messages = [m for m in errors if isinstance(m, str) and m.startswith(prefix)]
        if not messages:
            continue
        feedback.extend(messages)
        values = _evaluated_values(problem, verification_results, target)
        if values:
            feedback.append(f"Values computed for constraint {target} on the current plan: {values}")
    return feedback


def _collect_unknown_feedback(problem: dict, verification_results: dict) -> list[str]:
    """Explain why personal constraints could not be evaluated.

    A candidate the verifier cannot translate (e.g. an impossible metro leg)
    turns every personal result into None. Without this feedback R2 has no
    target and would spend the remaining personal steps as no-ops.
    """
    states = verification_results.get("personal_constraints", [])
    constraints = problem.get("hard_logic_py") or []
    unknown = [
        f"Personal constraint {index} is UNKNOWN; repair the plan so it can be evaluated: "
        f"{constraints[index - 1]}"
        for index, state in enumerate(states, 1)
        if state is None and index <= len(constraints)
    ]
    if not unknown:
        return []
    technical = [
        message
        for key in ("translation_errors", "schema_errors", "verifier_errors")
        for message in verification_results.get(key) or []
        if isinstance(message, str)
    ]
    hint = (
        "Every innercity transport must be a route that exists in the provided "
        "innercity transport data (use walk or taxi when no metro route exists)."
    )
    return technical + [hint] + unknown


def _collect_commonsense_feedback(verification_results: dict) -> list[str]:
    """Return the verifier's commonsense errors for the commonsense phase.

    The shared loop schedules one commonsense attempt; R2 then rewrites the
    plan against those errors instead of its personal-constraint targets.
    """
    errors = verification_results.get("commonsense_errors") or []
    return [message for message in errors if isinstance(message, str)]


def _frame_feedback(
    problem: dict, feedback: list[str], protected: list[int]
) -> list[str]:
    """Wrap target feedback with an explicit change request and keep-list.

    Raw DSL failures alone often lead the model to echo the plan unchanged,
    so the prompt states that the plan must change and names the currently
    satisfied constraints the rewrite should keep satisfied.
    """
    framed = [
        "The current travel plan VIOLATES the following requirement(s). "
        "Returning the same plan is not acceptable; change whatever parts of "
        "the plan are needed (e.g. cheaper transport, hotels or restaurants, "
        "different attractions or times) so that every listed requirement holds:",
        *feedback,
    ]
    constraints = problem.get("hard_logic_py") or []
    keep = [
        f"Personal constraint {index} (currently satisfied, keep it): {constraints[index - 1]}"
        for index in protected
        if 0 < index <= len(constraints)
    ]
    if keep:
        framed.append("While fixing these, keep the following satisfied:")
        framed.extend(keep)
    return framed


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


def _has_expected_days(candidate: list, problem: dict) -> bool:
    """Reject a rewrite whose day count differs from the requested trip length.

    A whole-plan reply cut off by the token limit can still parse into a
    shorter plan; it is not a usable rewrite. Queries without an integer
    ``days`` field are not checked.
    """
    days = problem.get("days")
    return not isinstance(days, int) or isinstance(days, bool) or len(candidate) == days


def _parse_candidate_response(response: str) -> tuple[list, str]:
    """Frame and parse the model response, then enforce the itinerary shape.

    The ChinaTravel prompt returns the content after the first day's opening
    fields, so this adds the expected prefix before repairing/parsing JSON.
    Returns both the parsed plan and framed text for attempt logging.
    """
    framed_response = "[{\"day\": 1," + response
    # Chat models often ignore the prefill and return a fenced full plan; the
    # fenced body is tried first, then the prefilled framing.
    texts = []
    fenced = re.search(r"```(?:json)?\s*(.*?)(?:```|$)", response, re.S)
    if fenced:
        texts.append(fenced.group(1))
    texts.append(framed_response)
    for text in texts:
        try:
            candidate = json.loads(repair_json(text))
        except Exception:
            continue
        if isinstance(candidate, dict):
            candidate = [candidate]
        if _is_usable_candidate(candidate):
            return candidate, framed_response
    raise ValueError("R2 response must contain itinerary days with usable activities")


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
        # In the commonsense phase the targets are the commonsense errors, so
        # no personal constraint is targeted.
        commonsense_phase = context.get("repair_phase") == "commonsense"
        targets = [] if commonsense_phase else _failed_personal_targets(verification_results)
        protected = _protected_personal_indices(verification_results)
        metadata = {
            "strategy": "R2",
            "target_constraint_indices": targets,
            "editable_scope": "plan",
            "protected_constraint_indices": protected,
        }

        # Stage 2-3: gather the feedback for this phase. With no known failures
        # or no messages, R2 cannot tell the model what to fix, so the current
        # plan is returned unchanged (case 4).
        if commonsense_phase:
            feedback = _collect_commonsense_feedback(verification_results)
        else:
            feedback = _collect_target_feedback(problem, verification_results, targets) if targets else []
            feedback += _collect_unknown_feedback(problem, verification_results)
        if not feedback:
            metadata["failure_reason"] = "no_valid_repair_candidate"
            result = RepairResult(deepcopy(raw_plan), metadata)
            self._last_result = result
            return result # return original itinerary, with metadata explaining that no valid repair generated

        # Stage 4: prepare a whole-plan prompt using current itinerary and all
        # target feedback in one request.
        query_message = _build_plan_prompt(
            problem, raw_plan, context, _frame_feedback(problem, feedback, protected)
        )

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
            if not _has_expected_days(candidate, problem):
                raise ValueError(
                    f"R2 candidate has {len(candidate)} days; the query asks for {problem.get('days')}"
                )
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
            "feedback_personal_constraint_indices": targets.copy(),
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
