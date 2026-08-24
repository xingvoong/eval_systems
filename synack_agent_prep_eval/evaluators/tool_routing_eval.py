"""
Phase 2: Tool Routing Evaluator
================================
Tests run_tool() dispatch in agent/tools.py.
HTTP calls to NVD are mocked — no network required.

Run:
    python evaluators/tool_routing_eval.py
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

AGENT_PATH = Path(__file__).parents[3] / "synack-agent-prep"
sys.path.insert(0, str(AGENT_PATH))

from agent.tools import run_tool

# ── Mock NVD responses ─────────────────────────────────────────────────────────
# Each scenario returns what the real NVD API would return for that query.

MOCK_RESPONSES = {
    "search_results": {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2014-0160",
                    "descriptions": [
                        {"lang": "en", "value": "The Heartbleed bug allows reading memory of systems protected by vulnerable OpenSSL versions."}
                    ]
                }
            }
        ]
    },
    "log4j_results": {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2021-44228",
                    "descriptions": [
                        {"lang": "en", "value": "Apache Log4j2 JNDI features used in configuration, log messages, and parameters do not protect against attacker controlled LDAP."}
                    ]
                }
            }
        ]
    },
    "heartbleed_details": {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2014-0160",
                    "descriptions": [
                        {"lang": "en", "value": "The Heartbleed bug allows reading memory of systems protected by vulnerable OpenSSL versions."}
                    ],
                    "metrics": {
                        "cvssMetricV2": [
                            {"cvssData": {"baseScore": 5.0, "baseSeverity": "HIGH"}}
                        ]
                    },
                    "references": [
                        {"url": "https://heartbleed.com/"}
                    ]
                }
            }
        ]
    },
    "empty_results": {
        "vulnerabilities": []
    },
}


def make_mock_response(scenario: str) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = MOCK_RESPONSES[scenario]
    mock.raise_for_status.return_value = None
    return mock


# ── Load test cases ────────────────────────────────────────────────────────────
DATA_FILE = Path(__file__).parents[1] / "data" / "tool_routing_cases.json"
with open(DATA_FILE) as f:
    cases = json.load(f)

passed = 0
failed = 0
rows   = []

for case in cases:
    cid      = case["id"]
    tool     = case["tool"]
    args     = case["args"]
    scenario = case["mock_scenario"]
    expected = case["expected_contains"]

    if scenario:
        mock_resp = make_mock_response(scenario)
        with patch("agent.tools.requests.get", return_value=mock_resp):
            result = run_tool(tool, args)
    else:
        result = run_tool(tool, args)

    ok = expected in result
    status = "PASS" if ok else "FAIL"

    if ok:
        passed += 1
    else:
        failed += 1

    rows.append((cid, tool, status, case["notes"], result[:60]))

# ── Print results ──────────────────────────────────────────────────────────────
total = passed + failed
print(f"\nTool Routing Eval — {passed}/{total} passed")
print(f"{'─'*80}")
print(f"{'ID':<8} {'Tool':<22} {'Status':<6}  {'Notes':<35} Result")
print(f"{'─'*80}")
for cid, tool, status, notes, result in rows:
    marker = "✓" if status == "PASS" else "✗"
    print(f"{cid:<8} {tool:<22} {marker} {status:<4}  {notes[:35]:<35} {result}")
print(f"{'─'*80}")
print(f"PASSED: {passed}/{total}")

if failed > 0:
    sys.exit(1)
