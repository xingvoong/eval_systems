#!/usr/bin/env bash
# ci/run_evals.sh
#
# Runs all deterministic evals and enforces thresholds.
# LLM-judge evals (quality, judge validation) run only when OPENROUTER_API_KEY is set.
#
# Run from llm_inference_gateway_eval/:
#   bash ci/run_evals.sh
#
# Exit codes:
#   0 — all thresholds passed
#   1 — one or more thresholds failed

set -uo pipefail

# ── Thresholds ────────────────────────────────────────────────────────────────
ROUTING_THRESHOLD=15        # routing_eval must pass this many / 15
CLASSIFIER_THRESHOLD=40     # classifier_eval must hit this accuracy % (0–100)
                            # 40% is the observed baseline — zero-shot classifier is the known weak point
RT_ROUTING_THRESHOLD=12     # routing_adversarial must hold this many / 12
RT_CLASSIFIER_THRESHOLD=3   # classifier_adversarial injection must hold this many / 6

# ── Tracking ─────────────────────────────────────────────────────────────────
PASSED=0
FAILED=0
SKIPPED=0
declare -a SUMMARY

pass() { PASSED=$((PASSED + 1)); SUMMARY+=("  PASS    $1"); }
fail() { FAILED=$((FAILED + 1)); SUMMARY+=("  FAIL    $1  <- $2"); }
skip() { SKIPPED=$((SKIPPED + 1)); SUMMARY+=("  SKIP    $1  ($2)"); }

# ── Helpers ───────────────────────────────────────────────────────────────────
run_python() {
    python "$@" 2>&1
}

# Extract the first integer from a line matching a pattern.
# Works on both GNU grep and BSD grep (macOS).
extract_int() {
    local text="$1"
    local pattern="$2"
    echo "$text" | grep -E "$pattern" | grep -oE '[0-9]+' | head -1
}

# ── Routing eval (deterministic) ──────────────────────────────────────────────
echo "=== routing_eval.py ==="
ROUTING_OUT=$(run_python evaluators/routing_eval.py)
echo "$ROUTING_OUT"

# Output line: "Results: 15/15 passed (100%)"
ROUTING_PASSED=$(extract_int "$ROUTING_OUT" "passed")
ROUTING_PASSED=${ROUTING_PASSED:-0}

if [ "$ROUTING_PASSED" -ge "$ROUTING_THRESHOLD" ]; then
    pass "routing_eval         ${ROUTING_PASSED}/15 passed (threshold: ${ROUTING_THRESHOLD}/15)"
else
    fail "routing_eval" "${ROUTING_PASSED}/15 passed — need ${ROUTING_THRESHOLD}/15"
fi

echo ""

# ── Classifier eval ───────────────────────────────────────────────────────────
echo "=== classifier_eval.py ==="
CLASSIFIER_OUT=$(run_python evaluators/classifier_eval.py)
echo "$CLASSIFIER_OUT"

# Output line: "Overall accuracy: 13/20 = 65%"
# Extract the percentage: get the line, get the last integer on it
CLASSIFIER_PCT=$(echo "$CLASSIFIER_OUT" | grep "Overall accuracy" | grep -oE '[0-9]+' | tail -1)
CLASSIFIER_PCT=${CLASSIFIER_PCT:-0}

if [ "$CLASSIFIER_PCT" -ge "$CLASSIFIER_THRESHOLD" ]; then
    pass "classifier_eval      ${CLASSIFIER_PCT}% accuracy (threshold: ${CLASSIFIER_THRESHOLD}%)"
else
    fail "classifier_eval" "${CLASSIFIER_PCT}% accuracy — need ${CLASSIFIER_THRESHOLD}%"
fi

echo ""

# ── Routing red team ──────────────────────────────────────────────────────────
echo "=== routing_adversarial.py ==="
RT_ROUTING_OUT=$(run_python red_team/routing_adversarial.py)
echo "$RT_ROUTING_OUT"

# Output line: "Routing held on 12/12 adversarial cases"
RT_ROUTING_HELD=$(extract_int "$RT_ROUTING_OUT" "Routing held on")
RT_ROUTING_HELD=${RT_ROUTING_HELD:-0}

if [ "$RT_ROUTING_HELD" -ge "$RT_ROUTING_THRESHOLD" ]; then
    pass "routing_adversarial  ${RT_ROUTING_HELD}/12 held (threshold: ${RT_ROUTING_THRESHOLD}/12)"
else
    fail "routing_adversarial" "${RT_ROUTING_HELD}/12 held — need ${RT_ROUTING_THRESHOLD}/12"
fi

echo ""

# ── Classifier red team ───────────────────────────────────────────────────────
echo "=== classifier_adversarial.py ==="
RT_CLASSIFIER_OUT=$(run_python red_team/classifier_adversarial.py)
echo "$RT_CLASSIFIER_OUT"

# Output line: "Label injection / lexical overlap: 3/6 held"
RT_CLASSIFIER_HELD=$(extract_int "$RT_CLASSIFIER_OUT" "injection.*held")
RT_CLASSIFIER_HELD=$((${RT_CLASSIFIER_HELD:-0} + 0))  # strip leading zeros

if [ "$RT_CLASSIFIER_HELD" -ge "$RT_CLASSIFIER_THRESHOLD" ]; then
    pass "classifier_adversarial  ${RT_CLASSIFIER_HELD}/6 held (threshold: ${RT_CLASSIFIER_THRESHOLD}/6)"
else
    fail "classifier_adversarial" "${RT_CLASSIFIER_HELD}/6 held — need ${RT_CLASSIFIER_THRESHOLD}/6"
fi

echo ""

# ── LLM-judge evals (optional — require OPENROUTER_API_KEY) ──────────────────
if [ -n "${OPENROUTER_API_KEY:-}" ]; then
    echo "=== quality_eval.py ==="
    run_python evaluators/quality_eval.py
    echo ""

    echo "=== judge_consistency.py ==="
    run_python evaluator_validation/judge_consistency.py
    echo ""

    echo "=== judge_calibration.py ==="
    run_python evaluator_validation/judge_calibration.py
    echo ""

    echo "=== adversarial_judge.py ==="
    run_python evaluator_validation/adversarial_judge.py
    echo ""
else
    skip "quality_eval + judge_validation" "OPENROUTER_API_KEY not set"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo "============================================================"
echo "  EVAL SUMMARY"
echo "============================================================"
for line in "${SUMMARY[@]}"; do
    echo "$line"
done
echo ""
echo "  Passed:  $PASSED"
echo "  Failed:  $FAILED"
echo "  Skipped: $SKIPPED"
echo "============================================================"

if [ "$FAILED" -gt 0 ]; then
    echo ""
    echo "  CI FAILED — $FAILED threshold(s) not met"
    exit 1
else
    echo ""
    echo "  CI PASSED"
    exit 0
fi
