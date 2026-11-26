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
TODAY_CAT = {"national": "National", "international": "International", "economy": "Banking & Economy",
             "schemes": "Schemes", "appointments": "Appointments", "awards": "Awards", "sports": "Sports",
             "defence": "Defence", "science": "Science", "environment": "Environment"}


def today_category(i):
    r = i["region"]
    if r == "national":
        return TODAY_CAT[i["category"]]
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
BN_CAT = {"national": "national", "international": "international", "economy": "economy",
          "schemes": "national", "appointments": "appointments_awards", "awards": "appointments_awards",
          "sports": "sports", "defence": "national", "science": "science", "environment": "environment"}


def bn_category(i):
    r = i["region"]
    if r == "national":
        return BN_CAT[i["category"]]
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
MR_CAT = {"national": "राष्ट्रीय", "international": "आंतरराष्ट्रीय", "economy": "अर्थव्यवस्था",
          "schemes": "योजना", "appointments": "पुरस्कार-नियुक्ती", "awards": "पुरस्कार-नियुक्ती",
          "sports": "क्रीडा", "defence": "राष्ट्रीय", "science": "विज्ञान-तंत्रज्ञान", "environment": "पर्यावरण"}


def export_marathi(items, out):
    def conv(i):
        b, maha = i["langs"]["mr"], i["region"] == "maharashtra"
        return {"id": i["id"], "lang": "mr", "date": i["date"], "time": i["time"],
                "title": b["title"], "points": b["points"],
                "category": "महाराष्ट्र" if maha else MR_CAT[i["category"]] if i["region"] == "national" else "इतर राज्ये",
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


def main() -> None:
    items = all_items()
    for name, fn in EXPORTERS.items():
        out = APPS / name
        shutil.rmtree(out, ignore_errors=True)  # full rebuild keeps retractions effective
        fn(items, out)
    print(f"[export] {len(items)} items -> {', '.join(EXPORTERS)}")


if __name__ == "__main__":
    main()
