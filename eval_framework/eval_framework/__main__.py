"""
eval_framework CLI

Usage:
    python -m eval_framework --system llm_gateway --phase routing
    python -m eval_framework --system synack_agent --phase guardrail
    python -m eval_framework --system synack_agent        # all phases
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

from eval_framework.case import EvalCase
from eval_framework.report import Report

EVALS_DIR = Path(__file__).parents[1] / "evals"
SYSTEMS_DIR = Path(__file__).parents[1] / "systems"


def load_adapter(system: str):
    """Auto-discover adapter from systems/ by filename stem.

    Drop systems/my_system.py with a BaseSystemAdapter subclass and it's
    immediately available as --system my_system. No registration required.
    """
    import importlib.util
    import inspect
    from eval_framework.adapter import BaseSystemAdapter

    adapter_path = SYSTEMS_DIR / f"{system}.py"
    if not adapter_path.exists():
        available = sorted(p.stem for p in SYSTEMS_DIR.glob("*.py") if not p.stem.startswith("_"))
        raise ValueError(
            f"No adapter found for '{system}'. "
            f"Available: {', '.join(available)}. "
            f"Add systems/{system}.py with a BaseSystemAdapter subclass to register it."
        )

    spec = importlib.util.spec_from_file_location(system, adapter_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for _, cls in inspect.getmembers(module, inspect.isclass):
        if issubclass(cls, BaseSystemAdapter) and cls is not BaseSystemAdapter:
            return cls()

    raise ValueError(f"systems/{system}.py has no BaseSystemAdapter subclass.")


def load_cases_from_json(path: Path, phase_type: str) -> list[EvalCase]:
    with open(path) as f:
        raw = json.load(f)

    cases = []
    for item in raw:
        cid = item["id"]

        if phase_type in ("deterministic", "routing"):
            # routing_cases.json: input=prompt, expected=expected_model
            inp = item.get("prompt", item.get("input", ""))
            expected = item.get("expected_model", item.get("expected", None))
            metadata = {
                k: v for k, v in item.items()
                if k not in ("id", "prompt", "input", "expected_model", "expected")
            }
            cases.append(EvalCase(id=cid, input=inp, expected=expected, metadata=metadata))

        elif phase_type == "guardrail":
            # guardrail_cases.json: category field distinguishes input vs output
            category = item.get("category", "input")
            if category == "input":
                inp = item.get("input", "")
                expected_blocked = not item.get("expected_valid", True)
            else:
                inp = item.get("output", "")
                expected_blocked = not item.get("expected_safe", True)
            cases.append(EvalCase(
                id=cid,
                input=inp,
                expected_blocked=expected_blocked,
                metadata={"category": category, "notes": item.get("notes", "")},
            ))

        elif phase_type == "judge":
            inp = item.get("prompt", item.get("input", ""))
            cases.append(EvalCase(
                id=cid,
                input=inp,
                metadata={
                    "response": item.get("response", ""),
                    "reference_response": item.get("reference_response", ""),
                    "quality_level": item.get("quality_level", ""),
                },
            ))

    return cases


def run_routing_phase(adapter, cases: list[EvalCase], threshold: int, report: Report) -> None:
    """
    Special handler for routing — uses adapter.route() to get model+reason,
    checks exact model match against expected.
    """
    from eval_framework.case import EvalResult

    passed = 0
    results = []

    print(f"\nRouting eval — {adapter.name} — {len(cases)} cases\n")
    print(f"{'ID':<10} {'Status':<8} {'Expected':<42} {'Actual':<42} Notes")
    print(f"{'─'*110}")

    for case in cases:
        metadata = case.metadata
        priority = metadata.get("request_metadata", {}).get("priority") if "request_metadata" in metadata else None
        max_cost = metadata.get("request_metadata", {}).get("max_cost") if "request_metadata" in metadata else None

        actual_model, actual_reason = adapter.route(case.input, priority=priority, max_cost=max_cost)
        expected_model = case.expected
        expected_reason = metadata.get("expected_routing_reason", "")

        model_ok = actual_model == expected_model
        reason_ok = actual_reason == expected_reason
        ok = model_ok and reason_ok

        result = EvalResult(
            case_id=case.id,
            passed=ok,
            actual=actual_model,
            expected=expected_model,
            notes="" if ok else (
                f"model: expected '{expected_model}' got '{actual_model}'" if not model_ok else
                f"reason: expected '{expected_reason}' got '{actual_reason}'"
            ),
        )
        results.append(result)
        if ok:
            passed += 1

        marker = "✓ PASS" if ok else "✗ FAIL"
        short_exp = (expected_model or "").replace("mistralai/", "")
        short_act = actual_model.replace("mistralai/", "") if actual_model else ""
        print(f"{case.id:<10} {marker:<8} {short_exp:<42} {short_act:<42} {result.notes[:40]}")

    print(f"{'─'*110}")
    print(f"Passed: {passed}/{len(cases)}\n")
    report.add_result("routing", passed, len(cases), threshold)


def run_judge_phase(adapter, cases: list[EvalCase], phase_name: str, judge_model: str, report: Report) -> None:
    from eval_framework.judge import LLMJudge

    judge = LLMJudge(model=judge_model)

    dims_key = list(cases[0].metadata.get("quality_dimensions", ["accuracy", "completeness", "conciseness"])
                    if cases else ["accuracy", "completeness", "conciseness"])

    print(f"\nJudge eval — {adapter.name} — {phase_name} — {len(cases)} cases\n")
    print(f"{'ID':<10} {'Level':<10} {'Accuracy':<10} {'Complete':<10} {'Concise':<10} Avg  Reasoning")
    print(f"{'─'*90}")

    rows = []
    for case in cases:
        scores = judge.score(
            prompt=case.input,
            reference=case.metadata.get("reference_response", ""),
            candidate=case.metadata.get("response", ""),
        )
        avg = round((scores.get("accuracy", scores.get("correctness", 0)) +
                     scores.get("completeness", 0) +
                     scores.get("conciseness", 0)) / 3, 1)
        level = case.metadata.get("quality_level", "")
        acc = scores.get("accuracy", scores.get("correctness", 0))
        comp = scores.get("completeness", 0)
        conc = scores.get("conciseness", 0)
        print(f"{case.id:<10} {level:<10} {acc:<10} {comp:<10} {conc:<10} {avg:<5} {scores.get('reasoning', '')[:40]}")
        rows.append((level, avg))

    print(f"{'─'*90}")

    for lvl in ["good", "mediocre", "bad"]:
        lvl_rows = [r for r in rows if r[0] == lvl]
        if lvl_rows:
            avg = round(sum(r[1] for r in lvl_rows) / len(lvl_rows), 1)
            print(f"  {lvl:<10} avg: {avg}")

    # Judge evals don't have a pass/fail threshold — record as informational
    report.add_result(phase_name, len(cases), len(cases), 0)


def run_deterministic_phase(adapter, cases: list[EvalCase], phase_name: str, threshold: int, report: Report) -> None:
    """General deterministic phase — calls adapter.call() and checks expected string is in output."""
    from eval_framework.case import EvalResult

    passed = 0
    print(f"\nDeterministic eval — {adapter.name} — {phase_name} — {len(cases)} cases\n")
    print(f"{'ID':<10} {'Status':<8} {'Expected':<30} {'Actual':<40} Notes")
    print(f"{'─'*100}")

    for case in cases:
        actual = adapter.call(case.input)
        expected = case.expected or ""
        ok = expected in actual

        if ok:
            passed += 1
        marker = "✓ PASS" if ok else "✗ FAIL"
        notes = "" if ok else f"expected '{expected}' not in output"
        print(f"{case.id:<10} {marker:<8} {expected[:30]:<30} {actual[:40]:<40} {notes}")

    print(f"{'─'*100}")
    print(f"Passed: {passed}/{len(cases)}\n")
    report.add_result(phase_name, passed, len(cases), threshold)


def run_phase(phase_cfg: dict, adapter, cases_dir: Path, report: Report) -> None:
    name = phase_cfg["name"]
    ptype = phase_cfg["type"]
    threshold = phase_cfg.get("threshold", 0)
    cases_path = cases_dir / phase_cfg["cases"]
    cases = load_cases_from_json(cases_path, ptype)

    if ptype == "deterministic":
        run_deterministic_phase(adapter, cases, name, threshold, report)
    elif ptype == "routing":
        run_routing_phase(adapter, cases, threshold, report)
    elif ptype == "guardrail":
        from eval_framework.runner import run_guardrail
        passed, total, _ = run_guardrail(adapter, cases)
        report.add_result(name, passed, total, threshold)
    elif ptype == "judge":
        import os
        if not os.environ.get("GROQ_API_KEY"):
            print(f"\nSkipping judge phase '{name}' — GROQ_API_KEY not set\n")
            return
        judge_model = phase_cfg.get("judge_model", "openai/gpt-oss-20b")
        run_judge_phase(adapter, cases, name, judge_model, report)
    else:
        raise ValueError(f"Unknown phase type '{ptype}'")


def main() -> int:
    available = sorted(p.stem for p in SYSTEMS_DIR.glob("*.py") if not p.stem.startswith("_"))
    parser = argparse.ArgumentParser(description="Pluggable eval runner")
    parser.add_argument("--system", required=True,
                        help=f"System to evaluate. Available: {', '.join(available)}")
    parser.add_argument("--phase", default=None, help="Phase name to run (omit to run all)")
    parser.add_argument("--save-baseline", action="store_true",
                        help="Save this run's results as the baseline for future regression checks")
    parser.add_argument("--baseline", action="store_true",
                        help="Compare this run against the saved baseline — fail if any phase regressed")
    args = parser.parse_args()

    config_path = EVALS_DIR / args.system / "config.yaml"
    if not config_path.exists():
        print(f"ERROR: no config at {config_path}")
        return 1

    with open(config_path) as f:
        config = yaml.safe_load(f)

    cases_dir = EVALS_DIR / args.system

    adapter = load_adapter(args.system)
    report = Report()

    phases = config["phases"]
    if args.phase:
        phases = [p for p in phases if p["name"] == args.phase]
        if not phases:
            print(f"ERROR: phase '{args.phase}' not found in config")
            return 1

    for phase_cfg in phases:
        run_phase(phase_cfg, adapter, cases_dir, report)

    report.print_summary()

    if args.save_baseline:
        baseline_path = EVALS_DIR / args.system / "baseline.json"
        with open(baseline_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"Baseline saved to {baseline_path}")

    if args.baseline:
        baseline_path = EVALS_DIR / args.system / "baseline.json"
        if not baseline_path.exists():
            print(f"ERROR: no baseline at {baseline_path}. Run with --save-baseline first.")
            return 1
        with open(baseline_path) as f:
            baseline = json.load(f)
        regression_code = report.compare_to_baseline(baseline)
        return max(report.exit_code(), regression_code)

    return report.exit_code()


if __name__ == "__main__":
    sys.exit(main())
