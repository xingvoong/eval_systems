"""
Phase 6 — Judge Consistency

Runs the same (prompt, response) pair through the judge 5 times at
temperature=0 and measures score variance across runs.

A reliable judge should return the same score every time on the same input.
Cases with variance > 0.5 are flagged as unreliable.

Run from llm_inference_gateway_eval/:
  python evaluator_validation/judge_consistency.py
"""

import json
import os
import sys
import requests
import statistics
from pathlib import Path

GATEWAY_ENV = Path(__file__).parents[3] / "llm_inference_gateway" / ".env"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
JUDGE_MODEL = "anthropic/claude-haiku-4-5"
RUNS = 5

JUDGE_SYSTEM = """You are an expert evaluator of LLM responses.
You will be given a user prompt, a reference response (considered correct and complete),
and a candidate response to evaluate.

Score the candidate on each dimension from 1 to 5:
  correctness  — Is the answer factually or functionally correct?
  completeness — Does it address all parts of the prompt?
  conciseness  — Is it appropriately brief without omitting essentials?

Return ONLY valid JSON with no extra text:
{"correctness": <int>, "completeness": <int>, "conciseness": <int>, "reasoning": "<one sentence>"}"""

JUDGE_USER_TEMPLATE = """Prompt:
{prompt}

Reference response:
{reference}

Candidate response:
{candidate}

Score the candidate response."""


def load_env(path):
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_cases():
    path = Path(__file__).parents[1] / "data" / "quality_cases.json"
    with open(path) as f:
        return json.load(f)


def call_judge(api_key, prompt, reference, candidate):
    user_msg = JUDGE_USER_TEMPLATE.format(
        prompt=prompt, reference=reference, candidate=candidate
    )
    response = requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": JUDGE_MODEL,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 256,
        },
    )
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def main():
    load_env(GATEWAY_ENV)
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY not set.")
        sys.exit(1)

    cases = load_cases()
    # Run on a representative subset: one good, one bad, one mediocre
    subset = [c for c in cases if c["id"] in ("q_001", "q_002", "q_004", "q_006", "q_010")]

    print(f"Running each case {RUNS}x at temperature=0...\n")
    print(f"{'ID':<8} {'Level':<10} {'Correct scores':<30} {'Var':<8} {'Complete scores':<30} {'Var':<8} {'Concise scores':<30} {'Var':<8} {'Stable?'}")
    print("-" * 145)

    unstable = []

    for case in subset:
        correct_scores, complete_scores, concise_scores = [], [], []

        for _ in range(RUNS):
            scores = call_judge(
                api_key,
                case["prompt"],
                case["reference_response"],
                case["response"],
            )
            correct_scores.append(scores["correctness"])
            complete_scores.append(scores["completeness"])
            concise_scores.append(scores["conciseness"])

        var_c = statistics.variance(correct_scores) if len(set(correct_scores)) > 1 else 0.0
        var_p = statistics.variance(complete_scores) if len(set(complete_scores)) > 1 else 0.0
        var_n = statistics.variance(concise_scores) if len(set(concise_scores)) > 1 else 0.0
        max_var = max(var_c, var_p, var_n)
        stable = "✓" if max_var <= 0.5 else "✗ UNSTABLE"

        if max_var > 0.5:
            unstable.append(case["id"])

        print(
            f"{case['id']:<8} {case['quality_level']:<10} "
            f"{str(correct_scores):<30} {var_c:<8.2f} "
            f"{str(complete_scores):<30} {var_p:<8.2f} "
            f"{str(concise_scores):<30} {var_n:<8.2f} "
            f"{stable}"
        )

    print("-" * 145)
    print(f"\nUnstable cases (variance > 0.5): {len(unstable)}/{len(subset)}")
    if unstable:
        print(f"  {unstable}")
    else:
        print("  None — judge is consistent at temperature=0")

    return 0 if not unstable else 1


if __name__ == "__main__":
    sys.exit(main())
