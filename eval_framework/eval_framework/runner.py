from eval_framework.adapter import BaseSystemAdapter
from eval_framework.case import EvalCase, EvalResult


def run_deterministic(adapter: BaseSystemAdapter, cases: list[EvalCase]) -> tuple[int, int, list[EvalResult]]:
    """
    For each case: call adapter.call(input), check that expected string appears in output.
    Returns (passed_count, total_count, results).
    """
    results = []
    passed = 0

    print(f"\nDeterministic eval — {adapter.name} — {len(cases)} cases\n")
    print(f"{'ID':<10} {'Status':<8} {'Expected':<35} {'Notes'}")
    print(f"{'─'*80}")

    for case in cases:
        actual = adapter.call(case.input)
        ok = case.expected is not None and case.expected in actual
        result = EvalResult(
            case_id=case.id,
            passed=ok,
            actual=actual,
            expected=case.expected,
            notes="" if ok else f"expected '{case.expected}' not in '{actual[:40]}'"
        )
        results.append(result)
        if ok:
            passed += 1

        marker = "✓ PASS" if ok else "✗ FAIL"
        exp_short = (case.expected or "")[:34]
        print(f"{case.id:<10} {marker:<8} {exp_short:<35} {result.notes[:40]}")

    print(f"{'─'*80}")
    print(f"Passed: {passed}/{len(cases)}\n")
    return passed, len(cases), results


def run_guardrail(adapter: BaseSystemAdapter, cases: list[EvalCase]) -> tuple[int, int, list[EvalResult]]:
    """
    For each case: call validate_input() or scan_output() depending on metadata.
    Checks actual blocked state matches expected_blocked.
    Returns (passed_count, total_count, results).
    """
    results = []
    passed = 0

    print(f"\nGuardrail eval — {adapter.name} — {len(cases)} cases\n")
    print(f"{'ID':<10} {'Category':<10} {'Status':<8} {'Notes'}")
    print(f"{'─'*72}")

    for case in cases:
        category = case.metadata.get("category", "input")

        if category == "output":
            is_safe, reason = adapter.scan_output(case.input)
            actual_blocked = not is_safe
        else:
            is_valid, reason = adapter.validate_input(case.input)
            actual_blocked = not is_valid

        ok = (actual_blocked == case.expected_blocked)
        result = EvalResult(
            case_id=case.id,
            passed=ok,
            actual=str(actual_blocked),
            expected=str(case.expected_blocked),
            notes=reason if not ok else ""
        )
        results.append(result)
        if ok:
            passed += 1

        marker = "✓ PASS" if ok else "✗ FAIL"
        print(f"{case.id:<10} {category:<10} {marker:<8} {result.notes[:45]}")

    print(f"{'─'*72}")
    print(f"Passed: {passed}/{len(cases)}\n")
    return passed, len(cases), results
