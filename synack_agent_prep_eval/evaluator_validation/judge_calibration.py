"""
Phase 5 — Judge Calibration

Compares judge scores against human labels on the same cases.
Computes Spearman rank correlation per dimension.

  < 0.70 → judge measures something, but not what you think
  > 0.85 → strong enough for relative comparison

Human labels written before running the judge — no contamination.

Run from synack_agent_prep_eval/:
  python evaluator_validation/judge_calibration.py
"""

import json
import os
import sys
from pathlib import Path
from scipy.stats import spearmanr

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

# Human labels — scored before running the judge
# q_001 good:     accurate Log4Shell, CVSS 10.0, correct fix (2.16.0)
# q_002 bad:      wrong product (Tomcat), wrong CVSS (8.5), wrong fix (2.14.0)
# q_003 good:     accurate Heartbleed, CVSS 7.5, correct fix (1.0.1g)
# q_004 bad:      wrong CVE ID (-0161), wrong severity (critical/9.8), wrong fix (1.1.0)
# q_005 good:     accurate EternalBlue, CVSS 8.8, correct fix (MS17-010)
# q_006 mediocre: vague EternalBlue — no CVE ID, no CVSS, no specific fix
# q_007 mediocre: vague Log4Shell — no CVE ID, no CVSS, no fix version
# q_008 bad:      wrong CVE ID (-0199), wrong protocol (RDP), wrong fix (disable RDP)
HUMAN_LABELS = {
    "q_001": {"accuracy": 5, "completeness": 5, "conciseness": 5},
    "q_002": {"accuracy": 1, "completeness": 3, "conciseness": 5},
    "q_003": {"accuracy": 5, "completeness": 5, "conciseness": 5},
    "q_004": {"accuracy": 1, "completeness": 3, "conciseness": 5},
    "q_005": {"accuracy": 5, "completeness": 5, "conciseness": 5},
    "q_006": {"accuracy": 2, "completeness": 1, "conciseness": 3},
    "q_007": {"accuracy": 1, "completeness": 1, "conciseness": 1},
    "q_008": {"accuracy": 1, "completeness": 3, "conciseness": 5},
}

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
        cases = json.load(f)

    print("Running judge on all 8 cases (temperature=0)...\n")
    print(f"{'ID':<8} {'Dim':<14} {'Human':<8} {'Judge':<8} {'Match?'}")
    print("─" * 50)

    human_acc, judge_acc = [], []
    human_comp, judge_comp = [], []
    human_conc, judge_conc = [], []

    for case in cases:
        cid   = case["id"]
        human = HUMAN_LABELS[cid]
        scores = call_judge(case["prompt"], case["reference_response"], case["response"])

        for dim, h_list, j_list in [
            ("accuracy",     human_acc,  judge_acc),
            ("completeness", human_comp, judge_comp),
            ("conciseness",  human_conc, judge_conc),
        ]:
            h = human[dim]
            j = scores[dim]
            h_list.append(h)
            j_list.append(j)
            match = "✓" if h == j else ("~" if abs(h - j) <= 1 else "✗")
            print(f"{cid:<8} {dim:<14} {h:<8} {j:<8} {match}")
        print()

    print("─" * 50)

    r_acc,  _ = spearmanr(human_acc,  judge_acc)
    r_comp, _ = spearmanr(human_comp, judge_comp)
    r_conc, _ = spearmanr(human_conc, judge_conc)

    def interpret(r):
        if r >= 0.85: return "strong ✓"
        if r >= 0.70: return "acceptable"
        return "weak ✗ — judge may not measure what you think"

    print("\nSpearman rank correlation (human vs judge):")
    print(f"  {'Dimension':<14} {'Correlation':<14} Interpretation")
    print(f"  {'─────────':<14} {'───────────':<14} ──────────────")
    print(f"  {'accuracy':<14} {r_acc:<14.2f} {interpret(r_acc)}")
    print(f"  {'completeness':<14} {r_comp:<14.2f} {interpret(r_comp)}")
    print(f"  {'conciseness':<14} {r_conc:<14.2f} {interpret(r_conc)}")

    avg_r = (r_acc + r_comp + r_conc) / 3
    print(f"\n  Average correlation: {avg_r:.2f} — {interpret(avg_r)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
