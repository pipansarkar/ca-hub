"""Write each app's JSON (in the exact format that app already reads) from store/items.

apps/today/    current_affairs_today      (English)
apps/bengali/  current_affairs_in_bengali (Bengali)
apps/marathi/  current_affairs_marathi    (Marathi)

To add an app: write an exporter function and register it in EXPORTERS.
"""
from __future__ import annotations

import json
import shutil
from collections import defaultdict

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


# ---------------------------------------------------------------- today
TODAY_CAT = {"polity": "Polity", "economy": "Economy", "banking": "Banking", "schemes": "Schemes",
             "international": "International", "defence": "Defence", "science": "Science & Tech",
             "environment": "Environment", "culture": "Art & Culture", "reports_indices": "Reports & Indices",
             "important_days": "Important Days", "sports": "Sports", "awards": "Awards",
             "appointments": "Appointments", "national": "National"}


def today_category(i):
    r = i["region"]
    if r == "national":
        return TODAY_CAT.get(i["category"], "National")
    return "West Bengal" if r == "west_bengal" else "Tripura/NE" if r in NORTH_EAST else "States"
TODAY_TAGS = {"UPSC", "Bank", "SSC", "Railways", "WBCS", "TPSC", "State PSC"}


def export_today(items, out):
    def conv(i):
        L = {"en": i["langs"]["en"]}  # English only; Bengali has its own app
        return {
            "id": i["id"],
            "category": today_category(i),
            "state": STATES.get(i["region"], ""),
            "tags": [t for t in i["tags"] if t in TODAY_TAGS],
            **{k: {"title": b["title"], "one_liner": b["one_liner"], "summary": b["summary"],
                   "key_points": b["points"]} for k, b in L.items()},
            "mcq": {"answer": i["answers"][0],
                    **{k: {"question": b["mcqs"][0]["question"], "options": b["mcqs"][0]["options"]}
                       for k, b in L.items()}},
            "source_name": i["source_name"], "source_url": i["source_url"],
        }

    mine = [i for i in items if "en" in i["langs"]]
    days = {d: {"date": d, "ai_assisted": True, "items": [conv(i) for i in its]}
            for d, its in by_date(mine).items()}
    dates = sorted(days, reverse=True)
    for d, day in days.items():
        save(out / f"{d}.json", day)
    months = sorted({d[:7] for d in dates}, reverse=True)
    for m in months:
        save(out / "months" / f"{m}.json", {"month": m, "days": [days[d] for d in dates if d.startswith(m)]})
    save(out / "index.json", {"latest": dates[0] if dates else None, "dates": dates, "months": months})


# ---------------------------------------------------------------- bengali
BN_CAT = {"polity": "polity", "economy": "economy", "banking": "banking", "schemes": "schemes",
          "international": "international", "defence": "defence", "science": "science",
          "environment": "environment", "culture": "culture", "reports_indices": "reports_indices",
          "important_days": "important_days", "sports": "sports", "awards": "appointments_awards",
          "appointments": "appointments_awards", "national": "national"}


def bn_category(i):
    r = i["region"]
    if r == "national":
        return BN_CAT.get(i["category"], "national")
    return {"west_bengal": "west_bengal", "tripura": "tripura"}.get(r) or ("north_east" if r in NORTH_EAST else "states")


def export_bengali(items, out):
    def conv(i):
        b = i["langs"]["bn"]
        return {"id": i["id"], "date": i["date"],
                "category": bn_category(i),
                "title_bn": b["title"], "points_bn": b["points"], "static_gk_bn": b["static_gk"],
                "mcqs": [{"question": q["question"], "options": q["options"], "answer_index": a,
                          "explanation": q["explanation"]} for q, a in zip(b["mcqs"], i["answers"])],
                "source_name": i["source_name"], "source_url": i["source_url"]}

    mine = [i for i in items if "bn" in i["langs"]]
    groups = by_date(mine)
    for d, its in groups.items():
        save(out / "days" / f"{d}.json", {"date": d, "generated_at": max(i["time"] for i in its),
                                          "items": [conv(i) for i in its]})
    dates = sorted(groups, reverse=True)
    save(out / "index.json", {"latest": dates[0] if dates else None, "dates": dates})


# ---------------------------------------------------------------- marathi
MR_CAT = {"polity": "राज्यव्यवस्था", "economy": "अर्थव्यवस्था", "banking": "बँकिंग", "schemes": "योजना",
          "international": "आंतरराष्ट्रीय", "defence": "संरक्षण", "science": "विज्ञान-तंत्रज्ञान",
          "environment": "पर्यावरण", "culture": "कला-संस्कृती", "reports_indices": "अहवाल-निर्देशांक",
          "important_days": "महत्त्वाचे दिवस", "sports": "क्रीडा", "awards": "पुरस्कार-नियुक्ती",
          "appointments": "पुरस्कार-नियुक्ती", "national": "राष्ट्रीय"}


def export_marathi(items, out):
    def conv(i):
        b, maha = i["langs"]["mr"], i["region"] == "maharashtra"
        return {"id": i["id"], "lang": "mr", "date": i["date"], "time": i["time"],
                "title": b["title"], "points": b["points"],
                "category": "महाराष्ट्र" if maha else MR_CAT.get(i["category"], "राष्ट्रीय") if i["region"] == "national" else "इतर राज्ये",
                "maharashtra": maha,
                "source": i["source_name"], "source_url": i["source_url"],
                "mcqs": [{"q": q["question"], "options": q["options"], "answer": a,
                          "explanation": q["explanation"]} for q, a in zip(b["mcqs"], i["answers"])]}

    mine = [conv(i) for i in items if "mr" in i["langs"]]
    months = defaultdict(list)
    for i in mine:
        months[i["date"][:7]].append(i)
    for m, its in months.items():
        save(out / "months" / f"{m}.json", its)
    updated = now_ist().isoformat(timespec="minutes")
    save(out / "latest.json", {"updated": updated, "items": mine[:150]})
    save(out / "index.json", {"updated": updated, "months": sorted(months, reverse=True)})


EXPORTERS = {"today": export_today, "bengali": export_bengali, "marathi": export_marathi}
APP_LANG = {"today": "en", "bengali": "bn", "marathi": "mr"}


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
    for name, fn in EXPORTERS.items():
        out = APPS / name
        shutil.rmtree(out, ignore_errors=True)  # full rebuild keeps retractions effective
        fn(items, out)
        export_static_gk(out, APP_LANG[name])
    print(f"[export] {len(items)} items -> {', '.join(EXPORTERS)}")


if __name__ == "__main__":
    main()
