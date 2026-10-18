"""Context-local accounting of public tools and top-level verifier executions."""
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from time import perf_counter

_active = ContextVar("chinatravel_system_usage", default=None)
_verification_depth = ContextVar("chinatravel_verification_depth", default=0)


class SystemUsage:
    def __init__(self):
        self.tools = Counter()
        self.successful = self.failed = self.verifications = 0

    def snapshot(self):
        return {"tool_call_count": sum(self.tools.values()),
                "tool_call_counts_by_type": dict(sorted(self.tools.items())),
                "successful_tool_call_count": self.successful,
                "failed_tool_call_count": self.failed,
                "verification_count": self.verifications}


@contextmanager
def system_usage_scope():
    """Reuse the enclosing query/strategy collector; isolate independent runs."""
    existing = _active.get()
    if existing is not None:
        yield existing
        return
    token = _active.set(SystemUsage())
    try:
        yield _active.get()
    finally:
        _active.reset(token)


def system_snapshot():
    usage = _active.get()
    return usage.snapshot() if usage is not None else None


def system_delta(before, after):
    if before is None or after is None:
        return {name: None for name in ("tool_call_count", "tool_call_counts_by_type",
                "successful_tool_call_count", "failed_tool_call_count", "verification_count")}
    result = {name: after[name] - before[name] for name in before if name != "tool_call_counts_by_type"}
    result["tool_call_counts_by_type"] = {
        name: count - before["tool_call_counts_by_type"].get(name, 0)
        for name, count in after["tool_call_counts_by_type"].items()
        if count != before["tool_call_counts_by_type"].get(name, 0)}
    return result


def tool_api(name):
    """Decorate the actual public API, never the dispatcher or its helpers."""
    def decorate(function):
        @wraps(function)
        def invoke(*args, **kwargs):
            usage = _active.get()
            if usage is None:
                return function(*args, **kwargs)
            usage.tools[name] += 1
            try:
                result = function(*args, **kwargs)
            except BaseException:
                usage.failed += 1
                raise
            usage.successful += 1
            return result
        return invoke
    return decorate


def verification_execution(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        usage = _active.get()
        depth = _verification_depth.get()
        if usage is not None and depth == 0:
            usage.verifications += 1
        token = _verification_depth.set(depth + 1)
        try:
            return function(*args, **kwargs)
        finally:
            _verification_depth.reset(token)
    return invoke


def measured_repair_pipeline(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        with system_usage_scope() as usage:
            before = usage.snapshot()
            started = perf_counter()
            result = function(*args, **kwargs)
            metrics = system_delta(before, usage.snapshot())
            metrics["total_execution_time_s"] = perf_counter() - started
            result["history"][0]["pipeline_system_metrics"] = metrics
            return result
    return invoke
