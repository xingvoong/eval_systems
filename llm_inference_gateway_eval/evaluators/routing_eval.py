"""
Phase 3 — Routing Evaluator

Runs each case in data/routing_cases.json through the gateway's
routing logic and checks:
  - did the right model get picked?
  - did the right rule fire?

LLM provider calls are mocked — no real API calls made.
The classifier runs for Rule 3 cases (model already cached from Phase 1).

Run from llm_inference_gateway_eval/:
  python evaluators/routing_eval.py
"""

import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add the gateway repo to the path so we can import its routing logic directly
GATEWAY_PATH = Path(__file__).parents[3] / "llm_inference_gateway"
sys.path.insert(0, str(GATEWAY_PATH))


def load_cases():
    cases_path = Path(__file__).parents[1] / "data" / "routing_cases.json"
    with open(cases_path) as f:
        return json.load(f)


def run_case(case):
    """
    Runs a single routing case through the gateway's route_request().
    Mocks out OpenAIProvider and HuggingFaceProvider so no real API calls happen.
    Returns (actual_model, actual_reason, passed, failure_reason).
    """
    prompt = case["prompt"]
    priority = case["request_metadata"].get("priority")
    max_cost = case["request_metadata"].get("max_cost")
    expected_model = case["expected_model"]
    expected_reason = case["expected_routing_reason"]

    mock_openai = MagicMock()
    mock_hf = MagicMock()

    # Mock providers — route_request returns (provider, model_name, reason)
    # We only care about model_name and reason, not the provider instance
    with patch("app.router.OpenAIProvider", return_value=mock_openai) as MockOAI, \
         patch("app.router.HuggingFaceProvider", return_value=mock_hf) as MockHF:

        # Make the mock constructors record what model they were called with
        MockOAI.side_effect = lambda model: MagicMock(_model=model)
        MockHF.side_effect = lambda model: MagicMock(_model=model)

        from app.router import route_request
        _, actual_model, actual_reason = route_request(
            prompt=prompt,
            priority=priority,
            max_cost=max_cost,
        )

    # Check model match
    model_match = actual_model == expected_model

    # Check reason match — use prefix match for zero_shot cases
    # e.g. expected "zero_shot:question answering" matches actual "zero_shot:question answering"
    reason_match = actual_reason == expected_reason

    passed = model_match and reason_match

    failure_reason = None
    if not passed:
        parts = []
        if not model_match:
            parts.append(f"model: expected '{expected_model}' got '{actual_model}'")
        if not reason_match:
            parts.append(f"reason: expected '{expected_reason}' got '{actual_reason}'")
        failure_reason = " | ".join(parts)

    return actual_model, actual_reason, passed, failure_reason


def main():
    cases = load_cases()

    print(f"Running {len(cases)} routing cases...\n")
    print(f"{'ID':<8} {'Result':<8} {'Expected Model':<40} {'Actual Model':<40} {'Notes'}")
    print("-" * 140)

    passed = 0
    failed = 0
    failures = []

    for case in cases:
        actual_model, actual_reason, ok, failure_reason = run_case(case)
        status = "PASS ✓" if ok else "FAIL ✗"

        short_expected = case["expected_model"].replace("mistralai/", "")
        short_actual = actual_model.replace("mistralai/", "")

        print(f"{case['id']:<8} {status:<8} {short_expected:<40} {short_actual:<40} {failure_reason or ''}")

        if ok:
            passed += 1
        else:
            failed += 1
            failures.append(case)

    print("-" * 140)
    print(f"\nResults: {passed}/{len(cases)} passed ({passed/len(cases):.0%})\n")

    if failures:
        print("Failed cases:")
        for case in failures:
            print(f"  {case['id']} — {case['prompt'][:70]}")
            print(f"           note: {case['notes']}")
        print()

    # Per-rule breakdown
    rule_results = {
        "priority==high": {"pass": 0, "fail": 0},
        "max_cost<0.01": {"pass": 0, "fail": 0},
        "zero_shot": {"pass": 0, "fail": 0},
        "conflict": {"pass": 0, "fail": 0},
    }

    for case in cases:
        _, _, ok, _ = run_case(case)
        reason = case["expected_routing_reason"]
        if "priority==high" in reason and case["request_metadata"].get("max_cost") is not None:
            key = "conflict"
        elif "priority==high" in reason:
            key = "priority==high"
        elif "max_cost" in reason:
            key = "max_cost<0.01"
        else:
            key = "zero_shot"

        rule_results[key]["pass" if ok else "fail"] += 1

    print("Per-rule breakdown:")
    print(f"  {'Rule':<20} {'Pass':<6} {'Fail':<6}")
    print(f"  {'────':<20} {'────':<6} {'────':<6}")
    for rule, counts in rule_results.items():
        total = counts["pass"] + counts["fail"]
        if total > 0:
            print(f"  {rule:<20} {counts['pass']:<6} {counts['fail']:<6}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
