"""Registered strategy factories; registration does not eagerly import models."""


def _r0():
    from .r0 import R0WholePlanRepair

    return R0WholePlanRepair()


def _r1():
    from .r1 import R1TargetedRepair

    return R1TargetedRepair()

def _r2():
    from .r2 import R2ProtectedRepair

    return R2ProtectedRepair()

def _r3():
    from .r3 import R3AdaptiveScopeRepair

    return R3AdaptiveScopeRepair()


def _r3p():
    from .r3 import R3AdaptiveScopeRepair

    return R3AdaptiveScopeRepair(phased=True)


def _r4():
    import os
    from .r4 import MatrixGuidedRepair

    path = os.environ.get("CHINATRAVEL_R4_MATRIX")
    if not path:
        raise ValueError("R4 requires CHINATRAVEL_R4_MATRIX; use r4/run_r4.py for guarded pilot runs")
    return MatrixGuidedRepair(path)


STRATEGY_FACTORIES = {"R0": _r0, "R1": _r1, "R2": _r2, "R3": _r3, "R3P": _r3p, "R4": _r4}


def create_repair_strategy(name):
    try:
        factory = STRATEGY_FACTORIES[name]
    except KeyError as exc:
        raise ValueError(f"Repair strategy {name!r} is unavailable; registered: {sorted(STRATEGY_FACTORIES)}") from exc
    return factory()
