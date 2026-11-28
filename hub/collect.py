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
    # MahaSamvad returns 403 to GitHub Actions servers (works from a home connection); skipped if blocked.
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


MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def recent(text: str, days: int = KEEP_DAYS) -> bool:
    """True if the first date found in text ('25 November, 2026' or 'August 12, 2026') is recent."""
    m = re.search(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS}),?\s+(\d{{4}})|({MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})", text)
    if not m:
        return False
    d, mon, y = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(5), m.group(4), m.group(6))
    when = dt.datetime.strptime(f"{d} {mon} {y}", "%d %B %Y").date()
    return (now_ist().date() - when).days <= days


def mea_list() -> list:
    """(link, title, body) of recent MEA press releases (international relations)."""
    base = "https://www.mea.gov.in/FrontEnd/"
    hdr = {**UA, "X-Requested-With": "XMLHttpRequest"}
    r = requests.get(base + "FetchPublicationListingData", headers=hdr, timeout=40, params={
        "publicationId": 51, "page": 1, "PageSize": 20, "PLngId": 1, "SortBy": "", "KeywordName": "",
        "DateRange": "", "IsInternalMEA": "false"})
    page = r.text
    if "pressReleaseList" not in page:
        print(f"[mea] unexpected response: HTTP {r.status_code}, {len(page)} bytes: {page[:160]!r}", file=sys.stderr)
    out = []
    rows = re.findall(r'class="date">([^<]+)</span>.*?<a href="(/press-releases\?dtl/\d+/[^"]*)">\s*([^<]+?)\s*</a>',
                      page, re.S)
    for date, href, title in rows:
        if not recent(date):
            continue
        pkid = re.search(r"dtl/(\d+)/", href).group(1)
        link = "https://www.mea.gov.in" + href
        out.append((link, clean(title), lambda pkid=pkid: clean(requests.get(
            base + "FetchPublicationDetailData", headers=hdr, timeout=40,
            params={"pkid": pkid, "languageId": 1}).text)[:6000]))
    return out


def isro_list() -> list:
    """(link, title, body) of recent ISRO press releases (space / science)."""
    page = get("https://www.isro.gov.in/Press.html").text
    out = []
    for href, title in re.findall(r'href="([A-Za-z0-9_\-]+\.html)"[^>]*?title="([^"]{10,200})"', page, re.S)[:15]:
        link = "https://www.isro.gov.in/" + href

        def body(link=link):
            t = clean(re.sub(r"(?is)<(nav|header|footer)\b.*?</\1>", " ", get(link).text))
            return t[:6000]
        out.append((link, clean(title), body))
    return out


def sebi_list() -> list:
    """(link, title, body) of recent SEBI press releases (capital markets)."""
    page = get("https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=6&ssid=23&smid=0").text
    out = []
    for row in re.split(r"<tr\b", page):
        d = re.search(r"<td>([A-Z][a-z]{2} \d{2}, \d{4})</td>", row)
        a = re.search(r'href="(https://www\.sebi\.gov\.in/media-and-notifications/press-releases/[^"]+\.html)"[^>]*title="([^"]+)"', row)
        if not (d and a) or (now_ist().date() - dt.datetime.strptime(d.group(1), "%b %d, %Y").date()).days > KEEP_DAYS:
            continue
        link = a.group(1)
        out.append((link, clean(a.group(2)), lambda link=link: clean(get(link).text.split("</header>")[-1])[:6000]))
    return out


def pdf_text(url: str) -> str:
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(get(url).content))
    text = " ".join((p.extract_text() or "") for p in reader.pages[:4])
    for bad, good in {"Ʃ": "tt", "Ɵ": "ti", "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}.items():
        text = text.replace(bad, good)
    return clean(text)[:6000]


def irdai_list() -> list:
    """(link, title, body) of recent IRDAI press releases (insurance). Releases are PDFs."""
    page = get("https://irdai.gov.in/press-releases").text
    out = []
    for row in re.split(r"<tr\b", page):
        pdf = re.search(r'href="(https://irdai\.gov\.in/documents/[^"]+\.pdf[^"]*)"', row)
        d = re.search(r">\s*(\d{2}-\d{2}-\d{4})\s*<", row)
        if not (pdf and d) or (now_ist().date() - dt.datetime.strptime(d.group(1), "%d-%m-%Y").date()).days > KEEP_DAYS:
            continue
        cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        title = next((c for c in cells if len(c) > 15), "")
        title = title.split(" / ")[-1].strip()  # bilingual "Hindi / English" -> English
        link = html.unescape(pdf.group(1))
        out.append((link, title, lambda link=link: pdf_text(link)))
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
    for name, fn in (("MEA", mea_list), ("ISRO", isro_list), ("SEBI", sebi_list), ("IRDAI", irdai_list)):
        try:
            rels = fn()
        except Exception as exc:
            print(f"[skip] {name}: {exc}", file=sys.stderr)
            continue
        print(f"[web] {name}: {len(rels)}", file=sys.stderr)
        for link, title, body_fn in rels:
            if link in pool or title.lower() in titles:
                continue
            if name == "ISRO":  # the ISRO list has no dates; check the release text instead
                try:
                    text = body_fn()
                except Exception as exc:
                    print(f"[body-fail] {link}: {exc}", file=sys.stderr)
                    continue
                if not recent(text):
                    continue
                body_fn = lambda text=text: text
            added += add(pool, titles, stamp, name, "national", link, title, body_fn)
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
