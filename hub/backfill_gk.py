"""Add related GK (Wikidata facts) to stored items that don't have it yet. Safe to re-run."""
from __future__ import annotations

import json
import sys
from typing import List

from pydantic import BaseModel

import export
from ai import ask
from config import ITEMS
from generate import Entity
from related_gk import facts_for


class Ents(BaseModel):
    n: int
    entities: List[Entity]


class AllEnts(BaseModel):
    items: List[Ents]


SYS = """For each news item, list up to 4 key named entities that exams attach static GK to:
organisations (ministries, regulators, banks, UN bodies), countries, Indian states/UTs, and places such as
national parks. Give the full official English name (e.g. "National Film Development Corporation of India"),
the abbreviation ('' if none), the kind (country | state | organisation | place; state = Indian state/UT only)
and whether it is Indian. No people. n must match the input."""


def main() -> None:
    refresh = "--refresh" in sys.argv  # recompute facts from stored entities (no AI calls)
    for f in sorted(ITEMS.glob("*.json")):
        items = json.loads(f.read_text(encoding="utf-8"))
        if refresh:
            for i in items:
                if i.get("entities"):
                    i["gk"] = facts_for(i["entities"])
        todo = [i for i in items if "gk" not in i or ("--reextract" in sys.argv and
                                                    not all("indian" in e for e in i.get("entities", [{}])))]
        for k in range(0, len(todo), 15):
            chunk = todo[k:k + 15]
            payload = [{"n": n, "title": i["langs"]["en"]["title"], "summary": i["langs"]["en"]["summary"]}
                       for n, i in enumerate(chunk)]
            out = ask(SYS, json.dumps(payload, ensure_ascii=False), AllEnts, 4000).items
            for e in out:
                if 0 <= e.n < len(chunk):
                    it = chunk[e.n]
                    it["entities"] = [x.model_dump() for x in e.entities][:4]
                    it["gk"] = facts_for(it["entities"])
                    print(f"[gk] {len(it['gk'])} facts: {it['langs']['en']['title'][:70]}", file=sys.stderr)
        f.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    export.main()


if __name__ == "__main__":
    main()
