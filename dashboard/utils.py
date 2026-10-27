"""Small presentation helpers; never execute persisted constraint code."""
import json
import math


def parsed(value, default=None):
    if isinstance(value, (list, dict)):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def present(value):
    if value is None or (isinstance(value, float) and math.isnan(value)) or value == '':
        return 'Unavailable'
    return value


def compact_verification(value):
    return {k: value[k] for k in ('personal_constraints', 'personal_errors', 'commonsense_errors',
                                 'schema_errors', 'verifier_errors', 'passed') if k in value}


def itinerary_rows(plan):
    days = plan.get('itinerary', []) if isinstance(plan, dict) else plan
    if not isinstance(days, list):
        return []
    return [dict(day=day.get('day', i + 1), **activity)
            for i, day in enumerate(days) if isinstance(day, dict)
            for activity in day.get('activities', []) if isinstance(activity, dict)]
