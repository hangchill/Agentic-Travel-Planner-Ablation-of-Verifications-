
from copy import deepcopy
from time import perf_counter

from chinatravel.evaluation.repair_attempt import (
    RepairAttemptRecord, failed_constraint_indices, normalize_repair_intent_metadata,
)


def verify_plan(*args, **kwargs):
    # Defer database-backed imports so the loop can be tested with a mock verifier.
    from chinatravel.agent.nesy_verifier.shared_verifier import verify_plan as verifier

    return verifier(*args, **kwargs)


def _token_count(llm, name):
    value = getattr(llm, name, None)
    return value if type(value) is int and value >= 0 else None


def _token_delta(before, after):
    return after - before if before is not None and after is not None else None


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

    ## Verify the initial itinerary.
    current_verification = deepcopy(initial_verification) if initial_verification is not None else verify_plan(
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
    }]

    ## Each proposed repair uses one attempt from the budget.
    for step in range(1, max_steps + 1):

        ## Stop if the current plan satisfies all reported checks.
        if current_verification["passed"]:
            break

        before_verification = deepcopy(current_verification)
        before_plan = deepcopy(current_plan)
        input_before = _token_count(llm, "input_token_count")
        output_before = _token_count(llm, "output_token_count")
        repair_started = perf_counter()
        ## Ask the selected strategy to propose a repair.
        result = strategy.repair(
            problem=problem,
            raw_plan=deepcopy(current_plan),
            verification_results=current_verification,
            context=context,
            llm=llm,
        )
        repair_time = perf_counter() - repair_started
        input_after = _token_count(llm, "input_token_count")
        output_after = _token_count(llm, "output_token_count")

        ## Verify the proposed itinerary.
        candidate_verification = verify_plan(
            problem,
            {
                "people_number": problem["people_number"],
                "start_city": problem["start_city"],
                "target_city": problem["target_city"],
                "itinerary": deepcopy(result.repaired_plan),
            },
            translate_fn=translate_fn,
        )
        after_verification = deepcopy(candidate_verification)

        ## Let the strategy decide whether to accept the proposal.
        accepted = strategy.accept(
            current_verification,
            candidate_verification,
        )

        ## Compare constraint results before and after the proposed repair.
        ## Compare against the current accepted plan, not a rejected candidate.
        transitions = compare_constraint_results(
            before_verification,
            after_verification,
        )

        intent, debug_metadata = normalize_repair_intent_metadata(result.metadata)
        strategy_name = intent.pop("repair_strategy", type(strategy).__name__)
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
            candidate_plan=deepcopy(result.repaired_plan),
            accepted_plan_after=deepcopy(result.repaired_plan if accepted else before_plan),
            repair_metadata=debug_metadata,
            input_tokens_before=input_before,
            input_tokens_after=input_after,
            input_tokens_delta=_token_delta(input_before, input_after),
            output_tokens_before=output_before,
            output_tokens_after=output_after,
            output_tokens_delta=_token_delta(output_before, output_after),
            repair_time_seconds=repair_time,
        )

        ## Record the repair and any changes in constraint satisfaction.
        history.append({
            "step": step,
            "accepted": accepted,
            "candidate_plan": deepcopy(result.repaired_plan),
            "verification": candidate_verification,
            "constraint_transitions": transitions,
            "metadata": deepcopy(debug_metadata),
            "repair_attempt": record.to_dict(),
        })
        if history_callback is not None:
            history_callback(deepcopy(history))

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
