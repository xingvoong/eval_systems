"""
Phase 3: Degradation Evaluator
================================
Tests that the multi-agent orchestrator degrades gracefully when workers fail.
Workers are mocked — no LLM calls, no network required.

Three degradation paths in the orchestrator:
  1. CVEResearcher fails  → early return "Research failed: ..."
  2. SeverityAssessor fails → early return "Research findings (assessment unavailable): ..."
  3. PatchChecker fails   → synthesis still runs with partial data (no early return)

Run:
    python evaluators/degradation_eval.py
"""

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# ── Setup ──────────────────────────────────────────────────────────────────────
AGENT_PATH = Path(__file__).parents[3] / "synack-agent-prep"

# Config.validate() raises if GROQ_API_KEY not set — use a fake key
os.environ.setdefault("GROQ_API_KEY", "fake-key-for-testing")

# Mock modules before any imports from the agent code
sys.modules.setdefault("groq",   MagicMock())
sys.modules.setdefault("dotenv", MagicMock())

# Mock workers module — we'll swap in AsyncMocks per test case
mock_workers = MagicMock()
sys.modules["workers"] = mock_workers

# Add paths so orchestrator can find core.*
sys.path.insert(0, str(AGENT_PATH))
sys.path.insert(0, str(AGENT_PATH / "02_multi_agent"))

# Load orchestrator by file path
ORCHESTRATOR_FILE = AGENT_PATH / "02_multi_agent" / "orchestrator.py"
if not ORCHESTRATOR_FILE.exists():
    print(f"ERROR: could not find {ORCHESTRATOR_FILE}")
    sys.exit(1)

spec = importlib.util.spec_from_file_location("orchestrator", str(ORCHESTRATOR_FILE))
orchestrator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orchestrator_module)

run_orchestrator = orchestrator_module.run_orchestrator

# ── TaskResult helper ──────────────────────────────────────────────────────────
from core.types import TaskResult

def ok_result(agent: str, result: str) -> TaskResult:
    return TaskResult(task_id="test", agent=agent, result=result,
                      success=True, latency_ms=50.0)

def fail_result(agent: str, error: str, result: str = "") -> TaskResult:
    return TaskResult(task_id="test", agent=agent, result=result,
                      success=False, latency_ms=50.0, error=error)

# ── Load test cases ────────────────────────────────────────────────────────────
DATA_FILE = Path(__file__).parents[1] / "data" / "degradation_cases.json"
with open(DATA_FILE) as f:
    cases = json.load(f)

passed = 0
failed = 0
rows   = []

for case in cases:
    cid      = case["id"]
    scenario = case["scenario"]
    expected = case["expected_contains"]

    # Patch the orchestrator module's imported names directly.
    # The orchestrator does `from workers import run_cve_researcher, ...` at load
    # time, creating local references. Patching the workers mock module after the
    # fact has no effect — we must patch the orchestrator's own namespace.
    if scenario == "researcher_fails":
        orchestrator_module.run_cve_researcher = AsyncMock(
            return_value=fail_result("cve_researcher", "Connection timeout")
        )
        orchestrator_module.run_patch_checker = AsyncMock(
            return_value=ok_result("patch_checker", "No patch needed.")
        )
        orchestrator_module.run_severity_assessor = AsyncMock(
            return_value=ok_result("severity_assessor", "High risk.")
        )

    elif scenario == "assessor_fails":
        orchestrator_module.run_cve_researcher = AsyncMock(
            return_value=ok_result("cve_researcher", "Log4Shell is a critical RCE in Apache Log4j.")
        )
        orchestrator_module.run_patch_checker = AsyncMock(
            return_value=ok_result("patch_checker", "Patch: upgrade to 2.15.0.")
        )
        orchestrator_module.run_severity_assessor = AsyncMock(
            return_value=fail_result("severity_assessor", "Timed out after 30s")
        )

    elif scenario == "patch_checker_fails":
        orchestrator_module.run_cve_researcher = AsyncMock(
            return_value=ok_result("cve_researcher", "Log4Shell is a critical RCE in Apache Log4j.")
        )
        orchestrator_module.run_patch_checker = AsyncMock(
            return_value=fail_result("patch_checker", "NVD unreachable",
                                     result="Patch information unavailable.")
        )
        orchestrator_module.run_severity_assessor = AsyncMock(
            return_value=ok_result("severity_assessor", "Critical — exploit in the wild.")
        )
        orchestrator_module.client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content="Log4Shell report. Patch information unavailable. Upgrade immediately."
            ))]
        )

    elif scenario == "all_succeed":
        orchestrator_module.run_cve_researcher = AsyncMock(
            return_value=ok_result("cve_researcher", "Log4Shell (CVE-2021-44228): critical RCE.")
        )
        orchestrator_module.run_patch_checker = AsyncMock(
            return_value=ok_result("patch_checker", "Patch: upgrade to Log4j 2.15.0.")
        )
        orchestrator_module.run_severity_assessor = AsyncMock(
            return_value=ok_result("severity_assessor", "CVSS 10.0 — exploit in the wild.")
        )
        orchestrator_module.client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content="Log4Shell is a critical RCE. CVSS 10.0. Upgrade to 2.15.0 immediately."
            ))]
        )

    result = asyncio.run(run_orchestrator("What is Log4Shell?"))
    ok = expected in result
    status = "PASS" if ok else "FAIL"

    if ok:
        passed += 1
    else:
        failed += 1

    rows.append((cid, scenario, status, case["notes"], result[:60]))

# ── Print results ──────────────────────────────────────────────────────────────
total = passed + failed
print(f"\nDegradation Eval — {passed}/{total} passed")
print(f"{'─'*80}")
print(f"{'ID':<8} {'Scenario':<22} {'Status':<6}  {'Notes':<35} Result")
print(f"{'─'*80}")
for cid, scenario, status, notes, result in rows:
    marker = "✓" if status == "PASS" else "✗"
    print(f"{cid:<8} {scenario:<22} {marker} {status:<4}  {notes[:35]:<35} {result}")
print(f"{'─'*80}")
print(f"PASSED: {passed}/{total}")

if failed > 0:
    sys.exit(1)
