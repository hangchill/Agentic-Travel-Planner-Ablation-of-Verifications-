"""Registered strategy factories; registration does not eagerly import models."""


def _r0():
    from .r0 import R0WholePlanRepair

    return R0WholePlanRepair()

def _r1():
    from .r1 import R1TargetedRepair
    return R1TargetedRepair()

STRATEGY_FACTORIES = {"R0": _r0, "R1": _r1,}

def create_repair_strategy(name):
    try:
        factory = STRATEGY_FACTORIES[name]
    except KeyError as exc:
        raise ValueError(f"Repair strategy {name!r} is unavailable; registered: {sorted(STRATEGY_FACTORIES)}") from exc
    return factory()
