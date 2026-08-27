"""
Adapter for llm_inference_gateway.

Calls route_request() directly, mocking out the LLM providers so no real
HTTP calls are made. Returns the routed model name as the "output" — that's
what the routing eval checks.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from eval_framework.adapter import BaseSystemAdapter

GATEWAY_PATH = Path(__file__).parents[3] / "llm_inference_gateway"


class LLMGatewayAdapter(BaseSystemAdapter):
    name = "llm_inference_gateway"

    def __init__(self) -> None:
        if str(GATEWAY_PATH) not in sys.path:
            sys.path.insert(0, str(GATEWAY_PATH))
        # Pre-import so patch("app.router.OpenAIProvider") can resolve the target.
        import app.router  # noqa: F401

    def _route_request(self, prompt: str, priority=None, max_cost=None) -> tuple[str, str]:
        """Internal: returns (model_name, routing_reason) with mocked providers."""
        with patch("app.router.OpenAIProvider", side_effect=lambda model: MagicMock(_model=model)) as MockOAI, \
             patch("app.router.HuggingFaceProvider", side_effect=lambda model: MagicMock(_model=model)) as MockHF:
            from app.router import route_request
            _, model_name, reason = route_request(
                prompt=prompt,
                priority=priority,
                max_cost=max_cost,
            )
        return model_name, reason

    def call(self, input: str, priority: str | None = None, max_cost: float | None = None) -> str:
        """Route a prompt and return the selected model name."""
        model_name, _ = self._route_request(input, priority=priority, max_cost=max_cost)
        return model_name

    def route(self, prompt: str, priority: str | None = None, max_cost: float | None = None) -> tuple[str, str]:
        """Returns (model_name, routing_reason). Used by the routing evaluator."""
        return self._route_request(prompt, priority=priority, max_cost=max_cost)
