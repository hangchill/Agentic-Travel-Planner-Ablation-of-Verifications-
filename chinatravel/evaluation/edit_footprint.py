"""Operational day/activity-position footprint, without semantic alignment."""
import math

ACTIVITY_FIELDS = (
    "type", "position", "start", "end", "start_time", "end_time", "price",
    "cost", "tickets", "rooms", "room_type", "TrainID", "FlightID",
)
TRANSPORT_FIELDS = (
    "from", "to", "start", "end", "mode", "type", "start_time", "end_time",
    "cost", "price", "distance", "duration", "tickets", "cars",
)
TYPES = {"airplane", "train", "attraction", "breakfast", "lunch", "dinner", "accommodation"}


def _fields(value, names):
    result = {}
    for name in names:
        if name not in value:
            continue
        item = value[name]
        if isinstance(item, str):
            item = item.strip()
        if item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("Non-scalar itinerary field")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Non-finite itinerary field")
        result[name] = item
    return result


def extract_itinerary_slots(plan):
    """Return {(explicit_day, zero_based_activity_position): canonical_value}.

    A full plan envelope or raw itinerary list is accepted. Invalid structure
    raises ValueError; the comparison helper converts it to unavailable metrics.
    Transport belongs to its destination activity, not a separate slot.
    """
    if isinstance(plan, dict):
        plan = plan.get("itinerary")
    if not isinstance(plan, list):
        raise ValueError("Expected itinerary list")
    slots, days = {}, set()
    for day in plan:
        if not isinstance(day, dict) or type(day.get("day")) is not int or day["day"] < 1:
            raise ValueError("Expected positive explicit day")
        number = day["day"]
        if number in days or not isinstance(day.get("activities"), list):
            raise ValueError("Duplicate day or invalid activities")
        days.add(number)
        for position, activity in enumerate(day["activities"]):
            if not isinstance(activity, dict) or activity.get("type") not in TYPES:
                raise ValueError("Invalid activity")
            if not all(isinstance(activity.get(key), str) for key in ("start_time", "end_time")):
                raise ValueError("Activity times unavailable")
            identity = ("start", "end") if activity["type"] in {"airplane", "train"} else ("position",)
            if not all(isinstance(activity.get(key), str) and activity[key].strip() for key in identity):
                raise ValueError("Activity identity unavailable")
            canonical = _fields(activity, ACTIVITY_FIELDS)
            transport = activity.get("transports")
            if transport is None or transport == "empty":
                transport = []
            if isinstance(transport, dict):
                transport = [transport] if transport else []
            if not isinstance(transport, list) or any(not isinstance(item, dict) for item in transport):
                raise ValueError("Invalid transports")
            for item in transport:
                endpoints = ("from", "to") if "from" in item or "to" in item else ("start", "end")
                if not all(isinstance(item.get(key), str) and item[key].strip() for key in endpoints) or not isinstance(item.get("mode", item.get("type")), str):
                    raise ValueError("Transport endpoints/mode unavailable")
            canonical["transports"] = [_fields(item, TRANSPORT_FIELDS) for item in transport]
            slots[(number, position)] = canonical
    return slots


def compare_edit_footprint(before, candidate):
    unavailable = dict(changed_slot_count=None, total_comparable_slots=None, changed_slot_rate=None)
    try:
        old, new = extract_itinerary_slots(before), extract_itinerary_slots(candidate)
    except (ValueError, TypeError):
        return unavailable
    keys = old.keys() | new.keys()
    changed = sum(key not in old or key not in new or old[key] != new[key] for key in keys)
    return dict(changed_slot_count=changed, total_comparable_slots=len(keys),
                changed_slot_rate=changed / len(keys) if keys else None)
