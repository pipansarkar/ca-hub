"""Structured AI calls. Default: Google Gemini free tier (GEMINI_API_KEY).
Optional paid Claude: AI_PROVIDER=claude + ANTHROPIC_API_KEY."""
from __future__ import annotations

import os
import sys
import time
from typing import Type, TypeVar

from pydantic import BaseModel

from config import GEMINI_MODELS, SECONDS_BETWEEN_CALLS

PROVIDER = os.environ.get("AI_PROVIDER", "gemini")
CLAUDE_MODEL = "claude-haiku-5-5"
T = TypeVar("T", bound=BaseModel)


class QuotaExhausted(Exception):
    pass


_last_call = 0.0
_dead_models: set = set()


def _pace() -> None:
    global _last_call
    wait = SECONDS_BETWEEN_CALLS - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def ask(system: str, user: str, schema: Type[T], max_tokens: int = 16000) -> T:
    _pace()
    if PROVIDER == "claude":
        import anthropic

        r = anthropic.Anthropic().messages.parse(
            model=CLAUDE_MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}], output_format=schema)
        if r.stop_reason in ("refusal", "max_tokens"):
            raise RuntimeError(f"Claude stopped: {r.stop_reason}")
        return r.parsed_output

    from google import genai
    from google.genai import errors, types

    client = genai.Client(http_options=types.HttpOptions(timeout=120_000))
    cfg = types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens,
                                      temperature=0.2, response_mime_type="application/json",
                                      response_schema=schema)
    last = None
    # Round-robin: try every live model once, then wait and go round again.
    for rnd in range(5):
        for model in GEMINI_MODELS:
            if model in _dead_models:
                continue
            try:
                r = client.models.generate_content(model=model, contents=user, config=cfg)
                return r.parsed if r.parsed is not None else schema.model_validate_json(r.text)
            except errors.ClientError as exc:  # 4xx
                last = exc
                if exc.code in (401, 403):
                    raise SystemExit(f"Gemini rejected the API key: {exc}")
                if exc.code in (404, 429):  # gone, or out of free quota today
                    print(f"[skip-model] {model}: {exc.code}", file=sys.stderr)
                    _dead_models.add(model)
                else:
                    print(f"[error] {model}: {str(exc)[:150]}", file=sys.stderr)
            except Exception as exc:  # 503 busy, 504 timeout, bad JSON
                last = exc
                print(f"[busy] {model}: {str(exc)[:80]}", file=sys.stderr)
        if len(_dead_models) == len(GEMINI_MODELS):
            break
        time.sleep(45 * (rnd + 1))
    if len(_dead_models) == len(GEMINI_MODELS):
        raise QuotaExhausted(str(last))
    raise RuntimeError(f"AI call failed: {last}")
