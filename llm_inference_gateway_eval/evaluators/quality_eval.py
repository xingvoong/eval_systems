"""
Phase 5 — Response Quality Evaluator (LLM-as-Judge)

Scores each response in data/quality_cases.json using Claude via OpenRouter.
Judge receives: prompt + reference response + candidate response.
Returns structured JSON scores on three dimensions.

Setup:
  pip install requests
  OPENROUTER_API_KEY is loaded from llm_inference_gateway/.env automatically

Run from llm_inference_gateway_eval/:
  python evaluators/quality_eval.py
"""

import json
import os
import sys
import requests
from pathlib import Path

GATEWAY_ENV = Path(__file__).parents[3] / "llm_inference_gateway" / ".env"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
JUDGE_MODEL = "anthropic/claude-haiku-4-5"

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
    cases_path = Path(__file__).parents[1] / "data" / "quality_cases.json"
    with open(cases_path) as f:
        return json.load(f)


def judge_response(api_key, case):
    user_msg = JUDGE_USER_TEMPLATE.format(
        prompt=case["prompt"],
        reference=case["reference_response"],
        candidate=case["response"],
    )
    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": JUDGE_MODEL,
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 256,
        },
    )
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"].strip()
    # strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [WARN] judge returned malformed JSON for {case['id']}: {raw}")
        return None


def main():
    load_env(GATEWAY_ENV)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY not set.")
        print(f"Ensure it's in {GATEWAY_ENV}")
        sys.exit(1)

    cases = load_cases()

    print(f"Judging {len(cases)} responses with {JUDGE_MODEL} via OpenRouter...\n")
    print(f"{'ID':<8} {'Level':<10} {'Correct':<9} {'Complete':<10} {'Concise':<9} {'Avg':<6} Reasoning")
    print("-" * 110)

    results = []
    for case in cases:
        scores = judge_response(api_key, case)
        if scores is None:
            continue

        avg = (scores["correctness"] + scores["completeness"] + scores["conciseness"]) / 3
        results.append({**case, "scores": scores, "avg": avg})

        print(
            f"{case['id']:<8} {case['quality_level']:<10} "
            f"{scores['correctness']:<9} {scores['completeness']:<10} {scores['conciseness']:<9} "
            f"{avg:<6.1f} {scores['reasoning']}"
        )

    print("-" * 110)

    if results:
        overall_avg = sum(r["avg"] for r in results) / len(results)
        print(f"\nOverall average score: {overall_avg:.2f} / 5.00\n")

        by_level = {}
        for r in results:
            level = r["quality_level"]
            if level not in by_level:
                by_level[level] = []
            by_level[level].append(r["avg"])

        print("Average score by quality level:")
        print(f"  {'Level':<12} {'Avg Score':<10} {'Cases'}")
        print(f"  {'─────':<12} {'─────────':<10} {'─────'}")
        for level, scores_list in sorted(by_level.items()):
            print(f"  {level:<12} {sum(scores_list)/len(scores_list):<10.2f} {len(scores_list)}")

        print()
        print("Observations to record:")
        print("  - Does the judge correctly rank good > mediocre > bad?")
        print("  - Any cases where the judge gave a bad response a high score?")
        print("  - Any cases where the judge gave a good response a low score?")

    results_path = Path(__file__).parents[1] / "data" / "quality_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to data/quality_results.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
