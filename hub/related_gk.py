"""Related static GK for a news item, from Wikidata (verified facts, no AI-written facts).

The AI only names the entities in a release ("NABARD", "Japan", "Assam"). This module looks each
one up on Wikidata and builds short facts in every language: HQ, year founded, capital, currency,
location. "Who currently holds a post" facts are deliberately NOT used: Wikidata often lags behind
appointments (tested: stale SEBI chair, conflicting heads of state). Results are cached in store/gk_cache.json for 30 days.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time

import requests

from config import LANGS, STORE

API = "https://www.wikidata.org/w/api.php"
UA = {"User-Agent": "ca-hub/1.0 (https://github.com/pipansarkar/ca-hub; educational exam-prep app)"}
CACHE = STORE / "gk_cache.json"
LANG_CODES = list(LANGS)
TTL_DAYS = 30

COUNTRY = {"Q6256", "Q3624078"}
INDIAN_STATE = {"Q12443800", "Q467745"}
PARK = {"Q46169", "Q473972"}  # national park, protected area

# fact templates: key -> {lang: "..."}; {x} = entity, {v} = value
T = {
    "capital": {"hi": "{x} की राजधानी: {v}", "en": "Capital of {x}: {v}", "bn": "{x}-এর রাজধানী: {v}", "mr": "{x} ची राजधानी: {v}"},
    "currency": {"hi": "{x} की मुद्रा: {v}", "en": "Currency of {x}: {v}", "bn": "{x}-এর মুদ্রা: {v}", "mr": "{x} चे चलन: {v}"},
    "hog": {"hi": "{x} के शासनाध्यक्ष: {v}", "en": "Head of government of {x}: {v}", "bn": "{x}-এর সরকারপ্রধান: {v}", "mr": "{x} चे शासनप्रमुख: {v}"},
    "hos": {"hi": "{x} के राष्ट्राध्यक्ष: {v}", "en": "Head of state of {x}: {v}", "bn": "{x}-এর রাষ্ট্রপ্রধান: {v}", "mr": "{x} चे राष्ट्रप्रमुख: {v}"},
    "cm": {"hi": "{x} के मुख्यमंत्री: {v}", "en": "Chief Minister of {x}: {v}", "bn": "{x}-এর মুখ্যমন্ত্রী: {v}", "mr": "{x} चे मुख्यमंत्री: {v}"},
    "hq": {"hi": "{x} का मुख्यालय: {v}", "en": "Headquarters of {x}: {v}", "bn": "{x}-এর সদর দপ্তর: {v}", "mr": "{x} चे मुख्यालय: {v}"},
    "founded": {"hi": "{x} की स्थापना: {v}", "en": "{x} was established in {v}", "bn": "{x} প্রতিষ্ঠিত হয় {v} সালে", "mr": "{x} ची स्थापना: {v}"},
    "chair": {"hi": "{x} के प्रमुख: {v}", "en": "Head of {x}: {v}", "bn": "{x}-এর প্রধান: {v}", "mr": "{x} चे प्रमुख: {v}"},
    "state": {"hi": "{x} {v} में है", "en": "{x} is in {v}", "bn": "{x} অবস্থিত {v}-এ", "mr": "{x} हे {v} मध्ये आहे"},
}


def _api(**params) -> dict:
    params.update(format="json")
    for attempt in range(3):
        try:
            r = requests.get(API, params=params, headers=UA, timeout=40)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(5 * (attempt + 1))
    return {}


def _one_current(claims: dict, prop: str) -> list:
    """The current holder of a post, only if Wikidata has exactly one (avoids conflicting/acting entries)."""
    ids = _ids(claims, prop, True)
    return ids if len(ids) == 1 else []


def _ids(claims: dict, prop: str, current_only: bool = False) -> list:
    out = []
    for c in claims.get(prop, []):
        if current_only and "P582" in c.get("qualifiers", {}):  # has an end time -> former
            continue
        if c.get("rank") == "deprecated":
            continue
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "id" in v:
            out.append((c.get("rank") == "preferred", v["id"]))
    out.sort(key=lambda x: not x[0])
    return [i for _, i in out]


def _year(claims: dict, prop: str):
    for c in claims.get(prop, []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "time" in v:
            return v["time"][1:5].lstrip("0")
    return None


def _labels(qids: list) -> dict:
    out = {}
    for k in range(0, len(qids), 40):
        d = _api(action="wbgetentities", ids="|".join(qids[k:k + 40]), props="labels",
                 languages="|".join(LANG_CODES))
        for q, e in d.get("entities", {}).items():
            out[q] = {l: v["value"] for l, v in e.get("labels", {}).items()}
    return out


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def lookup(name: str, kind: str = "", indian=None) -> list:
    """Facts about one entity: [{"en": "...", "bn": "...", "mr": "..."}].
    kind: country | state | organisation | place. Only exact label/alias matches of that kind are used."""
    found = _api(action="wbsearchentities", search=name, language="en", type="item", limit=8).get("search", [])
    found = [f for f in found if f.get("match", {}).get("type") in ("label", "alias")
             and _norm(f["match"].get("text", "")) == _norm(name)]
    if not found:
        return []
    ents = _api(action="wbgetentities", ids="|".join(f["id"] for f in found), props="claims|labels",
                languages="|".join(LANG_CODES)).get("entities", {})
    matches = []  # every exact-name candidate of the right kind
    for f in found:
        if f["id"] == "Q668":  # India itself: "capital of India" is not worth showing
            return []
        e = ents.get(f["id"], {})
        claims = e.get("claims", {})
        kinds = set(_ids(claims, "P31"))
        if "P576" in claims:  # dissolved / historical (e.g. Kingdom of Nepal)
            continue
        if kind == "country" and not kinds & COUNTRY or kind == "state" and not kinds & INDIAN_STATE \
                or kind == "place" and not kinds & PARK or kind == "organisation" and (kinds & (COUNTRY | INDIAN_STATE)):
            continue
        if kind in ("organisation", "place") and indian is not None:
            if indian != ("Q668" in _ids(claims, "P17")):  # e.g. India's NFDC vs Malaysia's NFDC
                continue
        if not (kinds & (COUNTRY | INDIAN_STATE | PARK)) and "P159" not in claims:
            continue
        matches.append((e, claims, kinds))
    if len(matches) != 1:  # none, or ambiguous ("Ministry of Foreign Affairs" exists in many countries)
        return []
    for e, claims, kinds in matches:
        facts = []  # (template key, value qid or literal)
        if kinds & COUNTRY:
            facts += [("capital", q) for q in _ids(claims, "P36")[:1]]
            facts += [("currency", q) for q in _ids(claims, "P38", True)[:1]]
        elif kinds & INDIAN_STATE:
            facts += [("capital", q) for q in _ids(claims, "P36")[:1]]
        elif kinds & PARK:
            facts += [("state", q) for q in _ids(claims, "P131")[:1]]
            # no "founded": Wikidata often gives the reserve-forest year, not the national-park year
        else:  # an organisation with a headquarters
            facts += [("hq", q) for q in _ids(claims, "P159")[:1]]
            y = _year(claims, "P571")
            if y:
                facts.append(("founded", y))
        if not facts:
            return []
        names = {l: v["value"] for l, v in e.get("labels", {}).items()}
        vals = _labels([v for _, v in facts if isinstance(v, str) and v.startswith("Q")])
        out = []
        for key, v in facts:
            en_val = v if not v.startswith("Q") else vals.get(v, {}).get("en", "")
            if key == "hq" and any(w in en_val for w in ("Building", "Bhawan", "Bhavan", "Secretariat",
                                                         "Headquarters", "Tower", "House", "Complex")):
                continue  # a building, not a city
            block = {}
            for l in LANG_CODES:
                x = names.get(l)
                val = v if not v.startswith("Q") else vals.get(v, {}).get(l)
                if x and val:
                    block[l] = T[key][l].format(x=x, v=val)
            if "en" in block:
                out.append(block)
        return out
    return []


def facts_for(entities: list) -> list:
    """entities: [{"name": "Securities and Exchange Board of India", "kind": "organisation"}, ...]"""
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    today = dt.date.today().isoformat()
    cutoff = (dt.date.today() - dt.timedelta(days=TTL_DAYS)).isoformat()
    out, changed = [], False
    for ent in entities[:4]:
        name, kind, short = ent.get("name", "").strip(), ent.get("kind", ""), ent.get("short", "").strip()
        indian = ent.get("indian")
        key = f"{kind}:{indian}:{name.lower()}"
        if not name:
            continue
        hit = cache.get(key)
        if not hit or hit["at"] < cutoff:
            try:
                hit = {"at": today, "facts": lookup(name, kind, indian) or (lookup(short, kind, indian) if short else [])}
            except Exception as exc:
                print(f"[gk] lookup failed for {name}: {exc}", file=sys.stderr)
                continue
            cache[key] = hit
            changed = True
        for f in hit["facts"]:
            if f not in out:
                out.append(f)
    if changed:
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return out[:6]


if __name__ == "__main__":
    tests = [("National Bank for Agriculture and Rural Development", "organisation"), ("Japan", "country"),
             ("Serbia", "country"), ("Assam", "state"), ("Securities and Exchange Board of India", "organisation"),
             ("SEBI", "organisation"), ("IRDAI", "organisation"),
             ("Kaziranga National Park", "place"), ("Reserve Bank of India", "organisation"), ("Georgia", "country")]
    for n, k in tests:
        print(n, f"({k}) ->")
        for f in lookup(n, k):
            print("   ", f["en"])
