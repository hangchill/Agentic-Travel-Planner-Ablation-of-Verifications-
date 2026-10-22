"""Registered strategy factories; registration does not eagerly import models."""


def _r0():
    from .r0 import R0WholePlanRepair

    return R0WholePlanRepair()


def _r2():
    from .r2 import R2ProtectedRepair

    return R2ProtectedRepair()


STRATEGY_FACTORIES = {"R0": _r0, "R2": _r2}


def create_repair_strategy(name):
    try:
        factory = STRATEGY_FACTORIES[name]
    except KeyError as exc:
        raise ValueError(f"Repair strategy {name!r} is unavailable; registered: {sorted(STRATEGY_FACTORIES)}") from exc
    return factory()
