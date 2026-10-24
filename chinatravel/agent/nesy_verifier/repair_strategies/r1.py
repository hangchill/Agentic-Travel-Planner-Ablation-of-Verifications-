from copy import deepcopy
from .base import BaseRepairStrategy, RepairResult
from chinatravel.evaluation.repair_attempt import failed_constraint_indices
from chinatravel.evaluation.constraint_families import classify_constraint
from chinatravel.environment.tools.transportation.apis import Transportation
import json
import re
import math


ACTIVITY_TYPES = {"dining": {"breakfast", "lunch", "dinner"},
                  "accommodation": {"accommodation"},
                  "attraction": {"attraction"},
                  "transport_mode": {"train", "airplane"},}

# returns all matching activities
def find_candidate_slots(raw_plan, constraint_family):
    allowed_types = ACTIVITY_TYPES.get(constraint_family)
    if not allowed_types:
        return []
    candidates = []
    for day_idx, day in enumerate(raw_plan):
        for activity_idx, activity in enumerate(day.get("activities", [])):
            if activity.get("type") in allowed_types:
                candidates.append((day_idx, activity_idx))
    return candidates

def find_budget_candidate_slots(raw_plan):
    """Find cost-bearing activity slots for targeted budget repair."""
    candidates = []
    for day_idx, day in enumerate(raw_plan):
        for activity_idx, activity in enumerate(
            day.get("activities", [])):
            if not isinstance(activity, dict):
                continue
            if activity.get("type") not in {
                "accommodation", "attraction",
                "breakfast", "lunch", "dinner",}:
                continue
            cost = activity.get("cost", 0)
            if (isinstance(cost, (int, float))
                and not isinstance(cost, bool)
                and cost > 0):
                candidates.append((day_idx, activity_idx))
    return candidates

def find_editable_slot(raw_plan, constraint_family):
    if constraint_family == "transport_mode":
        candidates = find_transport_slots(raw_plan)
    else:
        candidates = find_candidate_slots(raw_plan, constraint_family)    
    if len(candidates) == 1:
        return candidates[0]
    return None

def classify_failed_constraint(problem, target_idx):
    constraints = problem.get("hard_logic_py", [])
    if not 1 <= target_idx <= len(constraints):
        return None
    descriptor = {"constraint_index": target_idx,
                  "hard_logic_py": constraints[target_idx - 1],}
    result = classify_constraint(descriptor)
    if result["classification_status"] != "mapped":
        return None
    return result["family"]

# replace one activity and preserve the rest of the itinerary
def replace_activity_slot(raw_plan, slot, replacement):
    day_idx, activity_idx = slot
    repaired_plan = deepcopy(raw_plan)
    if not isinstance(replacement, dict):
        raise ValueError("Replacement must be an activity dictionary")
    if not 0 <= day_idx < len(repaired_plan):
        raise ValueError("Invalid day index")
    activities = repaired_plan[day_idx]["activities"]
    if not 0 <= activity_idx < len(activities):
        raise ValueError("Invalid activity index")
    original_type = activities[activity_idx].get("type")
    if replacement.get("type") != original_type:
        raise ValueError("Replacement must preserve activity type")
    required_keys = {"type", "start_time", "end_time"}
    if original_type not in {"train", "airplane"}:
        required_keys.add("position")
    if not required_keys.issubset(replacement):
        raise ValueError("Replacement activity missing required fields")
    activities[activity_idx] = deepcopy(replacement)
    return repaired_plan

def parse_replacement_json(response):
    if not isinstance(response, str):
        raise ValueError("LLM response must be a string")
    text = response.strip()
    if text.startswith("```"):
        match = re.fullmatch(
            r"```(?:json)?\s*\n(.*?)\n```",
            text, flags=re.DOTALL | re.IGNORECASE,)
        if not match:
            raise ValueError("Malformed JSON code fence")
        text = match.group(1).strip()
    try:
        result = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid replacement JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("Replacement must be a JSON object")
    return result

def generate_replacement(
    problem, raw_plan, slot, constraint_text, context, llm):
    day_idx, activity_idx = slot
    original = raw_plan[day_idx]["activities"][activity_idx]
    prompt = f"""
You are repairing one activity in a travel itinerary.
User request:{problem["nature_language"]}
Failed constraint:{constraint_text}
Current activity:{json.dumps(original, ensure_ascii=False)}
Available travel information:{json.dumps(context, ensure_ascii=False, default=str)}
Return ONLY one JSON object representing a replacement activity.

Rules:
- Preserve the original activity type.
- Keep the same activity structure and required fields.
- Use only entities supported by the available travel information.
- Do not return the entire itinerary.
- Do not invent prices, opening hours, or transport details.
"""
    response = llm([{"role": "user", "content": prompt}], 
                   one_line=False,  json_mode=True,)
    replacement = parse_replacement_json(response)
    if not isinstance(replacement, dict):
        raise ValueError("LLM must return one activity object")
    return replacement

def select_editable_slot(problem, raw_plan, candidates, constraint_text, llm):
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    candidate_info = [{"day_index": day_idx,
                       "activity_index": activity_idx,
                       "activity": raw_plan[day_idx]["activities"][activity_idx],}
                       for day_idx, activity_idx in candidates]
    prompt = f"""
You are identifying which itinerary activity should be edited
to address a failed travel constraint.

User request:
{problem["nature_language"]}

Failed constraint:
{constraint_text}

Candidate activities:
{json.dumps(candidate_info, ensure_ascii=False)}

Select ONE activity most relevant to the failed constraint.

Return ONLY a JSON object in this format:
{{"day_index": 0, "activity_index": 1}}

Use the exact zero-based indices provided.
Do not invent new indices.
"""
    response = llm([{"role": "user", "content": prompt}],
                   one_line=False,  json_mode=True,)
    try:
        selection = json.loads(response)
        if not isinstance(selection, dict):
            return None
        slot = (selection["day_index"], selection["activity_index"],)
    except (ValueError, TypeError, KeyError):
        return None

    if (type(slot[0]) is not int
        or type(slot[1]) is not int
        or slot not in candidates):
        return None
    return slot

# identify activities containing an inner city transport dictionary
def find_transport_slots(raw_plan): 
    candidates = []
    for day_idx, day in enumerate(raw_plan):
        for activity_idx, activity in enumerate(day.get("activities", [])):
            transport = activity.get("transports")
            if isinstance(transport, dict):
                candidates.append((day_idx, activity_idx))
    return candidates

def replace_transport_slot(raw_plan, slot, replacement): # ensure only nested transport fields changes
    day_idx, activity_idx = slot
    repaired_plan = deepcopy(raw_plan)
    activity = repaired_plan[day_idx]["activities"][activity_idx]
    if not isinstance(activity.get("transports"), dict):
        raise ValueError("Selected activity has no editable transport")
    if not isinstance(replacement, dict):
        raise ValueError("Replacement transport must be a dictionary")
    required_keys = {"from", "to", "start_time", "end_time", "mode", "cost"}
    original = activity["transports"]
    if replacement["from"] != original["from"]:
        raise ValueError("Transport origin cannot change")
    if replacement["to"] != original["to"]:
        raise ValueError("Transport destination cannot change")
    if replacement["mode"] not in {"metro", "taxi", "walk"}:
        raise ValueError("Unsupported transport mode")
    if (type(replacement["cost"]) not in (int, float)
        or replacement["cost"] < 0):
        raise ValueError("Invalid transport cost")
    if not required_keys.issubset(replacement):
        raise ValueError("Replacement transport is missing required fields")
    activity["transports"] = deepcopy(replacement)
    return repaired_plan

# replace only transport information, preserve origin and destination
def generate_transport_replacement(
    problem, raw_plan, slot, constraint_text, context, llm):
    day_idx, activity_idx = slot
    original = raw_plan[day_idx]["activities"][activity_idx]["transports"]
    prompt = f"""
You are repairing one inner-city transport segment in a travel itinerary.

User request:
{problem["nature_language"]}

Failed constraint:
{constraint_text}

Current transport:
{json.dumps(original, ensure_ascii=False)}

Available transport information:
{context.get("innercity_transport_info", "")}

Return ONLY one JSON object with:
from, to, start_time, end_time, mode, cost.

Rules:
- Preserve the original from and to locations.
- Change only the transport segment.
- Use a transport option supported by the available information.
- Do not invent routes, times or costs.
- Do not return the entire itinerary.
"""
    response = llm([{"role": "user", "content": prompt}],
                   one_line=False, json_mode=True,)
    try:
        replacement = json.loads(response)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid transport replacement JSON") from exc

    if not isinstance(replacement, dict):
        raise ValueError("Transport replacement must be an object")
    if replacement.get("from") != original.get("from"):
        raise ValueError("Transport origin cannot change")
    if replacement.get("to") != original.get("to"):
        raise ValueError("Transport destination cannot change")
    return replacement

def select_repair_target(problem, raw_plan, failed_indices):
    for target_idx in failed_indices:
        family = classify_failed_constraint(problem, target_idx)
        if family == "transport_mode":
            candidates = find_transport_slots(raw_plan)
        elif family == "monetary_budget":
            candidates = find_budget_candidate_slots(raw_plan)
        else:
            candidates = find_candidate_slots(raw_plan, family)
        if candidates:
            return target_idx, family, candidates
    return None, None, []


def localise_transport_error(raw_plan, error_message):
    pattern = (r"Unavailable Inner-City Transport information in (\d+), "
               r"from (.+?) to (.+?), "
               r"start_time ([^,]+), transport_type (.+)")
    match = re.fullmatch(pattern, error_message.strip())
    if not match:
        return None
    day_number = int(match.group(1))
    origin = match.group(2)
    destination = match.group(3)
    start_time = match.group(4)
    mode = match.group(5)
    day_idx = day_number - 1
    if not 0 <= day_idx < len(raw_plan):
        return None
    matches = []
    for activity_idx, activity in enumerate(
        raw_plan[day_idx].get("activities", [])):
        transport = activity.get("transports")
        if not isinstance(transport, dict):
            continue
        if (transport.get("from") == origin
            and transport.get("to") == destination
            and str(transport.get("start_time")) == start_time
            and str(transport.get("mode")) == mode):
            matches.append((day_idx, activity_idx))
    return matches[0] if len(matches) == 1 else None


def repair_commonsense_transport(
    problem, raw_plan, verification_results):
    errors = verification_results.get("commonsense_errors", [])
    if not isinstance(errors, list):
        return None
    for error in errors:
        if not isinstance(error, str):
            continue
        slot = localise_transport_error(raw_plan, error)
        if slot is None:
            continue
        day_idx, activity_idx = slot
        original = raw_plan[day_idx]["activities"][activity_idx]["transports"]
        city = problem.get("target_city")
        if not city:
            continue
        options = lookup_transport_options(
            city=city,
            origin=original["from"],
            destination=original["to"],
            start_time=original["start_time"],
            lang=problem.get("lang", "en"),)
        for option in options:
            replacement = convert_transport_option(option, original)
            if replacement is None:
                continue
            if replacement == original:
                continue
            repaired_plan = replace_transport_slot(
                raw_plan, slot, replacement)
            return RepairResult(
                repaired_plan=repaired_plan,
                metadata={"strategy": "R1",
                          "target_constraint_indices": [],
                          "editable_scope": "slot",
                          "scope_level": 1,
                          "feedback_personal_constraint_indices": [],
                          "feedback_commonsense_failure_count": len(errors),
                          "editable_slot": slot,
                          "target_commonsense_error": error,
                          "repair_source": "transport_lookup",},)
    return None


def localise_transport_cost_error(raw_plan, error_message):
    pattern = (
        r"Incorrect cost infomation of innercity transport in day (\d+), "
        r"from (.+?) to (.+?), (metro|taxi|walk)\. "
        r"\[cost = .+\]")
    match = re.fullmatch(pattern, error_message.strip())
    if not match:
        return None
    day_idx = int(match.group(1)) - 1
    origin, destination, mode = match.group(2, 3, 4)
    if not 0 <= day_idx < len(raw_plan):
        return None
    matches = []
    for activity_idx, activity in enumerate(
        raw_plan[day_idx].get("activities", [])):
        transport = activity.get("transports")
        if not isinstance(transport, dict):
            continue
        if (transport.get("from") == origin
            and transport.get("to") == destination
            and transport.get("mode") == mode):
            matches.append((day_idx, activity_idx))
    # never guess if multiple slots match
    return matches[0] if len(matches) == 1 else None

def repair_commonsense_transport_cost(
    problem, raw_plan, verification_results):
    errors = verification_results.get("commonsense_errors", [])
    if not isinstance(errors, list):
        return None
    transport_tool = Transportation(lang=problem.get("lang", "en"))
    people_number = problem.get("people_number")
    if (type(people_number) is not int
        or people_number <= 0):
        return None
    for error in errors:
        if not isinstance(error, str):
            continue
        slot = localise_transport_cost_error(raw_plan, error)
        if slot is None:
            continue
        day_idx, activity_idx = slot
        original = raw_plan[day_idx]["activities"][activity_idx]["transports"]
        mode = original["mode"]
        try:
            options = transport_tool.goto(
                city=problem["target_city"],
                start=original["from"],
                end=original["to"],
                start_time=original["start_time"],
                transport_type=mode,
                verbose=False,)
            if not isinstance(options, list) or not options:
                continue
            if mode == "metro":
                correct_cost = sum(segment["cost"] for segment in options) * people_number
            elif mode == "taxi":
                correct_cost = options[0]["cost"] * math.ceil(people_number / 4)
            elif mode == "walk":
                correct_cost = 0
            else:
                continue
            if (not isinstance(correct_cost, (int, float))
                or not math.isfinite(correct_cost)
                or correct_cost < 0):
                continue
        except (KeyError, ValueError, TypeError, OSError, IndexError):
            continue
        if abs(original["cost"] - correct_cost) <= 0.1:
            continue
        repaired_plan = deepcopy(raw_plan)
        repaired_plan[day_idx]["activities"][activity_idx]["transports"]["cost"] = correct_cost
        return RepairResult(repaired_plan=repaired_plan,
                            metadata={"strategy": "R1",
                                      "target_constraint_indices": [],
                                      "editable_scope": "slot",
                                      "scope_level": 1,
                                      "feedback_personal_constraint_indices": [],
                                      "feedback_commonsense_failure_count": len(errors),
                                      "editable_slot": slot,
                                      "target_commonsense_error": error,
                                      "repair_source": "transport_cost_lookup",
                                      "original_cost": original["cost"],
                                      "corrected_cost": correct_cost,},)
    return None

def is_within_opening_hours(start_time, end_time, open_time, close_time):
    def minutes(value):
        if not isinstance(value, str):
            raise ValueError("Time must be a string")
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("Invalid time format")
        hour, minute = map(int, parts)
        if not (0 <= minute < 60):
            raise ValueError("Invalid minutes")
        if hour == 24 and minute == 0:
            return 1440
        if not (0 <= hour < 24):
            raise ValueError("Invalid hours")
        return hour * 60 + minute
    opening = minutes(open_time)
    closing = minutes(close_time)
    start = minutes(start_time)
    end = minutes(end_time)
    # opening hours cross midnight
    if closing < opening:
        closing += 1440
        if start < opening:
            start += 1440
        if end < opening:
            end += 1440
    return opening <= start < end <= closing

def repair_commonsense_activity(
    problem, raw_plan, verification_results, context, llm):
    patterns = [
        ("attraction",
         r"The attraction, (.+?) in day (\d+), is closed "
         r"when you visiting\. Its open time is "
         r"\[(.+?) -- (.+?)\]",),
         ("restaurant",
          r"The restaurant, (.+?) in day (\d+), is closed "
          r"when you visiting\. Its open time is "
          r"\[(.+?) -- (.+?)\]",),]
    for error in verification_results.get("commonsense_errors", []):
        if not isinstance(error, str):
            continue
        for family, pattern in patterns:
            match = re.fullmatch(pattern, error.strip())
            if match is None:
                continue
            position = match.group(1)
            day_idx = int(match.group(2)) - 1
            open_time = match.group(3)
            close_time = match.group(4)
            if not 0 <= day_idx < len(raw_plan):
                continue
            matches = []
            for activity_idx, activity in enumerate(
                raw_plan[day_idx].get("activities", [])):
                activity_type = activity.get("type")
                correct_family = (
                    activity_type == "attraction"
                    if family == "attraction"
                    else activity_type in
                    {"breakfast", "lunch", "dinner"})
                if (correct_family
                    and activity.get("position") == position):
                    matches.append((day_idx, activity_idx))
            if len(matches) != 1:
                continue
            slot = matches[0]
            metadata = {
                "strategy": "R1",
                "target_constraint_indices": [],
                "editable_scope": "slot",
                "scope_level": 1,
                "editable_slot": slot,
                "constraint_family": family,
                "target_commonsense_error": error,
                "repair_source": "commonsense_activity",}
            instruction = (
                f"Fix this commonsense violation: {error}\n"
                f"The activity must fit within opening hours "
                f"{open_time} to {close_time}.\n"
                "Preserve the activity type and all unrelated "
                "itinerary slots.")
            try:
                replacement = generate_replacement(
                    problem=problem, raw_plan=raw_plan,
                    slot=slot, constraint_text=instruction,
                    context=context, llm=llm,)
                if not is_within_opening_hours(
                    replacement["start_time"],
                    replacement["end_time"],
                    open_time, close_time,):
                    raise ValueError(
                        "Replacement remains outside opening hours")
                repaired_plan = replace_activity_slot(
                    raw_plan, slot, replacement)
            except (ValueError, TypeError, KeyError) as exc:
                metadata["failure_reason"] = (
                    "invalid_commonsense_replacement")
                metadata["failure_detail"] = str(exc)[:200]
                return RepairResult(
                    repaired_plan=deepcopy(raw_plan),
                    metadata=metadata,)
            return RepairResult(
                repaired_plan=repaired_plan,
                metadata=metadata,)
    return None

class R1TargetedRepair(BaseRepairStrategy):
    def repair(self, problem, raw_plan, verification_results, context, llm):
        failed_indices = failed_constraint_indices(
            verification_results["personal_constraints"])
        phase = context.get("repair_phase")
        if phase == "commonsense" or (phase is None and not failed_indices):
            commonsense_result = repair_commonsense_transport_cost(
                problem, raw_plan, verification_results)
            if commonsense_result is None:
                commonsense_result = repair_commonsense_transport(
                    problem, raw_plan, verification_results)
            if commonsense_result is None:
                commonsense_result = repair_commonsense_activity(
                    problem=problem, raw_plan=raw_plan,
                    verification_results=verification_results,
                    context=context, llm=llm,)
            if commonsense_result is not None:
                return commonsense_result
            return RepairResult(
                repaired_plan=deepcopy(raw_plan),
                metadata={
                    "strategy": "R1",
                    "target_constraint_indices": [],
                    "editable_scope": "slot",
                    "scope_level": 1,
                    "failure_reason": "no_localizable_failure",},)
        if not failed_indices:
            return RepairResult(repaired_plan=deepcopy(raw_plan), metadata={
                "strategy": "R1", "target_constraint_indices": [],
                "failure_reason": "no_evaluable_personal_failure", "editable_scope": "slot"})
        target_idx, constraint_family, candidates = select_repair_target(
            problem, raw_plan, failed_indices,)
        if target_idx is None:
            return RepairResult(repaired_plan=deepcopy(raw_plan),
                                metadata={
                                    "strategy": "R1",
                                    "target_constraint_indices": [],
                                    "editable_scope": "slot",
                                    "scope_level": 1,
                                    "failure_reason": "no_localizable_failed_constraint",},) 
        constraint_text = problem["hard_logic_py"][target_idx - 1]
        if constraint_family == "monetary_budget":
            editable_slot = max(
                candidates,
                key=lambda slot: raw_plan[slot[0]]["activities"][slot[1]]["cost"],)
        else:
            editable_slot = select_editable_slot(
                problem=problem, raw_plan=raw_plan,
                candidates=candidates, constraint_text=constraint_text, llm=llm,)
        metadata = {"strategy": "R1", 
                    "target_constraint_indices": [target_idx],
                    "editable_scope": "slot",
                    "scope_level": 1,
                    "feedback_personal_constraint_indices": [target_idx],
                    "constraint_family": constraint_family,
                    "editable_slot": editable_slot,}

        # keep original plan if no unique slot can be identified
        if editable_slot is None:
            metadata["failure_reason"] = "no_localizable_slot"
            return RepairResult(repaired_plan=deepcopy(raw_plan), metadata=metadata,)
        try:
            if constraint_family == "transport_mode":
                replacement = generate_transport_replacement(
                    problem=problem, raw_plan=raw_plan,
                    slot=editable_slot, constraint_text=constraint_text,
                    context=context,llm=llm,)
                repaired_plan = replace_transport_slot(
                    raw_plan, editable_slot, replacement,)
            else:
                repair_instruction = constraint_text
                if constraint_family == "monetary_budget":
                    repair_instruction += (
                        "\nReduce the cost of this activity while preserving "
                        "its type, required fields, and other user constraints. "
                        "Use only verified alternatives from the available "
                        "travel information. Do not invent prices.")
                replacement = generate_replacement(
                    problem=problem, raw_plan=raw_plan, slot=editable_slot,
                    constraint_text=repair_instruction, context=context, llm=llm,)
                if constraint_family == "monetary_budget":
                    original = raw_plan[editable_slot[0]]["activities"][editable_slot[1]]
                    old_cost = original.get("cost")
                    new_cost = replacement.get("cost")
                    if (not isinstance(old_cost, (int, float))
                        or isinstance(old_cost, bool)
                        or not isinstance(new_cost, (int, float))
                        or isinstance(new_cost, bool)
                        or new_cost >= old_cost):
                        raise ValueError("Budget replacement must reduce activity cost")
                repaired_plan = replace_activity_slot(
                    raw_plan, editable_slot, replacement,)
        except (ValueError, TypeError, KeyError) as exc:
            metadata["failure_reason"] = "invalid_replacement"
            metadata["failure_detail"] = str(exc)[:200]
            return RepairResult(repaired_plan=deepcopy(raw_plan), metadata=metadata,)
        return RepairResult(repaired_plan=repaired_plan, metadata=metadata,)

def lookup_transport_options(
    city, origin, destination, start_time, lang="en"):
    from chinatravel.environment.tools.transportation.apis import (
        Transportation,)
    transport_tool = Transportation(lang=lang)
    options = []
    for mode in ("walk", "taxi", "metro"):
        try:
            result = transport_tool.goto(
                city=city, start=origin, end=destination,
                start_time=start_time, transport_type=mode,)
            if isinstance(result, list) and result:
                options.append({"mode": mode, "segments": result,})
        except (ValueError, KeyError, TypeError, OSError):
            continue
    return options


def convert_transport_option(option, original_transport):
    """Convert one verified direct transport option to R1 format."""
    if not isinstance(option, dict):
        return None
    segments = option.get("segments")
    # only support direct journeys for now
    if not isinstance(segments, list) or len(segments) != 1:
        return None
    segment = segments[0]
    if not isinstance(segment, dict):
        return None
    required = {"start", "end", "mode",
                "start_time", "end_time", "cost"}
    if not required.issubset(segment):
        return None
    # preserve original journey endpoints
    if segment["start"] != original_transport.get("from"):
        return None
    if segment["end"] != original_transport.get("to"):
        return None
    if segment["start_time"] != original_transport.get("start_time"):
        return None
    if segment["mode"] not in {"walk", "taxi"}:
        return None
    return {"from": segment["start"],
            "to": segment["end"],
            "mode": segment["mode"],
            "start_time": segment["start_time"],
            "end_time": segment["end_time"],
            "cost": segment["cost"],}
