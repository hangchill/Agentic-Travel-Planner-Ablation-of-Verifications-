"""Display formatting for itinerary and verification artifacts."""

from typing import Any


ACTIVITY_LABELS = {
    "accommodation": "Stay",
    "airplane": "Flight",
    "attraction": "Attraction",
    "breakfast": "Breakfast",
    "dinner": "Dinner",
    "lunch": "Lunch",
    "train": "Train",
}
ACTIVITY_ICONS = {
    "accommodation": "🛏️",
    "airplane": "✈️",
    "attraction": "📍",
    "breakfast": "🥐",
    "dinner": "🍽️",
    "lunch": "🍜",
    "train": "🚆",
}


def itinerary_days(plan: Any) -> list[dict[str, Any]]:
    """Return day objects from either an itinerary list or a wrapped plan."""
    if isinstance(plan, dict):
        plan = plan.get("itinerary", [])
    if not isinstance(plan, list):
        return []
    return [day for day in plan if isinstance(day, dict)]


def activity_title(activity: dict[str, Any]) -> str:
    activity_type = str(activity.get("type", "")).lower()
    place = activity.get("position")
    if place:
        return str(place)
    start = activity.get("start")
    end = activity.get("end")
    if start or end:
        return f"{start or 'Origin'} → {end or 'Destination'}"
    return ACTIVITY_LABELS.get(activity_type, activity_type.title() or "Activity")


def format_money(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return f"¥{float(value):,.2f}"
    except (TypeError, ValueError):
        return None


def transport_description(transport: Any) -> str | None:
    """Make the itinerary's supported dict/list transport shapes readable."""
    if isinstance(transport, str):
        if transport.strip().lower() in {"", "empty", "none", "null"}:
            return None
        return transport
    if isinstance(transport, list):
        segments = [
            description
            for item in transport
            if isinstance(item, dict)
            for description in [transport_description(item)]
            if description
        ]
        return " · ".join(segments) if segments else None
    if not isinstance(transport, dict):
        return None

    origin = transport.get("from")
    destination = transport.get("to")
    mode = transport.get("mode")
    start_time = transport.get("start_time")
    end_time = transport.get("end_time")
    route = f"{origin or 'Origin'} → {destination or 'Destination'}"
    details = [str(mode).replace("_", " ").title()] if mode else []
    if start_time or end_time:
        details.append(f"{start_time or '?'}–{end_time or '?'}")
    cost = format_money(transport.get("cost"))
    if cost:
        details.append(cost)
    return route + (f" ({', '.join(details)})" if details else "")


def count_constraint_states(states: Any) -> dict[str, int]:
    states = states if isinstance(states, list) else []
    return {
        "passed": sum(state is True for state in states),
        "failed": sum(state is False for state in states),
        "unknown": sum(state is None for state in states),
    }


def verification_issue_groups(verification: Any) -> list[tuple[str, list[str]]]:
    if not isinstance(verification, dict):
        return []
    groups = (
        ("Itinerary structure", "schema_errors"),
        ("Travel / transport", "translation_errors"),
        ("Preference constraints", "personal_errors"),
        ("Commonsense checks", "commonsense_errors"),
        ("Verification execution", "evaluation_errors"),
        ("Verifier diagnostics", "verifier_errors"),
        ("Planner-reported issues", "error_info"),
    )
    result = []
    for label, key in groups:
        values = verification.get(key) or []
        if isinstance(values, list) and values:
            result.append((label, [str(value) for value in values]))
    return result


def change_summary(attempt: dict[str, Any]) -> list[str]:
    """Explain personal-constraint transitions without exposing raw JSON."""
    transitions = attempt.get("constraint_transitions")
    if not isinstance(transitions, dict):
        transitions = attempt
    descriptions = []
    fixed = transitions.get("fixed") or []
    newly_violated = transitions.get("newly_violated") or []
    still_failed = transitions.get("still_failed") or []
    unknown = transitions.get("unknown") or []
    if fixed:
        descriptions.append(f"Resolved checks: {', '.join(map(str, fixed))}")
    if newly_violated:
        descriptions.append(f"Newly failed checks: {', '.join(map(str, newly_violated))}")
    if still_failed:
        descriptions.append(f"Still failing: {', '.join(map(str, still_failed))}")
    if unknown:
        descriptions.append(f"Could not evaluate: {', '.join(map(str, unknown))}")
    return descriptions
