"""
Phase 4 — Classifier Evaluator

Runs the zero-shot classifier on each case in data/classifier_cases.json
and records:
  - predicted label
  - confidence score for each label
  - whether prediction matches expected label

Why eval the classifier if the system uses the learned router?
  1. The classifier is the fallback if router_model.pkl is deleted
  2. Its failures explain what the learned router had to be trained to fix

Run from llm_inference_gateway_eval/:
  python evaluators/classifier_eval.py
"""

import json
import sys
from pathlib import Path

GATEWAY_PATH = Path(__file__).parents[3] / "llm_inference_gateway"
sys.path.insert(0, str(GATEWAY_PATH))

from app.classifier import get_classifier, TASK_LABELS


def load_cases():
    cases_path = Path(__file__).parents[1] / "data" / "classifier_cases.json"
    with open(cases_path) as f:
        return json.load(f)


def run_case(clf, case):
    result = clf(case["prompt"], candidate_labels=TASK_LABELS)
    predicted = result["labels"][0]
    confidence = result["scores"][0]
    all_scores = dict(zip(result["labels"], result["scores"]))
    correct = predicted == case["expected_label"]
    return predicted, confidence, all_scores, correct


def main():
    cases = load_cases()

    print("Loading classifier...\n")
    clf = get_classifier()

    print(f"Running {len(cases)} classifier cases...\n")
    print(f"{'ID':<8} {'Result':<8} {'Expected':<22} {'Predicted':<22} {'Conf':<6} {'Difficulty'}")
    print("-" * 90)

    correct_total = 0
    per_label = {}
    per_difficulty = {"easy": {"pass": 0, "fail": 0}, "medium": {"pass": 0, "fail": 0}, "hard": {"pass": 0, "fail": 0}}
    low_confidence = []
    failures = []

    for case in cases:
        predicted, confidence, all_scores, correct = run_case(clf, case)

        label = case["expected_label"]
        difficulty = case["difficulty"]

        if label not in per_label:
            per_label[label] = {"pass": 0, "fail": 0}

        if correct:
            correct_total += 1
            per_label[label]["pass"] += 1
            per_difficulty[difficulty]["pass"] += 1
        else:
            per_label[label]["fail"] += 1
            per_difficulty[difficulty]["fail"] += 1
            failures.append((case, predicted, confidence))

        if confidence < 0.50:
            low_confidence.append((case, predicted, confidence))

        status = "PASS ✓" if correct else "FAIL ✗"
        print(f"{case['id']:<8} {status:<8} {label:<22} {predicted:<22} {confidence:<6.2f} {difficulty}")

        # Print full score breakdown for failures and hard cases
        if not correct or difficulty == "hard":
            for lbl, score in sorted(all_scores.items(), key=lambda x: -x[1]):
                marker = " ←" if lbl == case["expected_label"] else ""
                print(f"         {'':8} {lbl:<22} {score:.2f}{marker}")

    print("-" * 90)
    print(f"\nOverall accuracy: {correct_total}/{len(cases)} = {correct_total/len(cases):.0%}\n")

    # Per-label breakdown
    print("Per-label accuracy:")
    print(f"  {'Label':<24} {'Pass':<6} {'Fail':<6} {'Accuracy'}")
    print(f"  {'─────':<24} {'────':<6} {'────':<6} {'────────'}")
    for label, counts in per_label.items():
        total = counts["pass"] + counts["fail"]
        acc = counts["pass"] / total if total > 0 else 0
        print(f"  {label:<24} {counts['pass']:<6} {counts['fail']:<6} {acc:.0%}")

    print()

    # Per-difficulty breakdown
    print("Per-difficulty accuracy:")
    print(f"  {'Difficulty':<12} {'Pass':<6} {'Fail':<6} {'Accuracy'}")
    print(f"  {'──────────':<12} {'────':<6} {'────':<6} {'────────'}")
    for diff, counts in per_difficulty.items():
        total = counts["pass"] + counts["fail"]
        if total > 0:
            acc = counts["pass"] / total
            print(f"  {diff:<12} {counts['pass']:<6} {counts['fail']:<6} {acc:.0%}")

    print()

    # Low confidence cases
    if low_confidence:
        print(f"Low confidence predictions (< 0.50) — {len(low_confidence)} cases:")
        for case, predicted, confidence in low_confidence:
            match = "✓" if predicted == case["expected_label"] else "✗"
            print(f"  {case['id']}  {match}  conf={confidence:.2f}  '{case['prompt'][:55]}'")

    print()

    # Failures summary
    if failures:
        print(f"Failures — {len(failures)} cases:")
        for case, predicted, confidence in failures:
            print(f"  {case['id']}  expected '{case['expected_label']}' got '{predicted}' (conf={confidence:.2f})")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
