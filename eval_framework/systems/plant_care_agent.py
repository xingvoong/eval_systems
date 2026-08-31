"""
Adapter for plant_care_agent.

Tests decide() and care_info() via direct import. LLM fallback in rules.lookup()
is mocked out so no API key is needed for deterministic and guardrail phases.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from eval_framework.adapter import BaseSystemAdapter

AGENT_ROOT = Path(__file__).parents[3] / "plant_care_agent"


def _load_modules():
    if str(AGENT_ROOT) not in sys.path:
        sys.path.insert(0, str(AGENT_ROOT))
    import rules
    import agent
    return rules, agent


class PlantCareAdapter(BaseSystemAdapter):
    name = "plant_care_agent"

    def __init__(self):
        if not (AGENT_ROOT / "agent.py").exists():
            raise FileNotFoundError(
                f"agent.py not found at {AGENT_ROOT}. "
                "Ensure plant_care_agent is checked out at ../../../plant_care_agent"
            )
        self._rules, self._agent = _load_modules()

    def call(self, input: str) -> str:
        """Input format: 'type|days_since_watered'
        Returns the decision string from decide().
        """
        parts = input.split("|")
        plant_type = parts[0].strip()
        days_since = int(parts[1].strip()) if len(parts) > 1 else 0

        last_watered = (datetime.now() - timedelta(days=days_since)).strftime("%Y-%m-%d")
        plant = {"name": "Test Plant", "type": plant_type, "last_watered": last_watered}

        with patch.dict(sys.modules, {"llm": type(sys)("llm")}):
            sys.modules["llm"].get_care_rules = lambda plant_type: None
            return self._agent.decide(plant)

    def validate_input(self, input: str) -> tuple[bool, str]:
        """Reject inputs that are empty, missing the type field, or have non-numeric days."""
        if not input or not input.strip():
            return False, "empty input"
        parts = input.split("|")
        if not parts[0].strip():
            return False, "missing plant type"
        if len(parts) > 1:
            try:
                int(parts[1].strip())
            except ValueError:
                return False, f"days_since_watered must be an integer, got '{parts[1].strip()}'"
        return True, "ok"

    def scan_output(self, output: str) -> tuple[bool, str]:
        """Flag outputs that suggest an unhandled error rather than a care decision."""
        unsafe_signals = ["Traceback", "Error", "Exception", "None"]
        for signal in unsafe_signals:
            if signal in output:
                return False, f"output contains '{signal}'"
        return True, "ok"
