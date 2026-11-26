"""Translate already-published items into a language they don't have yet (e.g. after adding Hindi).

  python hub/backfill_lang.py hi
Uses the same translation prompt and checks as generate.py. Safe to re-run.
"""
from __future__ import annotations

import json
import sys

import export
from ai import QuotaExhausted, ask
from checks import check_lang, safe_static_gk
from config import BATCH, ITEMS, LANGS
from generate import TItems, lang_block, log, translate_sys


def main(lang: str) -> None:
    cfg = LANGS[lang]
    done = 0
    for f in sorted(ITEMS.glob("*.json")):
        items = json.loads(f.read_text(encoding="utf-8"))
        todo = [i for i in items if lang not in i["langs"] and not i.get("retracted")]
        for k in range(0, len(todo), BATCH):
            chunk = todo[k:k + BATCH]
            payload = [{"n": n, **i["langs"]["en"]} for n, i in enumerate(chunk)]
            try:
                out = ask(translate_sys(lang), json.dumps(payload, ensure_ascii=False), TItems).items
            except QuotaExhausted:
                log("[quota] stopping; run again later")
                break
            except Exception as exc:
                log(f"  ! batch failed: {exc}")
                continue
            for t in out:
                if not 0 <= t.n < len(chunk):
                    continue
                it = chunk[t.n]
                block = lang_block(t)
                # the original release text is not stored; check numbers against the verified English core
                src = json.dumps(it["langs"]["en"], ensure_ascii=False)
                reason = check_lang(block, it["answers"], src, cfg.get("script"))
                if reason:
                    log(f"  reject {lang} ({reason}): {it['langs']['en']['title'][:60]}")
                    continue
                block["static_gk"] = safe_static_gk(block["static_gk"], src)
                it["langs"][lang] = block
                done += 1
        f.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[ok] {done} items translated to {lang}")
    export.main()


if __name__ == "__main__":
    main(sys.argv[1])
