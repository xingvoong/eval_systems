"""
Phase 5 — Judge Consistency

Runs the same (prompt, response) pair through the judge 5 times at
temperature=0 and measures score variance across runs.

A reliable judge should return the same score every time on the same input.
Cases with variance > 0.5 are flagged as unreliable.

Run from synack_agent_prep_eval/:
  python evaluator_validation/judge_consistency.py
"""

import json
import os
import sys
import statistics
from pathlib import Path

# ── Setup ──────────────────────────────────────────────────────────────────────
AGENT_PATH = Path(__file__).parents[3] / "synack-agent-prep"
sys.path.insert(0, str(AGENT_PATH))

def load_env(path):
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env(AGENT_PATH / ".env")

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
if not GROQ_KEY:
    print("SKIP: no GROQ_API_KEY set.")
    sys.exit(0)

from groq import Groq
client = Groq(api_key=GROQ_KEY)

JUDGE_MODEL = "openai/gpt-oss-20b"
RUNS = 5

JUDGE_SYSTEM = """You are a security knowledge evaluator. You score CVE research responses
against a reference answer on three dimensions (1-5 each):

accuracy    — Are the CVE ID, CVSS score, severity, and affected software correct?
              5 = all facts correct. 1 = major errors (wrong ID, wrong score, wrong fix).
completeness — Does the response cover CVE ID, severity, description, and fix?
              5 = all four present. 1 = missing most.
conciseness  — Is it direct and free of padding?
              5 = tight and factual. 1 = verbose with no added value.

Return only valid JSON in this exact format:
{"accuracy": <1-5>, "completeness": <1-5>, "conciseness": <1-5>, "reasoning": "<one sentence>"}"""


def call_judge(prompt, reference, candidate):
    user_msg = f"""QUESTION: {prompt}

REFERENCE ANSWER:
{reference}

CANDIDATE RESPONSE:
{candidate}

Score the candidate response."""

    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def main():
    cases_path = Path(__file__).parents[1] / "data" / "quality_cases.json"
    with open(cases_path) as f:
        all_cases = json.load(f)

    # One good, one bad, one mediocre
    subset = [c for c in all_cases if c["id"] in ("q_001", "q_002", "q_006")]

    print(f"Running each case {RUNS}x at temperature=0...\n")
    print(f"{'ID':<8} {'Level':<10} {'Accuracy scores':<25} {'Var':<6} {'Complete scores':<25} {'Var':<6} {'Concise scores':<25} {'Var':<6} {'Stable?'}")
    print("─" * 130)

    unstable = []

    for case in subset:
        acc_scores, comp_scores, conc_scores = [], [], []

        for _ in range(RUNS):
            scores = call_judge(case["prompt"], case["reference_response"], case["response"])
            acc_scores.append(scores["accuracy"])
            comp_scores.append(scores["completeness"])
            conc_scores.append(scores["conciseness"])

        var_a = statistics.variance(acc_scores)  if len(set(acc_scores))  > 1 else 0.0
        var_p = statistics.variance(comp_scores) if len(set(comp_scores)) > 1 else 0.0
        var_n = statistics.variance(conc_scores) if len(set(conc_scores)) > 1 else 0.0
        max_var = max(var_a, var_p, var_n)
        stable = "✓" if max_var <= 0.5 else "✗ UNSTABLE"

        if max_var > 0.5:
            unstable.append(case["id"])

        print(
            f"{case['id']:<8} {case['quality_level']:<10} "
            f"{str(acc_scores):<25} {var_a:<6.2f} "
            f"{str(comp_scores):<25} {var_p:<6.2f} "
            f"{str(conc_scores):<25} {var_n:<6.2f} "
            f"{stable}"
        )

    print("─" * 130)
    print(f"\nUnstable cases (variance > 0.5): {len(unstable)}/{len(subset)}")
    if unstable:
        print(f"  {unstable}")
    else:
        print("  None — judge is consistent at temperature=0")

    return 0 if not unstable else 1


if __name__ == "__main__":
    sys.exit(main())
