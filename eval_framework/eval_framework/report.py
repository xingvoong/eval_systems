from dataclasses import dataclass


@dataclass
class _PhaseResult:
    phase: str
    passed: int
    total: int
    threshold: int


class Report:
    def __init__(self) -> None:
        self._phases: list[_PhaseResult] = []

    def add_result(self, phase: str, passed: int, total: int, threshold: int) -> None:
        self._phases.append(_PhaseResult(phase=phase, passed=passed, total=total, threshold=threshold))

    def print_summary(self) -> None:
        print(f"\n{'─'*60}")
        print(f"{'Phase':<20} {'Passed':<10} {'Total':<10} {'Threshold':<12} Status")
        print(f"{'─'*60}")
        for r in self._phases:
            status = "✓ PASS" if r.passed >= r.threshold else "✗ FAIL"
            print(f"{r.phase:<20} {r.passed:<10} {r.total:<10} {r.threshold:<12} {status}")
        print(f"{'─'*60}\n")

    def exit_code(self) -> int:
        for r in self._phases:
            if r.passed < r.threshold:
                return 1
        return 0
