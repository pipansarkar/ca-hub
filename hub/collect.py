"""Collect new official releases into store/pool.json. No AI, no cost. Run hourly.

OFFICIAL SOURCES ONLY. PIB allows free reuse with prominent credit, provided the
material is reproduced accurately and not used in a misleading or derogatory way.
Never add newspapers or other current-affairs sites.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys

import feedparser
import requests

from config import POOL, STORE, now_ist

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}

# PIB regional offices -> default state ("" = decided per release). PIB's regional RSS
# feeds are empty, so we read each office's "All Releases" page (English) instead.
PIB_OFFICES = {
    3: ("PIB Delhi", ""), 1: ("PIB Mumbai", "maharashtra"), 5: ("PIB Hyderabad", "telangana"),
    6: ("PIB Chennai", "tamil_nadu"), 17: ("PIB Chandigarh", "punjab"), 19: ("PIB Kolkata", "west_bengal"),
    20: ("PIB Bengaluru", "karnataka"), 21: ("PIB Bhubaneswar", "odisha"), 22: ("PIB Ahmedabad", "gujarat"),
    23: ("PIB Guwahati", "assam"), 24: ("PIB Thiruvananthapuram", "kerala"), 30: ("PIB Imphal", "manipur"),
    31: ("PIB Aizawl", "mizoram"), 32: ("PIB Agartala", "tripura"), 33: ("PIB Gangtok", "sikkim"),
    34: ("PIB Kohima", "nagaland"), 35: ("PIB Shillong", "meghalaya"), 36: ("PIB Itanagar", "arunachal_pradesh"),
    37: ("PIB Lucknow", "uttar_pradesh"), 38: ("PIB Bhopal", "madhya_pradesh"), 39: ("PIB Jaipur", "rajasthan"),
    40: ("PIB Patna", "bihar"), 41: ("PIB Ranchi", "jharkhand"), 42: ("PIB Shimla", "himachal_pradesh"),
    43: ("PIB Raipur", "chhattisgarh"), 44: ("PIB Jammu & Kashmir", "jammu_kashmir"),
    45: ("PIB Vijayawada", "andhra_pradesh"), 46: ("PIB Dehradun", "uttarakhand"),
}
# Other official RSS feeds: name, url, kind, default region
FEEDS = [
    ("RBI", "https://www.rbi.org.in/pressreleases_rss.xml", "rss", "national"),
    ("महासंवाद (महाराष्ट्र शासन)", "https://mahasamvad.in/feed/", "wordpress", "maharashtra"),
    ("महासंवाद (महाराष्ट्र शासन)", "https://mahasamvad.in/feed/?paged=2", "wordpress", "maharashtra"),
    # Add other official state government feeds here.
]
KEEP_DAYS = 10


def clean(s: str) -> str:
    s = re.sub(r"(?is)<(script|style|blockquote)\b.*?</\1>", " ", s or "")
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("﻿", "")
    s = re.sub(r"[ \t\r\f\v\xa0]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def get(url: str) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r


def pib_body(link: str) -> str:
    prid = re.search(r"PRID=(\d+)", link).group(1)
    page = get(f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}").text
    i = page.find('id="PdfDiv"')
    text = clean(page[i:i + 60000] if i >= 0 else page)
    text = text.replace('id="PdfDiv" style="display: none;">', "")
    text = re.split(r"\((?:Release ID|रिलीज़ आईडी)", text)[0]
    return text.strip()[:6000]


def pib_list(reg: int, day: dt.date) -> list:
    """(link, title) of every English release from one PIB office on one day."""
    url = f"https://pib.gov.in/allRel.aspx?reg={reg}&lang=1"
    sess = requests.Session()
    page = sess.get(url, headers=UA, timeout=40).text
    if day != now_ist().date():  # older days need an ASP.NET postback with the date selected
        form = dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', page))
        form.update(dict(re.findall(r'<select name="([^"]+)"[^>]*>.*?<option selected="selected" value="([^"]*)"',
                                    page, re.S)))
        p = "ctl00$ContentPlaceHolder1$"
        form.update({p + "ddlday": str(day.day), p + "ddlMonth": str(day.month), p + "ddlYear": str(day.year),
                     "__EVENTTARGET": p + "ddlday"})
        page = sess.post(url, data=form, headers=UA, timeout=40).text
    out, seen = [], set()
    for prid, title in re.findall(r"PRID=(\d+)[^>]*>([^<]{5,})", page):
        if prid not in seen:
            seen.add(prid)
            out.append((f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}", clean(title)))
    return out


def add(pool, titles, stamp, name, region, link, title, body_fn) -> bool:
    if not link or not title or link in pool or title.lower() in titles:
        return False
    try:
        body = body_fn()
    except Exception as exc:
        print(f"[body-fail] {link}: {exc}", file=sys.stderr)
        return False  # try again next run
    pool[link] = {"source": name, "region": region, "title": title, "body": body,
                  "link": link, "first_seen": stamp, "status": "new"}
    titles.add(title.lower())
    return True


def main() -> None:
    STORE.mkdir(exist_ok=True)
    pool = json.loads(POOL.read_text(encoding="utf-8")) if POOL.exists() else {}
    titles = {v["title"].lower() for v in pool.values()}
    stamp = now_ist().isoformat(timespec="seconds")
    added = 0
    today = now_ist().date()
    days = [today] + ([today - dt.timedelta(days=1)] if now_ist().hour < 2 else [])  # catch late releases
    for reg, (name, region) in PIB_OFFICES.items():
        for day in days:
            try:
                rels = pib_list(reg, day)
            except Exception as exc:
                print(f"[skip] {name} {day}: {exc}", file=sys.stderr)
                continue
            print(f"[pib] {name} {day}: {len(rels)}", file=sys.stderr)
            for link, title in rels:
                added += add(pool, titles, stamp, name, region, link, title, lambda: pib_body(link))
    for name, url, kind, region in FEEDS:
        try:
            entries = feedparser.parse(get(url).content.lstrip(b"\xef\xbb\xbf")).entries
        except Exception as exc:
            print(f"[skip] {name} {url}: {exc}", file=sys.stderr)
            continue
        print(f"[feed] {name}: {len(entries)}", file=sys.stderr)
        for e in entries:
            if kind == "wordpress" and e.get("content"):
                fn = lambda e=e: clean(e.content[0].value)[:6000]
            else:
                fn = lambda e=e: clean(e.get("summary", ""))[:6000]
            added += add(pool, titles, stamp, name, region, e.get("link", ""), clean(e.get("title", "")), fn)
    cutoff = (now_ist() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    pool = {k: v for k, v in pool.items() if v["first_seen"] >= cutoff}
    POOL.write_text(json.dumps(pool, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ok] +{added} new, {len(pool)} in pool", file=sys.stderr)


if __name__ == "__main__":
    main()
