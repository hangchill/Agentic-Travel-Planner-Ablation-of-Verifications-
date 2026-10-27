"""Local evidence and comparisons for the curated repair walkthrough.

No planner, verifier, or API dependency. Activity slots are stable in this fixture;
arbitrary runs would need their own alignment.
"""

import json
import re
from pathlib import Path

DEMO_PATH = Path(__file__).parent / "demo_data" / "nanjing_r2.json"


def load_demo(path: Path = DEMO_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def baseline_index(snapshots: list[dict], index: int) -> int:
    """A rejected proposal is never the input to the following repair."""
    for previous in range(index - 1, -1, -1):
        if snapshots[previous]["accepted"] is True:
            return previous
    return 0


def flatten(value: object, prefix: str = "") -> dict:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            result.update(flatten(item, f"{prefix}.{key}" if prefix else key))
        return result
    return {prefix: value}


def activity_changes(before: dict, after: dict) -> list[dict]:
    left, right = flatten(before), flatten(after)
    return [
        {"field": key, "before": left.get(key), "after": right.get(key)}
        for key in sorted(left.keys() | right.keys())
        if (key in left) != (key in right) or left.get(key) != right.get(key)
    ]


def plan_changes(before: list, after: list) -> list[dict]:
    result = []
    for day in range(max(len(before), len(after))):
        left = before[day].get("activities", []) if day < len(before) else []
        right = after[day].get("activities", []) if day < len(after) else []
        for slot in range(max(len(left), len(right))):
            changes = activity_changes(left[slot] if slot < len(left) else {}, right[slot] if slot < len(right) else {})
            if changes:
                result.append({"day": day + 1, "slot": slot, "changes": changes})
    return result


def issue_transitions(before: dict, after: dict) -> dict[str, set]:
    left = {issue["check_id"] for issue in before["issues"]}
    right = {issue["check_id"] for issue in after["issues"]}
    return {"resolved": left - right, "new": right - left, "remaining": left & right}


def violating_time_fields(activity: dict, issues: list[dict]) -> set[str]:
    """Locate time values using the opening window in the saved error evidence."""
    fields = set()
    for issue in issues:
        if issue["check_id"] in {"lunch_time", "dinner_time"}:
            fields.add("start_time")
        if issue["check_id"] not in {"attraction_hours", "restaurant_hours"}:
            continue
        window = re.search(r"\[(\d{2}:\d{2})\s*--\s*(\d{2}:\d{2})\]", issue["message"])
        if window:
            opens, closes = window.groups()
            if activity.get("start_time", "") < opens or activity.get("start_time", "") >= closes:
                fields.add("start_time")
            if activity.get("end_time", "") > closes:
                fields.add("end_time")
    return fields


def listed_cost(plan: list) -> float:
    """Include activity and transfer costs without double-counting price fields."""
    def transfer_cost(value):
        if isinstance(value, dict):
            return float(value.get("cost", 0) or 0)
        if isinstance(value, list):
            return sum(transfer_cost(item) for item in value)
        return 0

    return sum(float(a.get("cost", 0) or 0) + transfer_cost(a.get("transports"))
               for day in plan for a in day.get("activities", []))
