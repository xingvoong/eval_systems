"""
Adapter for yc_startup_validator.

Uses phase2/serving/predictor.py and model_loader.py directly.
Model artifacts live in yc_startup_validator_app/model/ — no server needed.

call() takes a startup description and returns the score label (e.g. "strong", "promising").
"""
import sys
from pathlib import Path

from eval_framework.adapter import BaseSystemAdapter

YC_ROOT = Path(__file__).parents[3] / "YC_analysis_and_startup_prediction"
SERVING_DIR = YC_ROOT / "phase2" / "serving"


def _load_serving():
    for p in [str(SERVING_DIR)]:
        if p not in sys.path:
            sys.path.insert(0, p)
    from model_loader import get_artifacts
    from predictor import run_prediction, interpret_score
    return get_artifacts, run_prediction, interpret_score


class YCStartupValidatorAdapter(BaseSystemAdapter):
    name = "yc_startup_validator"

    def __init__(self):
        if not (SERVING_DIR / "predictor.py").exists():
            raise FileNotFoundError(
                f"predictor.py not found at {SERVING_DIR}. "
                "Ensure YC_analysis_and_startup_prediction is checked out at "
                "../../../YC_analysis_and_startup_prediction"
            )
        self._get_artifacts, self._run_prediction, self._interpret_score = _load_serving()
        self._artifacts = self._get_artifacts()

    def call(self, input: str) -> str:
        """Run prediction on a startup description. Returns the level label."""
        if not self._artifacts.loaded:
            return "model_not_loaded"
        result = self._run_prediction(
            self._artifacts.vectorizer,
            self._artifacts.model,
            input,
            top_k=8,
            version=self._artifacts.version,
        )
        return result["level"]

    def validate_input(self, input: str) -> tuple[bool, str]:
        """Reject empty or very short descriptions that can't be meaningfully classified."""
        if not input or not input.strip():
            return False, "empty input"
        if len(input.strip()) < 10:
            return False, f"description too short ({len(input.strip())} chars) — minimum 10"
        return True, "ok"

    def scan_output(self, output: str) -> tuple[bool, str]:
        """Flag outputs that are not a known level label."""
        valid_levels = {"strong", "promising", "weak", "low", "model_not_loaded"}
        if output.strip() not in valid_levels:
            return False, f"unexpected output '{output}' — expected one of {sorted(valid_levels)}"
        if output.strip() == "model_not_loaded":
            return False, "model failed to load"
        return True, "ok"
