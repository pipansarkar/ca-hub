"""Important days calendar -> apps/<app>/important_days.json

International days: the official UN list (un.org/en/observances/list-days-weeks), refreshed weekly.
National days: Government of India observances (fixed list below).
Names are translated once with the AI and cached in store/days_i18n.json.
"""
from __future__ import annotations

import html
import json
import re
import sys
from typing import List

import requests
from pydantic import BaseModel

from config import APPS, LANGS, STORE

UN_URL = "https://www.un.org/en/observances/list-days-weeks"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
MON = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
I18N = STORE / "days_i18n.json"

# Government of India national days and observances (fixed dates).
NATIONAL = [
    ("01-12", "National Youth Day (birth anniversary of Swami Vivekananda)"),
    ("01-15", "Indian Army Day"),
    ("01-23", "Parakram Diwas (birth anniversary of Netaji Subhas Chandra Bose)"),
    ("01-24", "National Girl Child Day"),
    ("01-25", "National Voters' Day"),
    ("01-26", "Republic Day"),
    ("01-30", "Martyrs' Day (Shaheed Diwas)"),
    ("02-28", "National Science Day"),
    ("04-21", "Civil Services Day"),
    ("04-24", "National Panchayati Raj Day"),
    ("05-11", "National Technology Day"),
    ("06-29", "National Statistics Day"),
    ("07-01", "National Doctors' Day"),
    ("08-07", "National Handloom Day"),
    ("08-15", "Independence Day"),
    ("08-23", "National Space Day"),
    ("08-29", "National Sports Day"),
    ("09-05", "Teachers' Day"),
    ("09-14", "Hindi Diwas"),
    ("09-15", "Engineers' Day"),
    ("10-02", "Gandhi Jayanti"),
    ("10-08", "Indian Air Force Day"),
    ("10-31", "National Unity Day (Rashtriya Ekta Diwas)"),
    ("11-11", "National Education Day"),
    ("11-14", "Children's Day"),
    ("11-26", "Constitution Day (Samvidhan Divas)"),
    ("12-04", "Indian Navy Day"),
    ("12-07", "Armed Forces Flag Day"),
    ("12-14", "National Energy Conservation Day"),
    ("12-22", "National Mathematics Day"),
    ("12-23", "Kisan Diwas (National Farmers' Day)"),
    ("12-25", "Good Governance Day"),
]


def un_days() -> list:
    page = requests.get(UN_URL, headers=UA, timeout=60).text
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "|", page)))
    out, seen = [], set()
    # "...||World Wetlands Day|| ... (|A/RES/75/317|)| ... ||02 Feb||"
    for name, day, mon in re.findall(r"\|\|\s*([A-Z][^|]{6,120}?)\s*\|\|[^|]*(?:\|[^|]*){0,12}?\|\|(\d{2}) ([A-Z][a-z]{2})\|\|", text):
        name = re.sub(r"\s*\[[A-Z]+\]\s*$", "", name).strip()  # drop "[FAO]" agency tags
        if mon not in MON or "Week" in name or "Decade" in name or name in seen:
            continue
        seen.add(name)
        out.append((f"{MON[mon]:02d}-{int(day):02d}", name))
    return out


class Tr(BaseModel):
    n: int
    name: str


class Trs(BaseModel):
    items: List[Tr]


def translate(names: list, lang: str) -> dict:
    from ai import ask
    cache = json.loads(I18N.read_text(encoding="utf-8")) if I18N.exists() else {}
    todo = [n for n in names if n not in cache.get(lang, {})]
    for k in range(0, len(todo), 40):
        chunk = todo[k:k + 40]
        sys_msg = (f"Translate these names of official observance days into {LANGS[lang]['name']}, as they are "
                   "written in exam books. Keep person names and well-known proper nouns recognisable. n must match.")
        out = ask(sys_msg, json.dumps([{"n": i, "name": x} for i, x in enumerate(chunk)], ensure_ascii=False), Trs, 6000)
        for t in out.items:
            if 0 <= t.n < len(chunk) and t.name.strip():
                cache.setdefault(lang, {})[chunk[t.n]] = t.name.strip()
        I18N.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return cache.get(lang, {})


def main() -> None:
    try:
        intl = un_days()
    except Exception as exc:
        print(f"[days] UN list failed: {exc}", file=sys.stderr)
        intl = []
    if len(intl) < 100:  # page changed or failed: keep the last good list
        prev = json.loads((STORE / "important_days.json").read_text(encoding="utf-8")) if (STORE / "important_days.json").exists() else []
        intl = [(d["date"], d["name"]) for d in prev if d["scope"] == "international"] or intl
    days = sorted([{"date": d, "name": n, "scope": "international", "source": "United Nations"} for d, n in intl] +
                  [{"date": d, "name": n, "scope": "national", "source": "Government of India"} for d, n in NATIONAL],
                  key=lambda d: d["date"])
    (STORE / "important_days.json").write_text(json.dumps(days, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"[days] {len(intl)} international + {len(NATIONAL)} national", file=sys.stderr)

    from export import APP_LANG
    for app, lang in APP_LANG.items():
        names = translate([d["name"] for d in days], lang) if lang != "en" else {}
        def tidy(n: str) -> str:  # "X (X)" -> "X" when a translation repeats itself
            m = re.fullmatch(r"(.+?)\s*\((.+)\)", n)
            return m.group(1).strip() if m and m.group(1).strip() == m.group(2).strip() else n
        rows = [{**d, "name": tidy(names.get(d["name"], d["name"]))} for d in days]
        (APPS / app).mkdir(parents=True, exist_ok=True)
        (APPS / app / "important_days.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        print(f"[days] {app}: {len(rows)} days", file=sys.stderr)


if __name__ == "__main__":
    main()
