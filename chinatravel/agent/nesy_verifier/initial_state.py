"""Serializable snapshot shared by independent repair runs."""

from dataclasses import asdict, dataclass, field


@dataclass
class InitialRepairState:
    query_uid: str | None
    problem: dict
    raw_initial_plan: list
    repair_context: dict
    initial_verification: dict | None = None
    environment_context: dict = field(default_factory=dict)
    generation_metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        from copy import deepcopy

        return cls(**deepcopy(value))
