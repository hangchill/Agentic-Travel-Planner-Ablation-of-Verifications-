"""JSON logging contract for one completed repair proposal (1-based indices)."""

from dataclasses import asdict, dataclass, field, fields
import json
import math
from typing import Any


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

    def __post_init__(self):
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
        for name in ("target_constraint_indices", *names):
            indices = getattr(self, name)
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
        from copy import deepcopy

        return cls(**deepcopy(value))
