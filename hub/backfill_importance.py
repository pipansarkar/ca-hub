"""Give stored items an exam-importance score (1-10) if they don't have one. Safe to re-run."""
from __future__ import annotations

import json
import sys
from typing import List

from pydantic import BaseModel

import export
from ai import ask
from config import ITEMS


class Score(BaseModel):
    n: int
    importance: int


class Scores(BaseModel):
    items: List[Score]


SYS = """Rate each Indian current-affairs item 1-10 for how likely it is to be asked in competitive exams
(UPSC, state PSC, Bank, SSC, Railways). 10 = landmark (major scheme launch, summit, constitutional/legal
change, top appointment, big award, index ranking); 5 = typical; 1 = minor routine event. n must match the input."""


def main() -> None:
    for f in sorted(ITEMS.glob("*.json")):
        items = json.loads(f.read_text(encoding="utf-8"))
        todo = [i for i in items if "importance" not in i]
        for k in range(0, len(todo), 30):
            chunk = todo[k:k + 30]
            payload = [{"n": n, "title": i["langs"]["en"]["title"], "category": i["category"]} for n, i in enumerate(chunk)]
            for sc in ask(SYS, json.dumps(payload, ensure_ascii=False), Scores, 3000).items:
                if 0 <= sc.n < len(chunk):
                    chunk[sc.n]["importance"] = max(1, min(10, sc.importance))
        f.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[ok] {f.name}: scored {sum('importance' in i for i in items)}/{len(items)}", file=sys.stderr)
    export.main()


if __name__ == "__main__":
    main()
