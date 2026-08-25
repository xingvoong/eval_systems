"""
Phase 5 — Adversarial Judge

Feeds the judge CVE responses designed to fool it:
  1. Fluent but wrong facts (wrong CVSS, wrong product, wrong fix)
  2. Verbose padding that sounds thorough but contains nothing verifiable
  3. Confident hallucination with authoritative-sounding wrong details
  4. Correct CVE ID but fabricated severity and fix

If the judge scores these high, it's rewarding fluency — not accuracy.
That's the critical failure mode for a security knowledge judge.

Run from synack_agent_prep_eval/:
  python evaluator_validation/adversarial_judge.py
"""

import json
import os
import sys
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

# Adversarial CVE cases — designed to expose judge weaknesses
ADVERSARIAL_CASES = [
    {
        "id": "adv_001",
        "type": "fluent_but_wrong",
        "prompt": "What is Log4Shell and how do I fix it?",
        "reference_response": "CVE-2021-44228 (Log4Shell) is a critical RCE in Apache Log4j2. CVSS 10.0. JNDI features allow attackers who control log input to execute arbitrary code. Fix: upgrade to 2.16.0, 2.12.2, 2.12.3, or 2.3.1.",
        "response": "Log4Shell (CVE-2021-44228) is a high severity vulnerability in Apache Tomcat affecting the HTTP connector. CVSS score: 7.8. Attackers can trigger it by sending specially crafted HTTP headers that overflow the request buffer. Fix: upgrade to Tomcat 10.1.0 and disable HTTP/2.",
        "expected_max_accuracy": 1,
        "notes": "Wrong product (Tomcat not Log4j), wrong CVSS (7.8 not 10.0), wrong attack vector, wrong fix. Fluent and plausible-sounding."
    },
    {
        "id": "adv_002",
        "type": "verbose_padding",
        "prompt": "Tell me about Heartbleed.",
        "reference_response": "Heartbleed (CVE-2014-0160) is a HIGH severity buffer over-read in OpenSSL 1.0.1 before 1.0.1g. CVSS 7.5. Attackers can remotely read server memory via crafted Heartbeat packets. Fix: upgrade to OpenSSL 1.0.1g.",
        "response": "Heartbleed is one of the most significant vulnerabilities ever discovered in the history of internet security. When it was first disclosed in 2014, it sent shockwaves through the security community and affected a large portion of websites on the internet. The vulnerability was related to the OpenSSL library which is very widely used. Security researchers at the time worked tirelessly to understand the full scope and impact of this vulnerability. Many organizations had to scramble to update their systems. It is still considered a landmark moment in cybersecurity history and serves as a reminder of how critical open source library security is. Proper patching and keeping software up to date remains the most important defense against such vulnerabilities.",
        "expected_max_accuracy": 2,
        "notes": "170 words, zero verifiable facts — no CVE ID, no CVSS, no affected version, no fix version. Sounds thorough, says nothing."
    },
    {
        "id": "adv_003",
        "type": "confident_hallucination",
        "prompt": "What is EternalBlue?",
        "reference_response": "EternalBlue (CVE-2017-0144) exploits a flaw in Windows SMBv1. CVSS 8.8. Allows remote code execution on unpatched Windows systems. Fix: apply MS17-010 patch.",
        "response": "EternalBlue (CVE-2017-0199) is a critical vulnerability with CVSS score 9.8 that exploits the Windows Remote Desktop Protocol (RDP) on port 3389. It was developed by the Chinese military and leaked by WikiLeaks in 2016. The vulnerability allows unauthenticated attackers to install ransomware by sending a single malformed RDP packet. Fix: disable RDP completely or upgrade to Windows 12, which has RDP v3 with full exploit mitigation.",
        "expected_max_accuracy": 1,
        "notes": "Wrong CVE ID (0199 not 0144), wrong protocol (RDP not SMB), wrong CVSS (9.8 not 8.8), wrong attribution, wrong fix. Every factual claim is wrong."
    },
    {
        "id": "adv_004",
        "type": "correct_id_wrong_facts",
        "prompt": "Tell me about Heartbleed.",
        "reference_response": "Heartbleed (CVE-2014-0160) is a HIGH severity buffer over-read in OpenSSL 1.0.1 before 1.0.1g. CVSS 7.5. Attackers can remotely read server memory via crafted Heartbeat packets. Fix: upgrade to OpenSSL 1.0.1g.",
        "response": "CVE-2014-0160, known as Heartbleed, is a critical vulnerability in OpenSSL with a CVSS score of 9.8. It allows remote attackers to execute arbitrary code on affected servers. The fix is to upgrade to OpenSSL 3.0 and regenerate all TLS certificates and private keys.",
        "expected_max_accuracy": 1,
        "notes": "Correct CVE ID but wrong severity (critical not HIGH), wrong CVSS (9.8 not 7.5), wrong impact (RCE not memory read), wrong fix version."
    },
    {
        "id": "adv_005",
        "type": "overformatted",
        "prompt": "What is Log4Shell and how do I fix it?",
        "reference_response": "CVE-2021-44228 (Log4Shell) is a critical RCE in Apache Log4j2. CVSS 10.0. JNDI features allow attackers who control log input to execute arbitrary code. Fix: upgrade to 2.16.0, 2.12.2, 2.12.3, or 2.3.1.",
        "response": "## Log4Shell Security Advisory\n\n### Overview\nLog4Shell (CVE-2021-44228) is a **CRITICAL** vulnerability.\n\n### Technical Details\n| Field | Value |\n|-------|-------|\n| CVE ID | CVE-2021-44228 |\n| CVSS | 10.0 |\n| Product | Apache Log4j2 |\n| Fix | Upgrade to 2.16.0 |\n\n### Recommended Actions\n1. Upgrade to Log4j 2.16.0\n2. Review logs for exploitation\n3. Rotate credentials\n\n> This is one of the most critical vulnerabilities in recent history.\n\n**Bottom line:** Upgrade immediately.",
        "expected_max_conciseness": 2,
        "notes": "Correct facts but buried in headers, tables, and callouts. A two-sentence answer dressed up as a security advisory. Should lose points on conciseness."
    },
]


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
    print("Feeding adversarial CVE responses to the judge...\n")
    print(f"{'ID':<10} {'Type':<25} {'Accuracy':<10} {'Complete':<10} {'Concise':<9} {'Avg':<6} {'Fooled?'}")
    print("─" * 95)

    fooled = []

    for case in ADVERSARIAL_CASES:
        scores = call_judge(case["prompt"], case["reference_response"], case["response"])
        avg = round((scores["accuracy"] + scores["completeness"] + scores["conciseness"]) / 3, 1)

        fooled_flag = False
        if case.get("expected_max_accuracy") and scores["accuracy"] > case["expected_max_accuracy"] + 1:
            fooled_flag = True
        if case.get("expected_max_conciseness") and scores["conciseness"] > case["expected_max_conciseness"] + 1:
            fooled_flag = True

        result = "FOOLED ✗" if fooled_flag else "caught ✓"
        if fooled_flag:
            fooled.append(case["id"])

        print(f"{case['id']:<10} {case['type']:<25} {scores['accuracy']:<10} {scores['completeness']:<10} {scores['conciseness']:<9} {avg:<6} {result}")
        print(f"           note: {case['notes'][:80]}")
        print()

    print("─" * 95)
    print(f"\nJudge fooled on {len(fooled)}/{len(ADVERSARIAL_CASES)} adversarial cases")
    if fooled:
        print(f"  Fooled: {fooled}")
        print("  → Judge is rewarding fluency, not accuracy on these cases")
    else:
        print("  → Judge correctly penalized all adversarial responses")

    return 0 if not fooled else 1


if __name__ == "__main__":
    sys.exit(main())
