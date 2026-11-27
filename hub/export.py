"""Write each app's JSON from store/items (one shared format, one language per app).

apps/today/    current_affairs_today      (English)
apps/bengali/  current_affairs_in_bengali (Bengali)
apps/marathi/  current_affairs_marathi    (Marathi)
apps/hindi/    current_affairs_hindi      (Hindi)

To add an app: add its folder and language to APP_LANG (and the language to config.LANGS).
"""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

from config import APPS, ITEMS, NORTH_EAST, STATES, now_ist


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def all_items() -> list:
    items = []
    for f in sorted(ITEMS.glob("*.json")):
        items += json.loads(f.read_text(encoding="utf-8"))
    items = [i for i in items if not i.get("retracted")]
    return sorted(items, key=lambda i: i["time"], reverse=True)


def by_date(items):
    d = defaultdict(list)
    for i in items:
        d[i["date"]].append(i)
    return d


# ---------------------------------------------------------------- common app format
# All three apps share one codebase and read the same format in their own language:
#   index.json {latest, dates, months} · <date>.json {date, items} · months/<YYYY-MM>.json {month, days}
# Categories, regions and sections are language-neutral keys; each app localizes the labels.
STATE_NAMES = json.loads((Path(__file__).parent / "state_names.json").read_text(encoding="utf-8"))


def to_app(i: dict, lang: str) -> dict:
    b = i["langs"][lang]
    mcqs = [{"question": q["question"], "options": q["options"], "answer": a, "explanation": q["explanation"]}
            for q, a in zip(b["mcqs"], i["answers"])]
    text = {"title": b["title"], "one_liner": b["one_liner"], "summary": b["summary"], "key_points": b["points"]}
    out = {
        "id": i["id"], "date": i["date"], "time": i["time"], "category": i["category"], "region": i["region"],
        "state": STATE_NAMES.get(i["region"], {}).get(lang, ""), "tags": i["tags"],
        "source_name": i["source_name"], "source_url": i["source_url"],
        "text": text, "mcqs": mcqs, "mcq": mcqs[0] if mcqs else None,
        "gk": [g[lang] for g in i.get("gk", []) if lang in g],
        "importance": i.get("importance", 5),
    }
    if lang == "en":
        out["en"] = text  # older Today-app builds read "en"
    return out


def export_app(items, out, lang):
    mine = [i for i in items if lang in i["langs"]]
    days = {d: {"date": d, "items": [to_app(i, lang) for i in its]} for d, its in by_date(mine).items()}
    dates = sorted(days, reverse=True)
    for d, day in days.items():
        save(out / f"{d}.json", day)
    months = sorted({d[:7] for d in dates}, reverse=True)
    for m in months:
        save(out / "months" / f"{m}.json", {"month": m, "days": [days[d] for d in dates if d.startswith(m)]})
    save(out / "index.json", {"latest": dates[0] if dates else None, "dates": dates, "months": months,
                              "updated": now_ist().isoformat(timespec="minutes")})


APP_LANG = {"today": "en", "bengali": "bn", "marathi": "mr", "hindi": "hi"}  # app folder -> language


def export_static_gk(out, lang):
    """apps/<app>/static_gk.json: {"source", "topics": {key: label}, "items": [question...]}"""
    src = ITEMS.parent / "static_gk.json"
    if not src.exists():
        return
    bank = json.loads(src.read_text(encoding="utf-8"))
    items = [{"id": i["id"], "topic": i["topic"], **i["langs"][lang], "source_url": i["source_url"]}
             for i in bank["items"] if lang in i["langs"]]
    topics = {k: v.get(lang, v["en"]) for k, v in bank["topics"].items()
              if any(i["topic"] == k for i in items)}
    save(out / "static_gk.json", {"source": bank["source"], "topics": topics, "items": items})


def main() -> None:
    items = all_items()
    for name, lang in APP_LANG.items():
        out = APPS / name
        # full rebuild keeps retractions effective; monthly PDFs (built separately) are kept
        if out.exists():
            for child in out.iterdir():
                if child.name not in ("pdf", "important_days.json"):  # built by their own scripts
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
        export_app(items, out, lang)
        export_static_gk(out, lang)
    print(f"[export] {len(items)} items -> {', '.join(APP_LANG)}")


if __name__ == "__main__":
    main()
