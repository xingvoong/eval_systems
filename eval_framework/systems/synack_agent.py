"""
Adapter for synack-agent-prep (01_react_agent/react_agent.py).

Loads the module by file path (the directory starts with a digit, so
normal import won't work). Mocks groq and dotenv before loading so no
live API client is created.

validate_input() and scan_output() delegate to the loaded module.
call() returns a stub — the real agent requires a live Groq API key.
"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

from eval_framework.adapter import BaseSystemAdapter

AGENT_ROOT = Path(__file__).parents[3] / "synack-agent-prep"
REACT_AGENT_FILE = AGENT_ROOT / "01_react_agent" / "react_agent.py"


def _load_react_agent():
    # Mock out modules that require external deps or live API keys.
    # agent/tools.py imports requests; react_agent.py imports groq and dotenv.
    sys.modules.setdefault("groq", MagicMock())
    sys.modules.setdefault("dotenv", MagicMock())
    sys.modules.setdefault("requests", MagicMock())
    if str(AGENT_ROOT) not in sys.path:
        sys.path.insert(0, str(AGENT_ROOT))
    spec = importlib.util.spec_from_file_location("react_agent", str(REACT_AGENT_FILE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SynackAgentAdapter(BaseSystemAdapter):
    name = "synack_agent"

    def __init__(self) -> None:
        if not REACT_AGENT_FILE.exists():
            raise FileNotFoundError(
                f"react_agent.py not found at {REACT_AGENT_FILE}. "
                "Ensure synack-agent-prep is checked out at ../../../synack-agent-prep"
            )
        self._module = _load_react_agent()

    def validate_input(self, input: str) -> tuple[bool, str]:
        return self._module.validate_input(input)

    def scan_output(self, output: str) -> tuple[bool, str]:
        return self._module.scan_output(output)

    def call(self, input: str) -> str:
        """Stub — real agent requires a live Groq API key."""
        return f"[stub] SynackAgent received: {input[:80]}"
