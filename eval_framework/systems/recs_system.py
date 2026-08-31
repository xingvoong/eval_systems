"""
Adapter for recs_system.

Tests the reranking layer (phase_4/rerank.py) using synthetic DataFrames.
No ML-1M data files, embeddings, or scorer model needed — rerank.py is pure logic.

Input format for call(): 'function_name|arg1|arg2|...'
  - filter_seen|user_id|movie_ids|seen_ids
  - apply_freshness|movie_ids_and_scores|movie_titles
  - enforce_diversity|movie_ids_and_scores|genre_lists|top_n

For guardrail phases, input is a JSON-encoded rerank scenario.
"""
import json
import sys
from pathlib import Path

import pandas as pd

from eval_framework.adapter import BaseSystemAdapter

RECS_ROOT = Path(__file__).parents[3] / "recs_system"
PHASE4 = RECS_ROOT / "phase_4"


def _load_rerank():
    for p in [str(RECS_ROOT / "phase_1"), str(RECS_ROOT / "phase_2"),
              str(RECS_ROOT / "phase_3"), str(PHASE4)]:
        if p not in sys.path:
            sys.path.insert(0, p)
    import rerank as rerank_mod
    return rerank_mod


class RecsSystemAdapter(BaseSystemAdapter):
    name = "recs_system"

    def __init__(self):
        if not (PHASE4 / "rerank.py").exists():
            raise FileNotFoundError(
                f"rerank.py not found at {PHASE4}. "
                "Ensure recs_system is checked out at ../../../recs_system"
            )
        self._rerank = _load_rerank()

    def call(self, input: str) -> str:
        """
        Input format: 'check_name|json_payload'

        check_name options:
          filter_seen   — payload: {"candidates": [[id, score], ...], "seen": [id, ...]}
          apply_freshness — payload: {"candidates": [[id, score], ...], "titles": {id: title}}
          enforce_diversity — payload: {"candidates": [[id, score], ...], "genres": {id: [g, ...]}, "top_n": n}
        """
        parts = input.split("|", 1)
        check = parts[0].strip()
        payload = json.loads(parts[1]) if len(parts) > 1 else {}

        if check == "filter_seen":
            candidates = [tuple(x) for x in payload["candidates"]]
            seen = set(payload["seen"])
            result = self._rerank.filter_seen(candidates, seen)
            return json.dumps({"remaining": [list(x) for x in result]})

        elif check == "apply_freshness":
            candidates = [tuple(x) for x in payload["candidates"]]
            titles = {int(k): v for k, v in payload["titles"].items()}
            movies_df = pd.DataFrame([
                {"movie_id": mid, "title": title, "genres": "Action", "genre_list": ["Action"]}
                for mid, title in titles.items()
            ])
            result = self._rerank.apply_freshness(candidates, movies_df)
            # return whether scores changed relative ordering
            original_order = [x[0] for x in candidates]
            new_order = [x[0] for x in result]
            return json.dumps({"original_order": original_order, "new_order": new_order})

        elif check == "enforce_diversity":
            candidates = [tuple(x) for x in payload["candidates"]]
            genres = {int(k): v for k, v in payload["genres"].items()}
            top_n = payload.get("top_n", 10)
            movies_df = pd.DataFrame([
                {"movie_id": mid, "title": f"Movie {mid}", "genres": "|".join(g), "genre_list": g}
                for mid, g in genres.items()
            ])
            result = self._rerank.enforce_diversity(candidates, movies_df, top_n=top_n)
            all_genres = set()
            for mid, _ in result:
                all_genres.update(genres.get(mid, []))
            return json.dumps({"count": len(result), "distinct_genres": sorted(all_genres)})

        return json.dumps({"error": f"unknown check '{check}'"})

    def validate_input(self, input: str) -> tuple[bool, str]:
        """Reject empty inputs or unknown check names."""
        if not input or not input.strip():
            return False, "empty input"
        parts = input.split("|", 1)
        check = parts[0].strip()
        known = {"filter_seen", "apply_freshness", "enforce_diversity"}
        if check not in known:
            return False, f"unknown check '{check}' — must be one of {sorted(known)}"
        if len(parts) < 2 or not parts[1].strip():
            return False, "missing JSON payload"
        try:
            json.loads(parts[1])
        except json.JSONDecodeError as e:
            return False, f"invalid JSON payload: {e}"
        return True, "ok"

    def scan_output(self, output: str) -> tuple[bool, str]:
        """Flag outputs that contain error signals or are not valid JSON."""
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return False, "output is not valid JSON"
        if "error" in parsed:
            return False, f"output contains error: {parsed['error']}"
        if "Traceback" in output or "Exception" in output:
            return False, "output contains stack trace"
        return True, "ok"
