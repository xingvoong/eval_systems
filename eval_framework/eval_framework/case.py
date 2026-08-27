from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalCase:
    id: str
    input: str
    expected: str | None = None          # for deterministic evals
    expected_blocked: bool | None = None  # for guardrail evals
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    actual: str
    expected: str | None
    notes: str = ""
