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

    client = genai.Client()
    cfg = types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens,
                                      temperature=0.2, response_mime_type="application/json",
                                      response_schema=schema)
    last = None
    for model in GEMINI_MODELS:
        if model in _dead_models:
            continue
        for attempt in range(3):
            try:
                r = client.models.generate_content(model=model, contents=user, config=cfg)
                return r.parsed if r.parsed is not None else schema.model_validate_json(r.text)
            except errors.ClientError as exc:
                last = exc
                if exc.code == 429 and attempt == 2:
                    print(f"[quota] {model} exhausted, trying next model", file=sys.stderr)
                    _dead_models.add(model)
                    break
                if exc.code in (401, 403):
                    raise SystemExit(f"Gemini rejected the API key: {exc}")
                if exc.code != 429:
                    print(f"[error] {model}: {exc}", file=sys.stderr)
                    break
            except Exception as exc:  # 5xx, bad JSON
                last = exc
                print(f"[retry] {model} attempt {attempt + 1}: {exc}", file=sys.stderr)
            time.sleep(30 * (attempt + 1))
    if len(_dead_models) == len(GEMINI_MODELS):
        raise QuotaExhausted(str(last))
    raise RuntimeError(f"AI call failed: {last}")
