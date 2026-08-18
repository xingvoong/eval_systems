"""
Phase 1 — Explore

Runs the llm_inference_gateway classifier on 20 prompts and records:
  - predicted label
  - confidence score for each label
  - what routing decision would follow (no LLM calls made)

Run with:
  pip install transformers torch
  python phase1_explore.py
"""

from transformers import pipeline

TASK_LABELS = ["summarization", "question answering", "code generation", "general chat"]

# Routing rule (mirrors router.py Rule 3 zero-shot path)
FAST_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
DEFAULT_MODEL = "gpt-4"

def route_from_label(label: str) -> str:
    if label in ("code generation", "summarization"):
        return FAST_MODEL
    return DEFAULT_MODEL

# 20 prompts — mix of all 4 task types, including some ambiguous ones
PROMPTS = [
    # clear code generation
    {"prompt": "Write a Python function to reverse a linked list.", "expected": "code generation"},
    {"prompt": "How do I sort a dictionary by value in Python?", "expected": "code generation"},
    {"prompt": "Write a SQL query to find the top 5 customers by revenue.", "expected": "code generation"},
    {"prompt": "Give me a bash script that backs up a directory every night.", "expected": "code generation"},
    {"prompt": "Implement a binary search algorithm in JavaScript.", "expected": "code generation"},

    # clear summarization
    {"prompt": "Summarize the key points from this article in 3 bullets.", "expected": "summarization"},
    {"prompt": "Give me a one-paragraph summary of the French Revolution.", "expected": "summarization"},
    {"prompt": "TL;DR this paragraph for me.", "expected": "summarization"},
    {"prompt": "Condense this meeting transcript into action items.", "expected": "summarization"},
    {"prompt": "What are the main takeaways from this earnings report?", "expected": "summarization"},

    # clear question answering
    {"prompt": "What is the capital of Japan?", "expected": "question answering"},
    {"prompt": "Who invented the telephone?", "expected": "question answering"},
    {"prompt": "What does HTTP stand for?", "expected": "question answering"},
    {"prompt": "When did World War II end?", "expected": "question answering"},
    {"prompt": "What is the difference between TCP and UDP?", "expected": "question answering"},

    # general chat
    {"prompt": "Hey, how are you doing today?", "expected": "general chat"},
    {"prompt": "I'm feeling a bit overwhelmed with work lately.", "expected": "general chat"},
    {"prompt": "What do you think about AI taking over jobs?", "expected": "general chat"},

    # ambiguous — interesting edge cases
    {"prompt": "Summarize this code and tell me if it has bugs.", "expected": "ambiguous"},
    {"prompt": "What's this do?", "expected": "ambiguous"},
]


def main():
    print("Loading classifier (downloads model on first run ~250MB)...\n")
    clf = pipeline("zero-shot-classification", model="typeform/distilbert-base-uncased-mnli")

    print(f"{'#':<3} {'Prompt':<55} {'Expected':<22} {'Predicted':<22} {'Confidence':<10} {'Routed To'}")
    print("-" * 145)

    correct = 0
    total_non_ambiguous = 0

    for i, item in enumerate(PROMPTS, 1):
        prompt = item["prompt"]
        expected = item["expected"]

        result = clf(prompt, candidate_labels=TASK_LABELS)
        predicted = result["labels"][0]
        confidence = result["scores"][0]
        routed_to = route_from_label(predicted)

        # track accuracy on non-ambiguous cases
        if expected != "ambiguous":
            total_non_ambiguous += 1
            if predicted == expected:
                correct += 1

        match = "✓" if predicted == expected else "✗" if expected != "ambiguous" else "?"
        short_prompt = prompt[:52] + "..." if len(prompt) > 52 else prompt
        short_routed = "Mistral-7B" if "Mistral" in routed_to else "gpt-4"

        print(f"{i:<3} {short_prompt:<55} {expected:<22} {predicted:<22} {confidence:<10.2f} {short_routed}  {match}")

        # print full confidence breakdown for ambiguous or wrong cases
        if predicted != expected or expected == "ambiguous":
            for label, score in zip(result["labels"], result["scores"]):
                print(f"    {'':55} {label:<22} {score:.2f}")

    print("-" * 145)
    print(f"\nClassifier accuracy (non-ambiguous cases): {correct}/{total_non_ambiguous} = {correct/total_non_ambiguous:.0%}")
    print("\nObservations to record:")
    print("  - Which labels does the classifier confuse most?")
    print("  - Which prompts had low confidence scores (< 0.50)?")
    print("  - Did ambiguous cases route to the right model anyway?")


if __name__ == "__main__":
    main()
