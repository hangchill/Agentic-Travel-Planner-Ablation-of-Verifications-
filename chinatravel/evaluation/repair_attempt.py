"""JSON logging contract for one completed repair proposal (1-based indices)."""

from dataclasses import asdict, dataclass, field, fields
import json
import math
from typing import Any
from copy import deepcopy


INTENT_FIELDS = (
    "target_constraint_indices", "target_constraint_labels", "target_provenance",
    "editable_scope", "scope_level", "feedback_personal_constraint_indices",
    "feedback_commonsense_failure_count", "protected_constraint_indices",
    "escalation_reason", "decision_reason",
)
DERIVED_FIELDS = ("concurrent_failed_constraint_indices", "concurrent_commonsense_failure_count")


def failed_constraint_indices(states: list[bool | None]) -> list[int]:
    """Original 1-based positions with exact FAIL, excluding UNKNOWN."""
    return [index for index, state in enumerate(states, 1) if state is False]


def normalize_repair_intent_metadata(metadata: dict, *, legacy_read=False) -> tuple[dict, dict]:
    """Extract canonical intent once, leaving only strategy/debug payload.

    Legacy whole_plan scope is unambiguous. Other legacy scope objects are
    preserved as legacy_scope_details rather than guessed. Validation of extracted
    canonical values belongs to RepairAttemptRecord.
    """
    if not isinstance(metadata, dict):
        raise ValueError("Repair metadata must be a dictionary")
    remaining = deepcopy(metadata)
    canonical_names = {item.name for item in fields(RepairAttemptRecord)} - {"repair_metadata"}
    extracted = {name: remaining.pop(name) for name in canonical_names if name in remaining}
    intent = extracted if legacy_read else {
        name: value for name, value in extracted.items()
        if name in (*INTENT_FIELDS, *DERIVED_FIELDS, "repair_strategy")}
    if "strategy" in remaining:
        intent["repair_strategy"] = remaining.pop("strategy")
    if "repair_strategy" in remaining:
        intent["repair_strategy"] = remaining.pop("repair_strategy")
    legacy = remaining.pop("scope", None)
    scope = intent.get("editable_scope", legacy)
    if scope == "whole_plan":
        scope = "plan"
    if ("editable_scope" not in intent or legacy_read) and scope not in (None, "slot", "day", "plan"):
        remaining["legacy_scope_details"] = scope
        scope = None
    if "editable_scope" in intent or legacy is not None:
        intent["editable_scope"] = scope
    return intent, remaining


@dataclass
class RepairAttemptRecord:
    step: int
    repair_strategy: str
    target_constraint_indices: list[int]
    target_constraint_labels: list[str]
    accepted: bool
    before_personal_constraints: list[bool | None]
    after_personal_constraints: list[bool | None]
    fixed: list[int]
    newly_violated: list[int]
    still_failed: list[int]
    still_passed: list[int]
    unknown: list[int]
    candidate_plan: Any
    accepted_plan_after: Any
    repair_metadata: dict
    input_tokens_before: int | None = None
    input_tokens_after: int | None = None
    input_tokens_delta: int | None = None
    output_tokens_before: int | None = None
    output_tokens_after: int | None = None
    output_tokens_delta: int | None = None
    repair_time_seconds: float | None = None
    exception: str | None = None
    query_uid: str | None = None
    constraint_descriptors: list[dict] = field(default_factory=list)
    target_provenance: str | None = None
    editable_scope: str | None = None
    scope_level: int | None = None
    concurrent_failed_constraint_indices: list[int] = field(default_factory=list)
    concurrent_commonsense_failure_count: int | None = None
    feedback_personal_constraint_indices: list[int] | None = None
    feedback_commonsense_failure_count: int | None = None
    protected_constraint_indices: list[int] = field(default_factory=list)
    escalation_reason: str | None = None
    decision_reason: str | None = None

    def __post_init__(self):
        # Constructor callers may still supply old debug metadata. Direct fields
        # take precedence; from_dict handles explicit-field presence exactly.
        intent, self.repair_metadata = normalize_repair_intent_metadata(self.repair_metadata)
        for name, value in intent.items():
            if name not in ("repair_strategy", "target_constraint_indices", "target_constraint_labels"):
                if getattr(self, name) is None or getattr(self, name) == []:
                    setattr(self, name, value)
        if isinstance(self.before_personal_constraints, list) and not self.concurrent_failed_constraint_indices:
            self.concurrent_failed_constraint_indices = failed_constraint_indices(self.before_personal_constraints)
        self.validate()

    def validate(self):
        if self.query_uid is not None and not isinstance(self.query_uid, str):
            raise ValueError("query_uid must be a string or None")
        if not isinstance(self.constraint_descriptors, list) or any(
            not isinstance(descriptor, dict) for descriptor in self.constraint_descriptors
        ):
            raise ValueError("constraint_descriptors must be a list of dictionaries")
        for index, descriptor in enumerate(self.constraint_descriptors, 1):
            if (type(descriptor.get("constraint_index")) is not int
                    or descriptor["constraint_index"] != index):
                raise ValueError("constraint_descriptors must use ordered 1-based indices")
            if "hard_logic_py" not in descriptor:
                raise ValueError("constraint descriptors must include hard_logic_py")
        if type(self.step) is not int or self.step < 1:
            raise ValueError("step must be a positive integer")
        if not isinstance(self.repair_strategy, str) or not self.repair_strategy:
            raise ValueError("repair_strategy must be a nonempty string")
        if type(self.accepted) is not bool:
            raise ValueError("accepted must be a bool")
        before, after = self.before_personal_constraints, self.after_personal_constraints
        for vector in (before, after):
            if not isinstance(vector, list) or any(
                value is not None and type(value) is not bool for value in vector
            ):
                raise ValueError("constraint vectors must be lists of bool or None")
        if len(before) != len(after):
            raise ValueError("constraint vector lengths must match")
        names = ("fixed", "newly_violated", "still_failed", "still_passed", "unknown")
        for name in ("target_constraint_indices", "concurrent_failed_constraint_indices",
                     "protected_constraint_indices", "feedback_personal_constraint_indices", *names):
            indices = getattr(self, name)
            if indices is None and name == "feedback_personal_constraint_indices":
                continue
            if not isinstance(indices, list) or any(
                type(i) is not int or not 1 <= i <= len(before) for i in indices
            ) or len(indices) != len(set(indices)):
                raise ValueError(f"{name} must contain unique 1-based constraint indices")
        expected = {name: [] for name in names}
        for i, (old, new) in enumerate(zip(before, after), 1):
            if old is None or new is None:
                name = "unknown"
            elif not old and new:
                name = "fixed"
            elif old and not new:
                name = "newly_violated"
            elif not old and not new:
                name = "still_failed"
            else:
                name = "still_passed"
            expected[name].append(i)
        for name in names:
            if sorted(getattr(self, name)) != expected[name]:
                raise ValueError(f"{name} does not match before/after constraint states")
        if not isinstance(self.target_constraint_labels, list) or any(
            not isinstance(label, str) for label in self.target_constraint_labels
        ):
            raise ValueError("target_constraint_labels must be a list of strings")
        if not isinstance(self.repair_metadata, dict):
            raise ValueError("repair_metadata must be a dict")
        reserved = {item.name for item in fields(self)} - {"repair_metadata"}
        if (reserved | {"strategy", "scope"}) & self.repair_metadata.keys():
            raise ValueError("Canonical fields belong on the record, not repair_metadata")
        for name in ("target_provenance", "escalation_reason", "decision_reason"):
            if getattr(self, name) is not None and not isinstance(getattr(self, name), str):
                raise ValueError(f"{name} must be a string or None")
        if self.editable_scope not in (None, "slot", "day", "plan"):
            raise ValueError("editable_scope must be slot/day/plan or None")
        if self.scope_level is not None:
            if type(self.scope_level) is not int or self.scope_level not in (1, 2, 3):
                raise ValueError("scope_level must be 1/2/3 or None")
            if self.editable_scope is not None and {1: "slot", 2: "day", 3: "plan"}[self.scope_level] != self.editable_scope:
                raise ValueError("scope_level and editable_scope disagree")
        for name in ("concurrent_commonsense_failure_count", "feedback_commonsense_failure_count"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a nonnegative integer or None")
        expected_failed = failed_constraint_indices(before)
        if self.concurrent_failed_constraint_indices != expected_failed:
            raise ValueError("Concurrent failures must match the before vector")
        for prefix in ("input", "output"):
            values = [getattr(self, f"{prefix}_tokens_{suffix}")
                      for suffix in ("before", "after", "delta")]
            if any(v is not None and (type(v) is not int or v < 0) for v in values):
                raise ValueError("token counts must be nonnegative integers or None")
            start, end, delta = values
            if start is not None and end is not None:
                if end < start or (delta is not None and delta != end - start):
                    raise ValueError("token counters and delta are inconsistent")
        duration = self.repair_time_seconds
        if duration is not None and (
            type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0
        ):
            raise ValueError("repair_time_seconds must be finite and nonnegative")
        if self.exception is not None and not isinstance(self.exception, str):
            raise ValueError("exception must be a string or None")
        # Reject non-JSON payloads and nonfinite values rather than losing data.
        json.dumps(asdict(self), allow_nan=False)

    def to_dict(self) -> dict:
        """Return a detached JSON-serializable snapshot, revalidating mutations."""
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "RepairAttemptRecord":
        """Load and validate a record; unknown fields are rejected."""
        if not isinstance(value, dict):
            raise ValueError("record must be a dict")
        unknown = set(value) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown record fields: {sorted(unknown)}")
        payload = deepcopy(value)
        intent, payload["repair_metadata"] = normalize_repair_intent_metadata(payload.get("repair_metadata", {}), legacy_read=True)
        for name, item in intent.items():
            payload.setdefault(name, item)
        if "concurrent_failed_constraint_indices" in payload and isinstance(payload.get("before_personal_constraints"), list):
            expected = failed_constraint_indices(payload["before_personal_constraints"])
            if payload["concurrent_failed_constraint_indices"] != expected:
                raise ValueError("Concurrent failures must match the before vector")
        return cls(**payload)


def coerce_repair_attempt(value: RepairAttemptRecord | dict) -> RepairAttemptRecord:
    """One validated input path shared by offline metrics and matrix analysis."""
    if isinstance(value, RepairAttemptRecord):
        value.validate()
        return value
    return RepairAttemptRecord.from_dict(value)
