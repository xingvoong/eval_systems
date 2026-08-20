"""
Phase 6 — Judge Calibration

Compares judge scores against human labels on the same cases.
Computes Spearman rank correlation per dimension.

  < 0.70 → judge measures something, but not what you think
  > 0.85 → strong enough for relative A/B comparison

Human labels are written directly in this file — scored by the
project author before running the judge, so there's no contamination.

Run from llm_inference_gateway_eval/:
  python evaluator_validation/judge_calibration.py
"""

import json
import os
import sys
import requests
from pathlib import Path
from scipy.stats import spearmanr

GATEWAY_ENV = Path(__file__).parents[3] / "llm_inference_gateway" / ".env"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
JUDGE_MODEL = "anthropic/claude-haiku-4-5"

# Human labels — scored before running the judge
# Format: case_id → {correctness, completeness, conciseness}
HUMAN_LABELS = {
    "q_001": {"correctness": 5, "completeness": 5, "conciseness": 5},   # identical to reference
    "q_002": {"correctness": 2, "completeness": 1, "conciseness": 4},   # explains concept, no code
    "q_003": {"correctness": 5, "completeness": 5, "conciseness": 5},   # identical to reference
    "q_004": {"correctness": 5, "completeness": 2, "conciseness": 1},   # correct but buried in padding
    "q_005": {"correctness": 5, "completeness": 5, "conciseness": 5},   # identical to reference
    "q_006": {"correctness": 1, "completeness": 1, "conciseness": 4},   # hollow bullets, no content
    "q_007": {"correctness": 5, "completeness": 5, "conciseness": 5},   # identical to reference
    "q_008": {"correctness": 4, "completeness": 2, "conciseness": 5},   # correct but missing details
    "q_009": {"correctness": 5, "completeness": 5, "conciseness": 5},   # identical to reference
    "q_010": {"correctness": 3, "completeness": 2, "conciseness": 4},   # basic script, missing rsync/date
}

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

    print("Running judge on all 10 cases (temperature=0)...\n")
    print(f"{'ID':<8} {'Dim':<14} {'Human':<8} {'Judge':<8} {'Match?'}")
    print("-" * 50)

    human_correct, judge_correct = [], []
    human_complete, judge_complete = [], []
    human_concise, judge_concise = [], []

    for case in cases:
        cid = case["id"]
        human = HUMAN_LABELS[cid]

        scores = call_judge(
            api_key,
            case["prompt"],
            case["reference_response"],
            case["response"],
        )

        for dim, h_list, j_list in [
            ("correctness", human_correct, judge_correct),
            ("completeness", human_complete, judge_complete),
            ("conciseness", human_concise, judge_concise),
        ]:
            h = human[dim]
            j = scores[dim]
            h_list.append(h)
            j_list.append(j)
            match = "✓" if h == j else ("~" if abs(h - j) <= 1 else "✗")
            print(f"{cid:<8} {dim:<14} {h:<8} {j:<8} {match}")

        print()

    print("-" * 50)

    # Spearman correlation per dimension
    r_correct, _ = spearmanr(human_correct, judge_correct)
    r_complete, _ = spearmanr(human_complete, judge_complete)
    r_concise, _ = spearmanr(human_concise, judge_concise)

    def interpret(r):
        if r >= 0.85:
            return "strong ✓"
        elif r >= 0.70:
            return "acceptable"
        else:
            return "weak ✗ — judge may not measure what you think"

    print("\nSpearman rank correlation (human vs judge):")
    print(f"  {'Dimension':<14} {'Correlation':<14} {'Interpretation'}")
    print(f"  {'─────────':<14} {'───────────':<14} {'──────────────'}")
    print(f"  {'correctness':<14} {r_correct:<14.2f} {interpret(r_correct)}")
    print(f"  {'completeness':<14} {r_complete:<14.2f} {interpret(r_complete)}")
    print(f"  {'conciseness':<14} {r_concise:<14.2f} {interpret(r_concise)}")

    avg_r = (r_correct + r_complete + r_concise) / 3
    print(f"\n  Average correlation: {avg_r:.2f}")
    print(f"  {interpret(avg_r)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
