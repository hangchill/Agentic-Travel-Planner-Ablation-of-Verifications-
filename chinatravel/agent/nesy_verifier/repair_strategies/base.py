
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


## Stores the result of one proposed repair.
@dataclass
class RepairResult:
    repaired_plan: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


## Common interface for all repair strategies (R0-R4).
class BaseRepairStrategy(ABC):

    ## Each strategy must implement how it generates a repair.
    @abstractmethod
    def repair(
        self,
        problem: dict,
        raw_plan: list,
        verification_results: dict,
        context: dict,
        llm: Any,
    ) -> RepairResult:
        pass

    ## Decide whether to accept a proposed repair.
    ## Default: accept the proposal, as R0 does.
    ## Other strategies can override this method.
    def accept(
        self,
        current_verification: dict,
        candidate_verification: dict,
    ) -> bool:
        return True
