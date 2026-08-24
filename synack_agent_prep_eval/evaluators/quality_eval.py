"""
Phase 4: Response Quality Evaluator
=====================================
LLM-as-judge: scores CVE research responses on accuracy, completeness,
and conciseness (1-5 each) against a reference response.

Requires ANTHROPIC_API_KEY or OPENROUTER_API_KEY in environment.
Skipped in CI if neither key is set.

Run:
    ANTHROPIC_API_KEY=sk-... python evaluators/quality_eval.py

Results saved to data/quality_results.json.
"""

import json
import os
import sys
from pathlib import Path

DATA_DIR     = Path(__file__).parents[1] / "data"
CASES_FILE   = DATA_DIR / "quality_cases.json"
RESULTS_FILE = DATA_DIR / "quality_results.json"

# ── Load .env from synack-agent-prep (has GROQ_API_KEY) ───────────────────────
def load_env(path):
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env(Path(__file__).parents[3] / "synack-agent-prep" / ".env")

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")

if not GROQ_KEY:
    print("SKIP: no GROQ_API_KEY set.")
    sys.exit(0)

JUDGE_MODEL = "openai/gpt-oss-20b"

sys.path.insert(0, str(Path(__file__).parents[3] / "synack-agent-prep"))
from groq import Groq
groq_client = Groq(api_key=GROQ_KEY)

# ── Judge prompt ───────────────────────────────────────────────────────────────
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


def call_judge(prompt: str, response: str, reference: str) -> dict:
    user_msg = f"""QUESTION: {prompt}

REFERENCE ANSWER:
{reference}

CANDIDATE RESPONSE:
{response}

Score the candidate response."""

    response = groq_client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
    )
    raw = response.choices[0].message.content

    # Strip markdown fences if present
    if raw.strip().startswith("```"):
        raw = raw.strip().split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


# ── Run eval ───────────────────────────────────────────────────────────────────
with open(CASES_FILE) as f:
    cases = json.load(f)

results = []
rows    = []

for case in cases:
    cid   = case["id"]
    level = case["quality_level"]
    print(f"  judging {cid} ({level})...", end=" ", flush=True)

    scores = call_judge(case["prompt"], case["response"], case["reference_response"])
    avg = round((scores["accuracy"] + scores["completeness"] + scores["conciseness"]) / 3, 1)

    print(f"accuracy={scores['accuracy']} completeness={scores['completeness']} conciseness={scores['conciseness']} avg={avg}")

    results.append({**case, "scores": scores, "avg": avg})
    rows.append((cid, level, scores["accuracy"], scores["completeness"], scores["conciseness"], avg))

# ── Save results ───────────────────────────────────────────────────────────────
with open(RESULTS_FILE, "w") as f:
    json.dump(results, f, indent=2)

# ── Print summary ──────────────────────────────────────────────────────────────
print(f"\nQuality Eval Results")
print(f"{'─'*65}")
print(f"{'ID':<8} {'Level':<10} {'Accuracy':<10} {'Complete':<10} {'Concise':<10} Avg")
print(f"{'─'*65}")
for cid, level, acc, comp, conc, avg in rows:
    print(f"{cid:<8} {level:<10} {acc:<10} {comp:<10} {conc:<10} {avg}")
print(f"{'─'*65}")

# Averages by quality level
for lvl in ["good", "mediocre", "bad"]:
    lvl_rows = [r for r in rows if r[1] == lvl]
    if lvl_rows:
        avg = round(sum(r[5] for r in lvl_rows) / len(lvl_rows), 1)
        print(f"  {lvl:<10} avg: {avg}")

print(f"\nResults saved to {RESULTS_FILE}")
