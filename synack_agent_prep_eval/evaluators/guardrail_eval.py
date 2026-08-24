"""
Phase 1: Guardrail Evaluator
=============================
Tests validate_input(), scan_output(), and check_rate_limit() from
01_react_agent/react_agent.py directly. No LLM calls — fully deterministic.

Run:
    python evaluators/guardrail_eval.py
"""

import json
import sys
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

# ── Import react_agent.py by file path ────────────────────────────────────────
# The directory name starts with a digit (01_react_agent) so normal Python
# import won't work. We load it by path instead.
# Mock groq and dotenv before loading — we don't need the LLM client.
sys.modules.setdefault("groq", MagicMock())
sys.modules.setdefault("dotenv", MagicMock())

AGENT_PATH = Path(__file__).parents[3] / "synack-agent-prep"
REACT_AGENT_FILE = AGENT_PATH / "01_react_agent" / "react_agent.py"

if not REACT_AGENT_FILE.exists():
    print(f"ERROR: could not find {REACT_AGENT_FILE}")
    print("Make sure synack-agent-prep is checked out at ../../../synack-agent-prep")
    sys.exit(1)

# Add synack-agent-prep root so react_agent.py can import agent.tools
sys.path.insert(0, str(AGENT_PATH))

spec = importlib.util.spec_from_file_location("react_agent", str(REACT_AGENT_FILE))
react_agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(react_agent)

validate_input   = react_agent.validate_input
scan_output      = react_agent.scan_output
check_rate_limit = react_agent.check_rate_limit

# ── Load test cases ────────────────────────────────────────────────────────────
DATA_FILE = Path(__file__).parents[1] / "data" / "guardrail_cases.json"
with open(DATA_FILE) as f:
    cases = json.load(f)

passed = 0
failed = 0
rows   = []

# ── Run input + output cases ───────────────────────────────────────────────────
for case in cases:
    cid = case["id"]
    cat = case["category"]

    if cat == "input":
        is_valid, reason = validate_input(case["input"])
        expected = case["expected_valid"]
        ok = (is_valid == expected)
    elif cat == "output":
        is_safe, reason = scan_output(case["output"])
        expected = case["expected_safe"]
        ok = (is_safe == expected)
    else:
        continue

    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1

    rows.append((cid, cat, status, case["notes"], reason))

# ── Rate limit inline test ─────────────────────────────────────────────────────
# Fresh user — 4 requests should pass, 5th should be blocked.
# Use a unique user_id so it doesn't collide with other test runs.
rate_user = "__eval_test_user__"
rate_results = [check_rate_limit(rate_user) for _ in range(5)]

first_four_ok = all(allowed for allowed, _ in rate_results[:4])
fifth_blocked  = not rate_results[4][0]

if first_four_ok and fifth_blocked:
    passed += 1
    rows.append(("g_rate", "rate_limit", "PASS", "4 pass, 5th blocked", ""))
else:
    failed += 1
    rows.append(("g_rate", "rate_limit", "FAIL", "4 pass, 5th blocked",
                 f"first_four_ok={first_four_ok} fifth_blocked={fifth_blocked}"))

# ── Print results ──────────────────────────────────────────────────────────────
total = passed + failed
print(f"\nGuardrail Eval — {passed}/{total} passed")
print(f"{'─'*72}")
print(f"{'ID':<8} {'Category':<12} {'Status':<6}  {'Notes':<40} Reason")
print(f"{'─'*72}")
for cid, cat, status, notes, reason in rows:
    marker = "✓" if status == "PASS" else "✗"
    print(f"{cid:<8} {cat:<12} {marker} {status:<4}  {notes[:40]:<40} {reason[:40]}")
print(f"{'─'*72}")
print(f"PASSED: {passed}/{total}")

if failed > 0:
    sys.exit(1)
