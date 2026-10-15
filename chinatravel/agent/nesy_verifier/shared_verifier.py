
## Shared verification function for R0-R4.
## Uses ChinaTravel's existing commonsense and personal constraint checks.

from copy import deepcopy

from chinatravel.agent.nesy_verifier.verifier.commonsense_constraint_nl import (
    collect_commonsense_constraints_error,
)
from chinatravel.symbol_verification.hard_constraint import (
    _normalize_legacy_hard_logic_py,
)
from chinatravel.symbol_verification.concept_func import func_dict
from chinatravel.symbol_verification.dsl import execute_dsl_code


## Check each personal constraint and distinguish failures from errors.
def check_personal_constraints(problem, plan):
    results = []
    evaluation_errors = []

    for i, original_constraint in enumerate(
        problem.get("hard_logic_py", [])
    ):
        constraint = _normalize_legacy_hard_logic_py(original_constraint)

        variables = deepcopy(func_dict)
        variables["plan"] = plan

        try:
            execute_dsl_code(
                constraint,
                variables,
                allowed_builtins={"set": set},
            )
            results.append(bool(variables.get("result", False)))

        except Exception as e:
            ## None means the constraint could not be evaluated.
            results.append(None)
            evaluation_errors.append({
                "constraint_index": i + 1,
                "error": str(e),
            })

    return results, evaluation_errors


## Shared verifier for R0-R4.
def verify_plan(problem, plan, translate_fn=None):

    ## Verify commonsense constraints before transport translation.
    commonsense_errors = collect_commonsense_constraints_error(
        problem, deepcopy(plan), verbose=False
    )

    ## Preserve the raw plan and translate a separate copy.
    translated_plan = deepcopy(plan)
    translation_errors = []

    if translate_fn is not None:
        try:
            translated_plan["itinerary"] = translate_fn(
                translated_plan["itinerary"], problem
            )
        except Exception as e:
            translation_errors.append(str(e))
    else:
        translation_errors.append("No transport translation function provided.")

    ## Do not evaluate personal constraints if translation failed.
    if translation_errors:
        personal_results = [
            None for _ in problem.get("hard_logic_py", [])
        ]
        evaluation_errors = []
    else:
        personal_results, evaluation_errors = check_personal_constraints(
            problem, translated_plan
        )

    ## Create feedback for genuinely failed personal constraints.
    personal_errors = []

    for i, passed in enumerate(personal_results):
        if passed is False:
            personal_errors.append(
                f"Personal constraint {i + 1} failed: "
                f"{problem['hard_logic_py'][i]}"
            )

    ## Collect all feedback.
    all_errors = commonsense_errors + personal_errors

    ## A plan only passes if there are no violations or verifier errors.
    passed = (
        len(all_errors) == 0
        and len(evaluation_errors) == 0
        and len(translation_errors) == 0
        and all(x is True for x in personal_results)
    )

    return {
        "commonsense_errors": commonsense_errors,
        "personal_constraints": personal_results,
        "personal_errors": personal_errors,
        "evaluation_errors": evaluation_errors,
        "translation_errors": translation_errors,
        "error_info": all_errors,
        "passed": passed,
        "translated_plan": translated_plan,
    }
