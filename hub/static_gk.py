"""Static GK question bank from Wikidata (CC0 public-domain facts, no AI -> nothing invented).

Writes store/static_gk.json; export.py copies each app's language into apps/<app>/static_gk.json.
Run weekly (facts change slowly).  Add a topic = add an entry to TOPICS.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from collections import defaultdict

import requests

from config import LANGS, STORE

ENDPOINT = "https://query.wikidata.org/sparql"
UA = {"User-Agent": "ca-hub/1.0 (https://github.com/pipansarkar/ca-hub; educational exam-prep app)",
      "Accept": "application/sparql-results+json"}
LANG_CODES = list(LANGS)  # en, bn, mr

# Each topic: SPARQL returning ?s (subject) and ?a (answer) items, plus question templates per language.
# {x} = subject label.  A subject may have several valid answers (e.g. two capitals); all are kept
# out of the wrong options.
TOPICS = {
    "state_capital": {
        "label": {"en": "Capitals of states & UTs", "hi": "राज्यों व केंद्र शासित प्रदेशों की राजधानियाँ", "bn": "রাজ্য ও কেন্দ্রশাসিত অঞ্চলের রাজধানী",
                  "mr": "राज्ये व केंद्रशासित प्रदेशांच्या राजधान्या"},
        "q": {"en": "What is the capital of {x}?", "hi": "{x} की राजधानी क्या है?", "bn": "{x}-এর রাজধানী কোনটি?", "mr": "{x} ची राजधानी कोणती?"},
        "sparql": "?s wdt:P31 ?t. VALUES ?t {wd:Q12443800 wd:Q467745} ?s wdt:P36 ?a.",
    },
    "national_park_state": {
        "label": {"en": "National parks of India", "hi": "भारत के राष्ट्रीय उद्यान", "bn": "ভারতের জাতীয় উদ্যান", "mr": "भारतातील राष्ट्रीय उद्याने"},
        "q": {"en": "{x} is in which state/UT?", "hi": "{x} किस राज्य/केंद्र शासित प्रदेश में है?", "bn": "{x} কোন রাজ্যে অবস্থিত?", "mr": "{x} कोणत्या राज्यात आहे?"},
        "sparql": "?s wdt:P31 wd:Q46169; wdt:P17 wd:Q668; wdt:P131/wdt:P131?/wdt:P131? ?a. ?a wdt:P31 ?t. "
                  "VALUES ?t {wd:Q12443800 wd:Q467745}",
    },
    "heritage_site_state": {
        "label": {"en": "UNESCO World Heritage Sites in India", "hi": "भारत के यूनेस्को विश्व धरोहर स्थल", "bn": "ভারতের ইউনেস্কো বিশ্ব ঐতিহ্য স্থান",
                  "mr": "भारतातील युनेस्को जागतिक वारसा स्थळे"},
        "q": {"en": "The World Heritage Site '{x}' is in which state/UT?", "hi": "विश्व धरोहर स्थल '{x}' किस राज्य/केंद्र शासित प्रदेश में है?",
              "bn": "বিশ্ব ঐতিহ্য স্থান '{x}' কোন রাজ্যে অবস্থিত?",
              "mr": "जागतिक वारसा स्थळ '{x}' कोणत्या राज्यात आहे?"},
        "sparql": "?s wdt:P1435 wd:Q9259; wdt:P17 wd:Q668; wdt:P131/wdt:P131?/wdt:P131? ?a. ?a wdt:P31 ?t. "
                  "VALUES ?t {wd:Q12443800 wd:Q467745}",
    },
    "country_capital": {
        "label": {"en": "Countries & capitals", "hi": "देश और राजधानियाँ", "bn": "দেশ ও রাজধানী", "mr": "देश व राजधान्या"},
        "q": {"en": "What is the capital of {x}?", "hi": "{x} की राजधानी क्या है?", "bn": "{x}-এর রাজধানী কোনটি?", "mr": "{x} ची राजधानी कोणती?"},
        "sparql": "?s wdt:P31 wd:Q3624078; wdt:P36 ?a. FILTER NOT EXISTS {?s wdt:P576 ?end}",
    },
    "country_currency": {
        "label": {"en": "Countries & currencies", "hi": "देश और मुद्राएँ", "bn": "দেশ ও মুদ্রা", "mr": "देश व चलने"},
        "q": {"en": "What is the currency of {x}?", "hi": "{x} की मुद्रा क्या है?", "bn": "{x}-এর মুদ্রা কী?", "mr": "{x} चे चलन कोणते?"},
        "sparql": "?s wdt:P31 wd:Q3624078; wdt:P38 ?a. FILTER NOT EXISTS {?s wdt:P576 ?end} "
                  "FILTER NOT EXISTS {?a wdt:P582 ?replaced}",
    },
    "intl_org_hq": {
        "label": {"en": "Intergovernmental organisations: headquarters", "hi": "अंतर-सरकारी संगठनों के मुख्यालय", "bn": "আন্তর্জাতিক সংস্থার সদর দপ্তর",
                  "mr": "आंतरराष्ट्रीय संस्थांची मुख्यालये"},
        "q": {"en": "Where is the headquarters of {x}?", "hi": "{x} का मुख्यालय कहाँ है?", "bn": "{x}-এর সদর দপ্তর কোথায়?",
              "mr": "{x} चे मुख्यालय कोठे आहे?"},
        "sparql": "?s wdt:P31/wdt:P279* wd:Q245065; wdt:P159 ?a; wikibase:sitelinks ?n. FILTER(?n >= 40) "
                  "?a wdt:P31/wdt:P279* wd:Q515. FILTER NOT EXISTS {?s wdt:P576 ?end}",
    },
    "indian_bank_hq": {
        "label": {"en": "Indian banks: headquarters", "hi": "भारतीय बैंकों के मुख्यालय", "bn": "ভারতীয় ব্যাংকের সদর দপ্তর",
                  "mr": "भारतीय बँकांची मुख्यालये"},
        "q": {"en": "Where is the headquarters of {x}?", "hi": "{x} का मुख्यालय कहाँ है?", "bn": "{x}-এর সদর দপ্তর কোথায়?",
              "mr": "{x} चे मुख्यालय कोठे आहे?"},
        "sparql": "?s wdt:P31/wdt:P279* wd:Q22687; wdt:P17 wd:Q668; wdt:P159 ?a; wikibase:sitelinks ?n. "
                  "FILTER(?n >= 8) ?a wdt:P31/wdt:P279* wd:Q515. FILTER NOT EXISTS {?s wdt:P576 ?end}",
    },
    "ramsar_state": {
        "label": {"en": "Ramsar wetlands of India", "bn": "ভারতের রামসার জলাভূমি", "hi": "भारत की रामसर आर्द्रभूमियाँ",
                  "mr": "भारतातील रामसर पाणथळ जागा"},
        "q": {"en": "The Ramsar site '{x}' is in which state/UT?", "bn": "রামসার জলাভূমি '{x}' কোন রাজ্যে অবস্থিত?",
              "hi": "रामसर स्थल '{x}' किस राज्य/केंद्र शासित प्रदेश में है?", "mr": "रामसर स्थळ '{x}' कोणत्या राज्यात आहे?"},
        "sparql": "?s wdt:P1435 wd:Q19683138; wdt:P17 wd:Q668; wdt:P131/wdt:P131?/wdt:P131? ?a. ?a wdt:P31 ?t. VALUES ?t {wd:Q12443800 wd:Q467745}",
    },
    "biosphere_state": {
        "label": {"en": "Biosphere reserves of India", "bn": "ভারতের বায়োস্ফিয়ার রিজার্ভ", "hi": "भारत के जैवमंडल आरक्षित क्षेत्र",
                  "mr": "भारतातील जैवावरण राखीव क्षेत्रे"},
        "q": {"en": "{x} is in which state/UT?", "bn": "{x} কোন রাজ্যে অবস্থিত?", "hi": "{x} किस राज्य/केंद्र शासित प्रदेश में है?",
              "mr": "{x} कोणत्या राज्यात आहे?"},
        "sparql": "?s wdt:P31 wd:Q158454; wdt:P17 wd:Q668; wdt:P131/wdt:P131? ?a. ?a wdt:P31 ?t. VALUES ?t {wd:Q12443800 wd:Q467745}",
    },
    "river_mouth": {
        "label": {"en": "Rivers of India: where they flow into", "bn": "ভারতের নদী: কোথায় মিশেছে", "hi": "भारत की नदियाँ: कहाँ मिलती हैं",
                  "mr": "भारतातील नद्या: कुठे मिळतात"},
        "q": {"en": "Into which river or sea does the {x} flow?", "bn": "{x} কোন নদী বা সাগরে গিয়ে মিশেছে?",
              "hi": "{x} किस नदी या सागर में मिलती है?", "mr": "{x} कोणत्या नदीला किंवा समुद्राला मिळते?"},
        "sparql": "?s wdt:P31 wd:Q4022; wdt:P17 wd:Q668; wdt:P403 ?a; wikibase:sitelinks ?n. FILTER(?n >= 15)",
        "max_answers": 1,
    },
    "airport_city": {
        "label": {"en": "Airports of India", "bn": "ভারতের বিমানবন্দর", "hi": "भारत के हवाई अड्डे", "mr": "भारतातील विमानतळ"},
        "q": {"en": "{x} is in which city?", "bn": "{x} কোন শহরে অবস্থিত?", "hi": "{x} किस शहर में है?",
              "mr": "{x} कोणत्या शहरात आहे?"},
        "sparql": "?s wdt:P31/wdt:P279* wd:Q1248784; wdt:P17 wd:Q668; wdt:P931 ?a; wikibase:sitelinks ?n. FILTER(?n >= 12)",
        "max_answers": 1,
        "no_answer_in_subject": True,
    },
    "country_legislature": {
        "label": {"en": "Parliaments of the world", "bn": "বিশ্বের সংসদ", "hi": "विश्व की संसदें", "mr": "जगातील संसद"},
        "q": {"en": "What is the parliament of {x} called?", "bn": "{x}-এর সংসদের নাম কী?", "hi": "{x} की संसद का नाम क्या है?",
              "mr": "{x} च्या संसदेचे नाव काय?"},
        "sparql": "?s wdt:P31 wd:Q3624078; wdt:P194 ?a. FILTER NOT EXISTS {?s wdt:P576 ?end}",
        "max_answers": 1,
        "no_subject_in_answer": True,
    },
    "country_continent": {
        "label": {"en": "Countries & continents", "bn": "দেশ ও মহাদেশ", "hi": "देश और महाद्वीप", "mr": "देश व खंड"},
        "q": {"en": "{x} is in which continent?", "bn": "{x} কোন মহাদেশে অবস্থিত?", "hi": "{x} किस महाद्वीप में है?",
              "mr": "{x} कोणत्या खंडात आहे?"},
        "sparql": "?s wdt:P31 wd:Q3624078; wdt:P30 ?a. FILTER NOT EXISTS {?s wdt:P576 ?end}",
        "max_answers": 1,
    },
}

FACT = {"en": "{q} Answer: {a}.", "bn": "{q} উত্তর: {a}।", "mr": "{q} उत्तर: {a}.", "hi": "{q} उत्तर: {a}।"}


def run(sparql: str) -> list:
    labels = " ".join(
        f'OPTIONAL {{?s rdfs:label ?s_{l}. FILTER(LANG(?s_{l})="{l}")}} '
        f'OPTIONAL {{?a rdfs:label ?a_{l}. FILTER(LANG(?a_{l})="{l}")}}' for l in LANG_CODES)
    q = f"SELECT DISTINCT ?s ?a {' '.join(f'?s_{l} ?a_{l}' for l in LANG_CODES)} WHERE {{ {sparql} {labels} }}"
    for attempt in range(3):
        r = requests.get(ENDPOINT, params={"query": q}, headers=UA, timeout=120)
        if r.status_code == 200:
            return r.json()["results"]["bindings"]
        print(f"[wikidata] {r.status_code}, retrying", file=sys.stderr)
        time.sleep(20 * (attempt + 1))
    r.raise_for_status()
    return []


def build_topic(key: str, t: dict) -> list:
    rows = run(t["sparql"])
    subj = {}
    answers = defaultdict(set)              # subject -> answer ids
    alabel = defaultdict(dict)              # answer id -> {lang: label}
    for b in rows:
        s, a = b["s"]["value"], b["a"]["value"]
        subj.setdefault(s, {})
        for l in LANG_CODES:
            if f"s_{l}" in b:
                subj[s][l] = b[f"s_{l}"]["value"]
            if f"a_{l}" in b:
                alabel[a][l] = b[f"a_{l}"]["value"]
        answers[s].add(a)
    pool = sorted(alabel)
    items = []
    for s, ans in sorted(answers.items()):
        if len(ans) > t.get("max_answers", 2):  # too many valid answers -> ambiguous
            continue
        correct = sorted(ans)[0]
        wrong_pool = [a for a in pool if a not in ans]
        if len(wrong_pool) < 3:
            continue
        rng = random.Random(f"{key}:{s}")
        wrong = rng.sample(wrong_pool, min(12, len(wrong_pool)))
        langs = {}
        for l in LANG_CODES:
            x, c = subj[s].get(l), alabel[correct].get(l)
            opts_w = [alabel[w][l] for w in wrong if l in alabel[w] and alabel[w][l] != c][:3]
            if not x or not c or len(set(opts_w)) < 3 or x.startswith("Q"):
                continue
            if t.get("no_subject_in_answer") and x.split()[-1].lower() in c.lower():
                continue  # e.g. "Parliament of Canada" would give the answer away
            if t.get("no_answer_in_subject") and c.split()[0].lower()[:4] in x.lower():
                continue  # e.g. "Jodhpur Airport" -> Jodhpur
            options = opts_w + [c]
            rng.shuffle(options)
            qtext = t["q"][l].format(x=x)
            langs[l] = {"question": qtext, "options": options, "answer": options.index(c),
                        "fact": FACT[l].format(q=qtext, a=c)}
        if "en" in langs:
            qid = s.rsplit("/", 1)[-1]
            items.append({"id": hashlib.sha1(f"{key}:{qid}".encode()).hexdigest()[:10], "topic": key,
                          "source_url": f"https://www.wikidata.org/wiki/{qid}", "langs": langs})
    return items


def main() -> None:
    old_path = STORE / "static_gk.json"
    old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else {"items": [], "topics": {}}
    bank, topics = [], {}
    for key, t in TOPICS.items():
        try:
            items = build_topic(key, t)
            if not items:
                raise RuntimeError("no questions")
        except Exception as exc:
            # Wikidata timed out etc.: keep this topic's questions from the last good build
            items = [i for i in old["items"] if i["topic"] == key]
            print(f"[keep-old] {key}: {str(exc)[:80]} -> {len(items)} previous questions", file=sys.stderr)
            if not items:
                continue
        per = {l: sum(1 for i in items if l in i["langs"]) for l in LANG_CODES}
        print(f"[topic] {key}: {per}", file=sys.stderr)
        topics[key] = t["label"]
        bank += items
        time.sleep(3)
    if len(bank) < 50:
        raise SystemExit("Static GK build looks broken (too few items); keeping the old bank.")
    STORE.mkdir(exist_ok=True)
    (STORE / "static_gk.json").write_text(json.dumps(
        {"source": "Wikidata (CC0)", "topics": topics, "items": bank}, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] {len(bank)} static GK questions", file=sys.stderr)


if __name__ == "__main__":
    main()
