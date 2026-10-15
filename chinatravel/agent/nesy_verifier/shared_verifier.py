
## Shared verifier used by all repair strategies (R0-R4).

from copy import deepcopy

from chinatravel.agent.nesy_verifier.verifier.commonsense_constraint_nl import (
    collect_commonsense_constraints_error,
)
from chinatravel.symbol_verification.hard_constraint import (
    _normalize_legacy_hard_logic_py,
)
from chinatravel.symbol_verification.concept_func import func_dict
from chinatravel.symbol_verification.dsl import execute_dsl_code


## Marks a verifier crash rather than a real violation. Matches a string
## hardcoded upstream in commonsense_constraint_nl.py. The 'symoblic' typo is
## real and must stay verbatim; update this if that upstream string changes.
COMMONSENSE_VERIFIER_ERROR_MARKER = "Raise error in symoblic commonsense feedback"

## Activity types ChinaTravel accepts (checked against collect_type_error).
ALLOWED_ACTIVITY_TYPES = {
    "airplane",
    "train",
    "attraction",
    "breakfast",
    "lunch",
    "dinner",
    "accommodation",
}

## Intercity activities use 'start'/'end' instead of 'position'.
INTERCITY_TYPES = {"airplane", "train"}

_REQUIRED_TRANSPORT_KEYS = {"from", "to", "start_time", "end_time", "mode", "cost"}


## Separate verifier crash messages from genuine commonsense violations.
def _split_commonsense_errors(errors):
    genuine_commonsense_errors = []
    verifier_errors = []

    for error in errors:
        if COMMONSENSE_VERIFIER_ERROR_MARKER in error:
            verifier_errors.append(error)
        else:
            genuine_commonsense_errors.append(error)

    return genuine_commonsense_errors, verifier_errors


## Spot transport that silently failed to translate: the baseline translator
## swallows errors and leaves an empty list, so we flag an activity only when a
## real transport dict (all keys, from != to) became []. Genuine empties
## (missing/empty/non-dict transports, or from == to) are left alone.
def _detect_silent_translation_failures(original_itinerary, translated_itinerary):
    failures = []

    if not isinstance(original_itinerary, list) or not isinstance(
        translated_itinerary, list
    ):
        return failures

    for d, (orig_day, trans_day) in enumerate(
        zip(original_itinerary, translated_itinerary), start=1
    ):
        if not isinstance(orig_day, dict) or not isinstance(trans_day, dict):
            continue

        orig_activities = orig_day.get("activities")
        trans_activities = trans_day.get("activities")

        if not isinstance(orig_activities, list) or not isinstance(
            trans_activities, list
        ):
            continue

        for orig_act, trans_act in zip(orig_activities, trans_activities):
            if not isinstance(orig_act, dict) or not isinstance(trans_act, dict):
                continue

            orig_transports = orig_act.get("transports")

            if not isinstance(orig_transports, dict):
                continue
            if not _REQUIRED_TRANSPORT_KEYS.issubset(orig_transports.keys()):
                continue
            if orig_transports.get("from") == orig_transports.get("to"):
                continue

            if trans_act.get("transports") == []:
                label = orig_act.get("position")
                if label is None:
                    label = f"{orig_act.get('start')}->{orig_act.get('end')}"
                failures.append(
                    f"Transport translation failed for day {d} activity '{label}'"
                )

    return failures


## Report structural problems without fixing them: never raises, never rewrites
## the plan, never calls the environment. Detection and feedback only.
def _validate_plan_structure(plan):
    schema_errors = []

    if not isinstance(plan, dict):
        schema_errors.append("Plan must be a dict with an 'itinerary' list.")
        return schema_errors

    itinerary = plan.get("itinerary")
    if not isinstance(itinerary, list):
        schema_errors.append("Plan 'itinerary' must be a list of day objects.")
        return schema_errors

    for d, day in enumerate(itinerary, start=1):
        if not isinstance(day, dict):
            schema_errors.append(f"Day {d} must be a dict with an 'activities' list.")
            continue

        activities = day.get("activities")
        if not isinstance(activities, list):
            schema_errors.append(
                f"Day {d} must have an 'activities' list."
            )
            continue

        for a, activity in enumerate(activities, start=1):
            if not isinstance(activity, dict):
                schema_errors.append(
                    f"Day {d} activity {a} must be a dict."
                )
                continue

            act_type = activity.get("type")
            if act_type is None:
                schema_errors.append(
                    f"Day {d} activity {a} is missing a 'type'."
                )
                continue

            ## Inner-city transport belongs inside a destination activity's
            ## 'transports' field, so a standalone activity of this type is wrong.
            if act_type == "innercity_transport":
                schema_errors.append(
                    f"Day {d} activity {a} has unsupported type "
                    f"'innercity_transport'; inner-city transport must be nested "
                    f"in a destination activity's 'transports' field, not a "
                    f"separate activity."
                )
                continue

            if act_type not in ALLOWED_ACTIVITY_TYPES:
                schema_errors.append(
                    f"Day {d} activity {a} has unsupported type '{act_type}'."
                )
                continue

            if act_type not in INTERCITY_TYPES and "position" not in activity:
                schema_errors.append(
                    f"Day {d} activity {a} ('{act_type}') is missing 'position'."
                )

            if "start_time" not in activity:
                schema_errors.append(
                    f"Day {d} activity {a} ('{act_type}') is missing 'start_time'."
                )
            if "end_time" not in activity:
                schema_errors.append(
                    f"Day {d} activity {a} ('{act_type}') is missing 'end_time'."
                )

    return schema_errors


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
            ## None = could not be evaluated, kept distinct from a real pass/fail.
            results.append(None)
            evaluation_errors.append({
                "constraint_index": i + 1,
                "error": str(e),
            })

    return results, evaluation_errors


def verify_plan(problem, plan, translate_fn=None):

    schema_errors = _validate_plan_structure(plan)

    raw_commonsense_errors = collect_commonsense_constraints_error(
        problem, deepcopy(plan), verbose=False
    )

    commonsense_errors, verifier_errors = _split_commonsense_errors(
        raw_commonsense_errors
    )

    ## Keep the raw plan untouched; translate a separate copy.
    translated_plan = deepcopy(plan)
    translation_errors = []
    translation_failures = []

    if translate_fn is not None:
        try:
            translated_plan["itinerary"] = translate_fn(
                translated_plan["itinerary"], problem
            )

            translation_failures = _detect_silent_translation_failures(
                plan.get("itinerary"), translated_plan["itinerary"]
            )
            translation_errors.extend(translation_failures)

        except Exception as e:
            translation_errors.append(str(e))
    else:
        translation_errors.append("No transport translation function provided.")

    ## Skip personal checks if translation failed; results are unknown (None).
    if translation_errors:
        personal_results = [
            None for _ in problem.get("hard_logic_py", [])
        ]
        evaluation_errors = []
    else:
        personal_results, evaluation_errors = check_personal_constraints(
            problem, translated_plan
        )

    personal_errors = []

    for i, passed in enumerate(personal_results):
        if passed is False:
            personal_errors.append(
                f"Personal constraint {i + 1} failed: "
                f"{problem['hard_logic_py'][i]}"
            )

    ## error_info is genuine violations only (what R0's repair prompt tries to
    ## fix). Technical errors stay on their own channels so repair difficulty is
    ## unchanged.
    all_errors = commonsense_errors + personal_errors

    ## Any technical error (verifier crash, translation failure, bad structure)
    ## forces passed=False, so a plan can never pass by accident.
    passed = (
        len(all_errors) == 0
        and len(evaluation_errors) == 0
        and len(translation_errors) == 0
        and len(verifier_errors) == 0
        and len(schema_errors) == 0
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
        "verifier_errors": verifier_errors,
        "schema_errors": schema_errors,
        "translation_failures": translation_failures,
    }
