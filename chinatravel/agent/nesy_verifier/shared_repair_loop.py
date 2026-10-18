
from copy import deepcopy
from time import perf_counter

from chinatravel.agent.system_usage import (system_snapshot, system_delta, verification_execution, measured_repair_pipeline)

from chinatravel.agent.model_usage import usage_snapshot, usage_delta

from chinatravel.evaluation.edit_footprint import compare_edit_footprint

from chinatravel.evaluation.repair_attempt import (
    RepairAttemptRecord, failed_constraint_indices, normalize_repair_intent_metadata,
)


def verify_plan(*args, **kwargs):
    # Defer database-backed imports so the loop can be tested with a mock verifier.
    from chinatravel.agent.nesy_verifier.shared_verifier import verify_plan as verifier

    return verifier(*args, **kwargs)


def _constraint_descriptors(problem):
    """Preserve query definitions without inferring labels or categories."""
    descriptions = problem.get("hard_logic_nl")
    descriptors = []
    for index, constraint in enumerate(problem.get("hard_logic_py", []), 1):
        descriptor = {"constraint_index": index, "hard_logic_py": deepcopy(constraint)}
        if isinstance(descriptions, list) and index <= len(descriptions):
            descriptor["hard_logic_nl"] = deepcopy(descriptions[index - 1])
        descriptors.append(descriptor)
    return descriptors



## Compare constraint results without treating evaluation errors as violations.
def compare_constraint_results(before, after):
    old_results = before["personal_constraints"]
    new_results = after["personal_constraints"]

    if len(old_results) != len(new_results):
        raise ValueError("Constraint result lengths do not match.")

    fixed = []
    newly_violated = []
    still_failed = []
    still_passed = []
    unknown = []

    for i, (old, new) in enumerate(
        zip(old_results, new_results), start=1
    ):
        if old is None or new is None:
            unknown.append(i)
        elif old is False and new is True:
            fixed.append(i)
        elif old is True and new is False:
            newly_violated.append(i)
        elif old is False and new is False:
            still_failed.append(i)
        else:
            still_passed.append(i)

    return {
        "fixed": fixed,
        "newly_violated": newly_violated,
        "still_failed": still_failed,
        "still_passed": still_passed,
        "unknown": unknown,
    }

## Run the same verification and repair process for R0-R4.
@measured_repair_pipeline
def run_repair_loop(
    problem,
    raw_plan,
    strategy,
    context,
    llm,
    translate_fn,
    max_steps=10,
    initial_verification=None,
    history_callback=None,
):

    ## Keep the current accepted itinerary separate from candidates.
    current_plan = deepcopy(raw_plan)

    initial_system_before = system_snapshot()
    ## Verify the initial itinerary.
    current_verification = deepcopy(initial_verification) if initial_verification is not None else verification_execution(verify_plan)(
        problem,
        {
            "people_number": problem["people_number"],
            "start_city": problem["start_city"],
            "target_city": problem["target_city"],
            "itinerary": current_plan,
        },
        translate_fn=translate_fn,
    )

    ## Store all repair attempts, including rejected proposals.
    history = [{
        "step": 0,
        "accepted": True,
        "verification": current_verification,
        "system_metrics": system_delta(initial_system_before, system_snapshot()),
    }]

    ## Each proposed repair uses one attempt from the budget.
    strategy_name = type(strategy).__name__
    for step in range(1, max_steps + 1):

        ## Stop if the current plan satisfies all reported checks.
        if current_verification["passed"]:
            break

        before_verification = deepcopy(current_verification)
        before_plan = deepcopy(current_plan)
        system_before = system_snapshot()
        usage_before = usage_snapshot(llm)
        repair_started = perf_counter()
        result = None
        failure = None
        repair_finished = verification_started = verification_finished = None
        usage_after_repair = usage_after_verification = None
        candidate_verification = None
        try:
            result = strategy.repair(
                problem=deepcopy(problem), raw_plan=deepcopy(current_plan),
                verification_results=deepcopy(current_verification), context=context, llm=llm,
            )
            repair_finished = perf_counter()
            usage_after_repair = usage_snapshot(llm)
            verification_started = perf_counter()
            candidate_verification = verification_execution(verify_plan)(
                problem,
                {"people_number": problem["people_number"], "start_city": problem["start_city"],
                 "target_city": problem["target_city"], "itinerary": deepcopy(result.repaired_plan)},
                translate_fn=translate_fn,
            )
            verification_finished = perf_counter()
            usage_after_verification = usage_snapshot(llm)
            accepted = strategy.accept(deepcopy(current_verification), deepcopy(candidate_verification))
        except Exception as exc:
            failure = exc
            accepted = False
        attempt_finished = perf_counter()
        usage_after = usage_snapshot(llm)
        if usage_after_repair is None:
            usage_after_repair = usage_after
        if usage_after_verification is None:
            usage_after_verification = usage_after
        if repair_finished is None:
            repair_finished = attempt_finished
        if candidate_verification is None:
            # An execution failure is unknown, never a fabricated violation.
            candidate_verification = {
                "personal_constraints": [None] * len(current_verification["personal_constraints"]),
                "passed": False, "verification_unavailable": True,
            }
        after_verification = deepcopy(candidate_verification)
        ## Compare constraint results before and after the proposed repair.
        ## Compare against the current accepted plan, not a rejected candidate.
        transitions = compare_constraint_results(
            before_verification,
            after_verification,
        )

        intent, debug_metadata = normalize_repair_intent_metadata(result.metadata if result is not None else {})
        strategy_name = intent.pop("repair_strategy", strategy_name)
        # Derivable context is authoritative, never supplied by a strategy.
        intent["concurrent_failed_constraint_indices"] = failed_constraint_indices(before_verification["personal_constraints"])
        commonsense = before_verification.get("commonsense_errors")
        intent["concurrent_commonsense_failure_count"] = len(commonsense) if isinstance(commonsense, list) else None
        intent.setdefault("target_constraint_indices", [])
        intent.setdefault("target_constraint_labels", [])
        record = RepairAttemptRecord(
            step=step,
            query_uid=problem.get("uid") if isinstance(problem.get("uid"), str) else None,
            constraint_descriptors=_constraint_descriptors(problem),
            repair_strategy=strategy_name,
            **intent,
            accepted=accepted,
            before_personal_constraints=before_verification["personal_constraints"],
            after_personal_constraints=after_verification["personal_constraints"],
            **transitions,
            candidate_plan=deepcopy(result.repaired_plan) if result is not None else None,
            accepted_plan_after=deepcopy(result.repaired_plan if accepted else before_plan),
            repair_metadata=debug_metadata,
            input_tokens_before=usage_before.get("input_tokens"),
            input_tokens_after=usage_after.get("input_tokens"),
            input_tokens_delta=usage_delta(usage_before, usage_after, "input_tokens"),
            output_tokens_before=usage_before.get("output_tokens"),
            output_tokens_after=usage_after.get("output_tokens"),
            output_tokens_delta=usage_delta(usage_before, usage_after, "output_tokens"),
            **compare_edit_footprint(before_plan, result.repaired_plan if result is not None else None),
            **system_delta(system_before, system_snapshot()),
            total_tokens_delta=usage_delta(usage_before, usage_after, "total_tokens"),
            repair_model_calls=usage_delta(usage_before, usage_after_repair, "model_calls"),
            verification_model_calls=usage_delta(usage_after_repair, usage_after_verification, "model_calls"),
            model_calls=usage_delta(usage_before, usage_after, "model_calls"),
            failed_model_calls=usage_delta(usage_before, usage_after, "failed_model_calls"),
            repair_time_seconds=repair_finished - repair_started,
            verification_time_seconds=((verification_finished or attempt_finished) - verification_started
                                       if verification_started is not None else 0.0),
            attempt_time_seconds=attempt_finished - repair_started,
            exception=f"{type(failure).__name__}: {failure}" if failure is not None else None,

        )

        ## Record the repair and any changes in constraint satisfaction.
        history.append({
            "step": step,
            "accepted": accepted,
            "candidate_plan": deepcopy(result.repaired_plan) if result is not None else None,
            "verification": candidate_verification,
            "constraint_transitions": transitions,
            "metadata": deepcopy(debug_metadata),
            "repair_attempt": record.to_dict(),
        })
        if history_callback is not None:
            history_callback(deepcopy(history))

        if failure is not None:
            raise failure

        ## Update the current plan only when accepted.
        if accepted:
            current_plan = deepcopy(result.repaired_plan)
            current_verification = candidate_verification

    ## Return the final accepted plan and the full attempt history.
    return {
        "raw_plan": current_plan,
        "verification": current_verification,
        "history": history,
    }
