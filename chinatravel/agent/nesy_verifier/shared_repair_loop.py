
from copy import deepcopy

from chinatravel.agent.nesy_verifier.shared_verifier import verify_plan



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
):

    ## Keep the current accepted itinerary separate from candidates.
    current_plan = deepcopy(raw_plan)

    ## Verify the initial itinerary.
    current_verification = verify_plan(
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

        ## Ask the selected strategy to propose a repair.
        result = strategy.repair(
            problem=problem,
            raw_plan=deepcopy(current_plan),
            verification_results=current_verification,
            context=context,
            llm=llm,
        )

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

        ## Let the strategy decide whether to accept the proposal.
        accepted = strategy.accept(
            current_verification,
            candidate_verification,
        )

        ## Compare constraint results before and after the proposed repair.
        ## Compare against the current accepted plan, not a rejected candidate.
        transitions = compare_constraint_results(
            current_verification,
            candidate_verification,
        )

        ## Record the repair and any changes in constraint satisfaction.
        history.append({
            "step": step,
            "accepted": accepted,
            "candidate_plan": deepcopy(result.repaired_plan),
            "verification": candidate_verification,
            "constraint_transitions": transitions,
            "metadata": result.metadata,
        })

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
