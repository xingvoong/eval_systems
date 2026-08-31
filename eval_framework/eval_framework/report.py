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

    def to_dict(self) -> dict:
        return {
            "phases": [
                {"phase": r.phase, "passed": r.passed, "total": r.total, "threshold": r.threshold}
                for r in self._phases
            ]
        }

    def compare_to_baseline(self, baseline: dict) -> int:
        """Compare current results against a saved baseline.

        Prints a regression report and returns 1 if any phase regressed, 0 otherwise.
        A regression is when passed count drops below the baseline.
        """
        baseline_by_phase = {p["phase"]: p for p in baseline.get("phases", [])}
        regressions = []

        print(f"\n{'─'*60}")
        print(f"{'Phase':<20} {'Baseline':<12} {'Current':<12} Status")
        print(f"{'─'*60}")

        for r in self._phases:
            b = baseline_by_phase.get(r.phase)
            if b is None:
                print(f"{r.phase:<20} {'(new)':<12} {r.passed:<12} --")
                continue
            delta = r.passed - b["passed"]
            if delta < 0:
                status = f"✗ REGRESSED ({delta})"
                regressions.append(r.phase)
            elif delta > 0:
                status = f"↑ improved (+{delta})"
            else:
                status = "✓ no change"
            print(f"{r.phase:<20} {b['passed']:<12} {r.passed:<12} {status}")

        print(f"{'─'*60}")
        if regressions:
            print(f"\nREGRESSION DETECTED in: {', '.join(regressions)}\n")
            return 1
        print("\nNo regressions.\n")
        return 0
