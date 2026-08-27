import json
import os
from eval_framework.case import EvalCase


JUDGE_SYSTEM = """You are an expert evaluator of LLM responses.
You will be given a user prompt, a reference response (considered correct and complete),
and a candidate response to evaluate.

Score the candidate on each dimension from 1 to 5:
  accuracy     — Is the answer factually correct?
  completeness — Does it address all parts of the prompt?
  conciseness  — Is it appropriately brief without omitting essentials?

Return ONLY valid JSON with no extra text:
{"accuracy": <int>, "completeness": <int>, "conciseness": <int>, "reasoning": "<one sentence>"}"""

JUDGE_USER_TEMPLATE = """Prompt:
{prompt}

Reference response:
{reference}

Candidate response:
{candidate}

Score the candidate response."""


class LLMJudge:
    def __init__(self, model: str = "openai/gpt-oss-20b", api_key: str | None = None):
        from groq import Groq
        self.model = model
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise ValueError("GROQ_API_KEY not set and no api_key passed")
        self.client = Groq(api_key=key)

    def score(self, prompt: str, reference: str, candidate: str) -> dict:
        user_msg = JUDGE_USER_TEMPLATE.format(
            prompt=prompt,
            reference=reference,
            candidate=candidate,
        )
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        return json.loads(raw)

    def validate_consistency(self, case: EvalCase, n: int = 5) -> float:
        """Run same case n times, return max variance across dimensions."""
        prompt = case.input
        reference = case.metadata.get("reference_response", "")
        candidate = case.metadata.get("response", "")

        all_scores: list[dict] = []
        for _ in range(n):
            all_scores.append(self.score(prompt, reference, candidate))

        dims = ["accuracy", "completeness", "conciseness"]
        max_variance = 0.0
        for dim in dims:
            values = [s[dim] for s in all_scores if dim in s]
            if len(values) < 2:
                continue
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            if variance > max_variance:
                max_variance = variance

        return max_variance

    def validate_calibration(self, cases: list[EvalCase], human_labels: list[float]) -> dict:
        """Returns Spearman correlation per dimension between judge scores and human labels."""
        from scipy.stats import spearmanr

        dims = ["accuracy", "completeness", "conciseness"]
        scores_by_dim: dict[str, list[float]] = {d: [] for d in dims}

        for case in cases:
            prompt = case.input
            reference = case.metadata.get("reference_response", "")
            candidate = case.metadata.get("response", "")
            result = self.score(prompt, reference, candidate)
            for dim in dims:
                scores_by_dim[dim].append(float(result.get(dim, 0)))

        correlations = {}
        for dim in dims:
            corr, pval = spearmanr(scores_by_dim[dim], human_labels)
            correlations[dim] = {"spearman_r": round(corr, 3), "p_value": round(pval, 4)}

        return correlations
