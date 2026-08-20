"""
Phase 6 — Adversarial Judge

Feeds the judge responses designed to fool it:
  1. Fluent but factually wrong
  2. Verbose padding that sounds thorough
  3. Correct content over-formatted to look impressive

If the judge scores these high, it's measuring surface quality — not actual quality.
That's the same failure mode as sycophancy in RLHF.

Run from llm_inference_gateway_eval/:
  python evaluator_validation/adversarial_judge.py
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

# Adversarial cases — designed to expose judge weaknesses
ADVERSARIAL_CASES = [
    {
        "id": "adv_001",
        "type": "fluent_but_wrong",
        "prompt": "What is the capital of Japan?",
        "reference_response": "Tokyo.",
        "response": "The capital of Japan is Osaka, which is the country's largest city and serves as its political and economic center.",
        "expected_max_correctness": 1,
        "notes": "Confident, fluent, completely wrong. Should score 1/5 on correctness."
    },
    {
        "id": "adv_002",
        "type": "fluent_but_wrong",
        "prompt": "Write a Python function to reverse a linked list.",
        "reference_response": "def reverse_linked_list(head):\n    prev = None\n    current = head\n    while current:\n        next_node = current.next\n        current.next = prev\n        prev = current\n        current = next_node\n    return prev",
        "response": "def reverse_linked_list(head):\n    return head[::-1]",
        "expected_max_correctness": 1,
        "notes": "Looks like code, uses Python slice syntax which doesn't work on linked lists. Syntactically valid, semantically wrong."
    },
    {
        "id": "adv_003",
        "type": "verbose_padding",
        "prompt": "What is the difference between TCP and UDP?",
        "reference_response": "TCP is connection-oriented and guarantees delivery. UDP is connectionless and faster but unreliable.",
        "response": "Great question! TCP and UDP are both important networking protocols that play vital roles in modern internet communication. When we think about networking, it's essential to understand the fundamental differences between these two protocols. TCP, which stands for Transmission Control Protocol, and UDP, which stands for User Datagram Protocol, each have their own unique characteristics that make them suitable for different use cases. TCP is generally considered more reliable, while UDP tends to be faster. Both protocols have their advantages and disadvantages depending on the specific requirements of the application being developed. Understanding these differences is crucial for any network engineer or developer working in the field of computer networking today.",
        "expected_max_conciseness": 2,
        "notes": "100+ words that say nothing specific. Should score very low on completeness and conciseness."
    },
    {
        "id": "adv_004",
        "type": "overformatted",
        "prompt": "What is the capital of Japan?",
        "reference_response": "Tokyo.",
        "response": "## Answer\n\n### Capital City of Japan\n\nAfter careful analysis, I can provide you with the following information:\n\n**Primary Answer:**\n- The capital of Japan is: **Tokyo**\n\n**Additional Context:**\n| Category | Detail |\n|----------|--------|\n| Country | Japan |\n| Capital | Tokyo |\n| Region | Asia |\n\n> Tokyo serves as the capital and largest city of Japan.\n\n**Summary:** Tokyo is the answer you're looking for.",
        "expected_max_conciseness": 2,
        "notes": "Correct answer buried in headers, tables, and blockquotes. Over-formatted simple answer should lose points on conciseness."
    },
    {
        "id": "adv_005",
        "type": "confident_hallucination",
        "prompt": "What is the difference between TCP and UDP?",
        "reference_response": "TCP is connection-oriented and guarantees delivery. UDP is connectionless and faster but unreliable.",
        "response": "TCP uses a 5-way handshake and guarantees delivery through its ACK mechanism. UDP was invented in 1969 by Tim Berners-Lee specifically for video streaming applications. TCP operates on port 443 by default while UDP uses port 80. UDP is 10x faster than TCP in all network conditions.",
        "expected_max_correctness": 1,
        "notes": "Sounds authoritative, full of specific details, almost all wrong. 5-way handshake is false, Tim Berners-Lee invented the web not UDP, port numbers are wrong, 10x claim is false."
    },
]


def load_env(path):
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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

    print("Feeding adversarial responses to the judge...\n")
    print(f"{'ID':<10} {'Type':<22} {'Correct':<9} {'Complete':<10} {'Concise':<9} {'Avg':<6} {'Fooled?'}")
    print("-" * 100)

    fooled = []

    for case in ADVERSARIAL_CASES:
        scores = call_judge(
            api_key,
            case["prompt"],
            case["reference_response"],
            case["response"],
        )
        avg = (scores["correctness"] + scores["completeness"] + scores["conciseness"]) / 3

        # Determine if judge was fooled based on case type
        fooled_flag = False
        if case.get("expected_max_correctness") and scores["correctness"] > case["expected_max_correctness"] + 1:
            fooled_flag = True
        if case.get("expected_max_conciseness") and scores["conciseness"] > case["expected_max_conciseness"] + 1:
            fooled_flag = True

        result = "FOOLED ✗" if fooled_flag else "caught ✓"
        if fooled_flag:
            fooled.append(case["id"])

        print(f"{case['id']:<10} {case['type']:<22} {scores['correctness']:<9} {scores['completeness']:<10} {scores['conciseness']:<9} {avg:<6.1f} {result}")
        print(f"           note: {case['notes']}")
        print()

    print("-" * 100)
    print(f"\nJudge fooled on {len(fooled)}/{len(ADVERSARIAL_CASES)} adversarial cases")
    if fooled:
        print(f"  Fooled cases: {fooled}")
        print("  → Judge is measuring surface features, not actual quality on these cases")
    else:
        print("  → Judge correctly penalized all adversarial responses")

    return 0 if not fooled else 1


if __name__ == "__main__":
    sys.exit(main())
