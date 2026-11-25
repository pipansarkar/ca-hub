"""Automatic quality gates. Items are auto-published, so these are the safety net."""
from __future__ import annotations

import re
from typing import List, Optional

DIGITS = str.maketrans("०१२३४५६७८९০১২৩৪৫৬৭৮৯", "01234567890123456789")


def numbers_in(text: str) -> set:
    """Numbers in text; Devanagari/Bengali digits normalised, separators removed (1,00,000 -> 100000)."""
    out = set()
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", (text or "").translate(DIGITS)):
        n = m.replace(",", "").rstrip(".")
        if n:
            out.add(n.lstrip("0") or "0")
    return out


def factual_text(L: dict, answers: List[int]) -> str:
    """Text stated as fact: title, lines, points, correct options, explanations.
    Wrong options are distractors and may contain other numbers."""
    parts = [L["title"], L["one_liner"], L["summary"], *L["points"]]
    for q, a in zip(L["mcqs"], answers):
        parts += [q["question"], q["options"][a], q["explanation"]]
    return "\n".join(parts)


def check_lang(L: dict, answers: List[int], source: str, script: Optional[str]) -> Optional[str]:
    """Return a rejection reason, or None if the language block is OK."""
    for k in ("title", "one_liner", "summary"):
        if not isinstance(L.get(k), str) or not L[k].strip():
            return f"empty {k}"
    if not 2 <= len(L["points"]) <= 5 or not all(p.strip() for p in L["points"]):
        return "points count"
    if len(L["mcqs"]) != len(answers) or len(answers) != 2:
        return "need 2 mcqs"
    for q, a in zip(L["mcqs"], answers):
        opts = [o.strip() for o in q["options"]]
        if len(opts) != 4 or len(set(opts)) != 4 or not all(opts) or not 0 <= a < 4:
            return "bad mcq options"
        if not q["question"].strip():
            return "empty question"
    text = factual_text(L, answers)
    if script and len(re.findall(script, L["title"] + " ".join(L["points"]))) < 20:
        return "wrong script"
    invented = numbers_in(text) - numbers_in(source)
    if invented:
        return f"numbers not in source: {sorted(invented)[:5]}"
    return None


def safe_static_gk(gk: str, source: str) -> str:
    """Static GK comes from model memory; drop it if it states numbers we can't verify."""
    gk = (gk or "").strip()
    return "" if numbers_in(gk) - numbers_in(source) else gk
