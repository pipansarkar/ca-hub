"""Monthly digest PDFs for every app: apps/<app>/pdf/<YYYY-MM>.pdf

Rendered from HTML with headless Chrome, so Bengali / Devanagari text is shaped correctly
(on GitHub Actions, install fonts-noto-core first). Rebuilds the current and previous month.

  python hub/monthly_pdf.py            # recent months
  python hub/monthly_pdf.py --all      # every month
"""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from config import APPS, now_ist
from export import APP_LANG

APP_NAME = {"en": "Current Affairs Today", "bn": "কারেন্ট অ্যাফেয়ার্স", "mr": "चालू घडामोडी", "hi": "करेंट अफेयर्स"}
MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "bn": ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"],
    "mr": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
}
# section key -> (categories, {lang: label}); state news goes to "states"
SECTIONS = [
    ("national", ["national", "polity", "important_days", "culture"], {"en": "National", "bn": "জাতীয়", "mr": "राष्ट्रीय", "hi": "राष्ट्रीय"}),
    ("international", ["international"], {"en": "International", "bn": "আন্তর্জাতিক", "mr": "आंतरराष्ट्रीय", "hi": "अंतरराष्ट्रीय"}),
    ("financial", ["economy", "banking"], {"en": "Financial Awareness", "bn": "অর্থনীতি ও ব্যাংকিং", "mr": "अर्थव्यवस्था व बँकिंग", "hi": "अर्थव्यवस्था एवं बैंकिंग"}),
    ("schemes", ["schemes"], {"en": "Govt Schemes", "bn": "সরকারি প্রকল্প", "mr": "सरकारी योजना", "hi": "सरकारी योजनाएँ"}),
    ("sports", ["sports"], {"en": "Sports", "bn": "খেলাধুলা", "mr": "क्रीडा", "hi": "खेल"}),
    ("defence", ["defence"], {"en": "Defence", "bn": "প্রতিরক্ষা", "mr": "संरक्षण", "hi": "रक्षा"}),
    ("science", ["science"], {"en": "Science & Tech", "bn": "বিজ্ঞান ও প্রযুক্তি", "mr": "विज्ञान-तंत्रज्ञान", "hi": "विज्ञान एवं प्रौद्योगिकी"}),
    ("environment", ["environment"], {"en": "Environment", "bn": "পরিবেশ", "mr": "पर्यावरण", "hi": "पर्यावरण"}),
    ("awards", ["awards", "appointments"], {"en": "Awards & Appointments", "bn": "পুরস্কার ও নিয়োগ", "mr": "पुरस्कार व नियुक्ती", "hi": "पुरस्कार एवं नियुक्तियाँ"}),
    ("reports", ["reports_indices"], {"en": "Reports & Indices", "bn": "রিপোর্ট ও সূচক", "mr": "अहवाल व निर्देशांक", "hi": "रिपोर्ट एवं सूचकांक"}),
    ("states", [], {"en": "States", "bn": "রাজ্য", "mr": "राज्ये", "hi": "राज्य"}),
]
LABEL = {
    "gk": {"en": "Related static GK", "bn": "সম্পর্কিত স্ট্যাটিক জিকে", "mr": "संबंधित स्थिर GK", "hi": "संबंधित स्टैटिक GK"},
    "src": {"en": "Source", "bn": "সূত্র", "mr": "स्रोत", "hi": "स्रोत"},
    "note": {"en": "Based on official releases (PIB, MEA, RBI, SEBI, IRDAI, ISRO, state governments). AI-generated notes, checked "
                   "automatically against the source. Static GK: Wikidata. Not an official government publication.",
             "bn": "সরকারি বিজ্ঞপ্তি (PIB, বিদেশ মন্ত্রক, RBI, SEBI, IRDAI, ISRO, রাজ্য সরকার) থেকে। AI দিয়ে তৈরি, মূল সূত্রের সঙ্গে স্বয়ংক্রিয়ভাবে মেলানো। এটি সরকারি প্রকাশনা নয়।",
             "mr": "अधिकृत प्रसिद्धिपत्रकांवर आधारित (PIB, परराष्ट्र मंत्रालय, RBI, SEBI, IRDAI, ISRO, राज्य शासन). AI ने तयार केलेले, मूळ स्रोताशी आपोआप पडताळलेले. हे शासकीय प्रकाशन नाही.",
             "hi": "आधिकारिक विज्ञप्तियों पर आधारित (PIB, विदेश मंत्रालय, RBI, SEBI, IRDAI, ISRO, राज्य सरकारें)। AI द्वारा तैयार, मूल स्रोत से अपने-आप मिलाए गए। यह सरकारी प्रकाशन नहीं है।"},
}
FONT = {"en": "'Noto Sans', 'Helvetica', sans-serif",
        "bn": "'Noto Sans Bengali', 'Kohinoor Bangla', 'Bangla MN', sans-serif",
        "mr": "'Noto Sans Devanagari', 'Kohinoor Devanagari', sans-serif",
        "hi": "'Noto Sans Devanagari', 'Kohinoor Devanagari', sans-serif"}


def chrome() -> str:
    for c in (os.environ.get("CHROME"), "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if c and (shutil.which(c) or Path(c).exists()):
            return c
    raise SystemExit("Chrome/Chromium not found")


def section_of(item: dict) -> str:
    if item.get("region", "national") != "national":
        return "states"
    for key, cats, _ in SECTIONS:
        if item["category"] in cats:
            return key
    return "national"


def pretty_date(iso: str, lang: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[lang][int(m) - 1]} {y}"


def build_html(lang: str, month: str, days: list) -> str:
    e = html.escape
    items = [i for d in sorted(days, key=lambda d: d["date"]) for i in d["items"]]
    y, m = month.split("-")
    out = [f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 16mm 14mm; }}
body {{ font-family: {FONT[lang]}; font-size: 10.5pt; line-height: 1.5; color: #111; }}
.cover {{ border-bottom: 3px solid #3949ab; padding-bottom: 10px; margin-bottom: 8px; }}
.cover h1 {{ font-size: 22pt; margin: 0; }} .cover div {{ color: #555; font-size: 12pt; }}
h2 {{ font-size: 12.5pt; background: #e8ebf7; padding: 6px 10px; margin: 20px 0 6px; page-break-after: avoid; }}
h3 {{ font-size: 11pt; margin: 12px 0 3px; color: #283593; page-break-after: avoid; }}
.date {{ color: #666; font-size: 9pt; }}
ul {{ margin: 4px 0 4px 18px; padding: 0; }}
.gk {{ background: #f3f4f8; border-left: 3px solid #3949ab; padding: 5px 10px; font-size: 9.5pt; margin-top: 5px; }}
.src {{ color: #888; font-size: 8.5pt; }} .item {{ page-break-inside: avoid; }}
.note {{ color: #777; font-size: 8.5pt; margin-top: 24px; border-top: 1px solid #ddd; padding-top: 6px; }}
</style></head><body>
<div class="cover"><h1>{e(APP_NAME[lang])}</h1><div>{e(MONTHS[lang][int(m) - 1])} {y} · {len(items)}</div></div>"""]
    n = 0
    for key, _, labels in SECTIONS:
        its = [i for i in items if section_of(i) == key]
        if not its:
            continue
        out.append(f"<h2>{e(labels[lang])}</h2>")
        for i in its:
            n += 1
            t = i["text"]
            state = f" · {e(i['state'])}" if i.get("state") else ""
            out.append(f'<div class="item"><h3>{n}. {e(t["title"])}</h3>'
                       f'<div class="date">{e(pretty_date(i["date"], lang))}{state}</div><div>{e(t["summary"])}</div>')
            if t.get("key_points"):
                out.append("<ul>" + "".join(f"<li>{e(p)}</li>" for p in t["key_points"]) + "</ul>")
            if i.get("gk"):
                out.append(f'<div class="gk"><b>{e(LABEL["gk"][lang])}</b><br>' + "<br>".join(e(g) for g in i["gk"]) + "</div>")
            out.append(f'<div class="src">{e(LABEL["src"][lang])}: {e(i["source_name"])}</div></div>')
    out.append(f'<div class="note">{e(LABEL["note"][lang])}</div></body></html>')
    return "\n".join(out)


def render(html_text: str, pdf: Path) -> None:
    pdf.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "digest.html"
        src.write_text(html_text, encoding="utf-8")
        subprocess.run([chrome(), "--headless", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                        f"--user-data-dir={tmp}/profile", f"--print-to-pdf={pdf}", src.as_uri()],
                       check=True, capture_output=True, timeout=180)


def main() -> None:
    months_wanted = None if "--all" in sys.argv else {
        now_ist().strftime("%Y-%m"), (now_ist().replace(day=1) - __import__("datetime").timedelta(days=1)).strftime("%Y-%m")}
    for app, lang in APP_LANG.items():
        for f in sorted((APPS / app / "months").glob("*.json")):
            if months_wanted and f.stem not in months_wanted:
                continue
            days = json.loads(f.read_text(encoding="utf-8"))["days"]
            pdf = APPS / app / "pdf" / f"{f.stem}.pdf"
            render(build_html(lang, f.stem, days), pdf)
            print(f"[pdf] {pdf.relative_to(APPS)} ({pdf.stat().st_size // 1024} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
