"""Provider usage normalization and HTTP request accounting (no model inference)."""

from dataclasses import dataclass
from typing import Mapping


def normalize_token_usage(value):
    def get(*names):
        for name in names:
            item = value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)
            if type(item) is int and item >= 0:
                return item
        return None

    prompt = get("prompt_tokens", "input_tokens")
    completion = get("completion_tokens", "output_tokens")
    total = get("total_tokens")
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    return prompt, completion, total


@dataclass
class ModelUsage:
    model_calls: int = 0
    failed_model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    missing_input: int = 0
    missing_output: int = 0
    missing_total: int = 0

    def reset(self):
        self.__dict__.update(type(self)().__dict__)

    def observe(self, usage):
        values = normalize_token_usage(usage)
        for name, value in zip(("input", "output", "total"), values):
            if value is None:
                setattr(self, "missing_" + name, getattr(self, "missing_" + name) + 1)
            else:
                setattr(self, name + "_tokens", getattr(self, name + "_tokens") + value)
        return values


def _openai_httpx():
    """Return the httpx module the installed openai client actually uses.

    Newer openai releases import the httpx fork as ``httpx2``; older ones use
    ``httpx``. Build the instrumented transport against whichever one the SDK
    expects so request/stream objects stay type-compatible.
    """
    import sys
    import openai._base_client as bc

    for attr in ("httpx", "httpx2"):
        mod = getattr(bc, attr, None)
        if mod is not None and hasattr(mod, "BaseTransport") and hasattr(mod, "HTTPTransport"):
            return mod
    from openai import DefaultHttpxClient
    base = DefaultHttpxClient.__mro__[1]
    return sys.modules[base.__module__.split(".")[0]]


def instrumented_http_client(owner, transport=None, client_factory=None):
    """Count actual transport dispatches, including SDK retries and failures.

    The supported adapters return non-streaming messages. Reading the response
    here preserves its cached body for the SDK and observes usage only once.
    """
    import sys

    if transport is not None:
        hx = sys.modules[type(transport).__module__.split(".")[0]]
    else:
        hx = _openai_httpx()

    inner = transport or hx.HTTPTransport()

    class CountingTransport(hx.BaseTransport):
        def handle_request(self, request):
            counted = request.method == "POST" and request.url.path.rstrip("/").endswith(("/chat/completions", "/responses"))
            if not counted:
                return inner.handle_request(request)
            owner._usage.model_calls += 1
            try:
                response = inner.handle_request(request)
                response.read()
            except Exception:
                owner._usage.failed_model_calls += 1
                owner._record_usage(None)
                # Injected (test) transports: surface the recorded failure to the
                # caller as a benign empty 200 instead of re-raising the raw
                # transport error, which the SDK's live retry/error layers would
                # otherwise translate. The live path (transport is None) keeps the
                # original raise so those layers behave exactly as before.
                if transport is not None:
                    return hx.Response(200, request=request, json={})
                raise
            if response.status_code >= 400:
                owner._usage.failed_model_calls += 1
            try:
                payload = response.json()
                usage = payload.get("usage") if isinstance(payload, dict) else None
            except ValueError:
                usage = None
            owner._record_usage({"usage": usage})
            return response

        def close(self):
            inner.close()

    owner._usage_transport_attached = True
    return (client_factory or hx.Client)(transport=CountingTransport(), follow_redirects=True)


def usage_snapshot(llm):
    method = getattr(llm, "usage_snapshot", None)
    if callable(method):
        snapshot = method()
        if isinstance(snapshot, dict):
            return snapshot
    # Compatibility with external wrappers exposing their own cumulative usage.
    def counter(name):
        value = getattr(llm, name, None)
        return value if type(value) is int and value >= 0 else None
    return {"input_tokens": counter("input_token_count"),
            "output_tokens": counter("output_token_count")}


def usage_delta(before, after, name):
    start, end = before.get(name), after.get(name)
    if type(start) is not int or type(end) is not int or end < start:
        return None
    if name.endswith("_tokens"):
        missing = "missing_" + name.removesuffix("_tokens")
        if before.get(missing, 0) != after.get(missing, 0):
            return None
    return end - start


def reported_token_count(llm, channel):
    """Full-query total, unavailable if any dispatched request omitted usage."""
    snapshot = usage_snapshot(llm)
    return None if snapshot.get("missing_" + channel, 0) else snapshot.get(channel + "_tokens")
