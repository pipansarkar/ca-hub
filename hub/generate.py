"""Turn new pool releases into published items (all languages), then export.

1. shortlist: pick exam-relevant releases from titles (1 call)
2. core:      write English facts + 2 MCQs from the full release text (1 call / BATCH)
3. translate: rewrite each core into bn / mr (1 call / BATCH / language)
4. checks:    shape, script and "every number is in the source" per language
5. store + export to every app
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from typing import List

from pydantic import BaseModel, Field

import export
from ai import QuotaExhausted, ask
from checks import check_lang, safe_static_gk
from related_gk import facts_for
from config import (BATCH, CATEGORIES, EXAM_TAGS, ITEMS, LANGS, MAX_PER_RUN, MIN_BODY_CHARS,
                    POOL, REGIONS, STATES, now_ist)


# ---------------- schemas ----------------
class Shortlist(BaseModel):
    indices: List[int]


class Q(BaseModel):
    question: str
    options: List[str] = Field(description="exactly 4")
    answer: int = Field(description="0-based index of the correct option")
    explanation: str


class Entity(BaseModel):
    name: str = Field(description="full official English name, e.g. 'Securities and Exchange Board of India'")
    short: str = Field(description="common abbreviation if any, e.g. 'SEBI', else ''")
    kind: str = Field(description="country | state | organisation | place")
    indian: bool = Field(description="true if it is an Indian organisation/place")


class Core(BaseModel):
    n: int
    importance: int = Field(description="1-10: how likely this is to be asked in competitive exams")
    entities: List[Entity]
    category: str
    region: str
    tags: List[str]
    title: str
    one_liner: str
    summary: str
    points: List[str]
    static_gk: str
    mcqs: List[Q]


class Cores(BaseModel):
    items: List[Core]


class TQ(BaseModel):
    question: str
    options: List[str]
    explanation: str


class TItem(BaseModel):
    n: int
    title: str
    one_liner: str
    summary: str
    points: List[str]
    static_gk: str
    mcqs: List[TQ]


class TItems(BaseModel):
    items: List[TItem]


# ---------------- prompts ----------------
AUDIENCE = ("You prepare current affairs for Indian competitive-exam aspirants: UPSC, state PSCs "
            "(WBCS, TPSC, MPSC), Bank, SSC, Railways, Police Bharti.")

SHORTLIST_SYS = AUDIENCE + f"""
From the official releases listed, return the indices of those worth publishing (at most {MAX_PER_RUN}),
most important first. Keep: schemes and missions, appointments, awards, MoUs/agreements, summits,
reports and indices, defence exercises, economy/RBI data, science and space, sports results,
environment, important days, firsts, and notable state-level news from ANY state or UT (state schemes,
projects, state firsts, awards, GI tags, festivals of exam value). Aim for a mix of national and state news. Skip: greetings, condolences, photo posts, film screenings, routine meetings,
speeches without new facts, political criticism, crime, duplicates of the same event, and routine RBI
notices (weekly statistical supplement, money market operations, results or announcements of T-bill,
G-sec, SDL or VRR/VRRR auctions). Keep RBI policy decisions, new rules/directions, penalties on banks and
appointments."""

CORE_SYS = AUDIENCE + f"""
For each official release, write exam notes in English. The source may be Hindi, Marathi or English.
Accuracy rules (critical; notes are published automatically):
- Use only facts stated in the release. Copy names, dates, numbers, amounts and places exactly.
  Never invent, round or estimate a number. Write numbers in digits.
- Restate in your own concise words; do not copy sentences. Never exaggerate or editorialise.
Fields:
- category: one of {CATEGORIES}
  (polity = constitution, parliament, laws, courts, elections, governance; banking = RBI, banks,
  SEBI, insurance, payments; culture = art, heritage, festivals, GI tags; reports_indices = reports,
  rankings, surveys, indices; national = anything that fits nothing else)
- region: "national", or the key of the ONE state/UT the release is mainly about: {list(STATES)}.
  For state news, the title must name the state. An event merely held in a state (summits, visits,
  conferences) is "national" unless it is about that state's own affairs.
- tags: 1-4 of {EXAM_TAGS}
- title (max 12 words), one_liner (one exam-style sentence, max 25 words), summary (60-80 words),
  points (3-4 short facts: who/what/when/where/key number)
- static_gk: one related well-known static fact (e.g. HQ of an organisation) only if you are certain; else ""
- mcqs: exactly 2, each with exactly 4 distinct plausible options, answer = 0-based index of the correct
  option (vary its position), and a one-line explanation. Both must be answerable from the release.
- entities: up to 4 key named entities that exams attach static GK to: organisations (ministries,
  regulators, banks, UN bodies, companies), countries, Indian states/UTs, and places such as national
  parks or wetlands. Give the full official English name (e.g. "National Film Development Corporation
  of India"), the abbreviation, the kind (state = Indian state/UT only), and whether it is Indian. No people.
- importance: 1-10, how likely an examiner is to ask about this (10 = landmark: major scheme launch,
  summit, constitutional/legal change, top appointment, big award or index ranking; 1 = minor routine event).
- n: the release number you were given."""


def translate_sys(lang: str) -> str:
    L = LANGS[lang]
    return f"""Translate exam notes from English into {L['name']}.
Write {L['style']}
Rules: keep every fact, name, number and date exactly; write numbers in digits; translate every field;
keep the same number of points; keep the 4 options of each question in the SAME ORDER (the answer key
depends on it); do not add or drop anything. n must match the input."""


# ---------------- helpers ----------------
def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def lang_block(x) -> dict:
    return {"title": x.title.strip(), "one_liner": x.one_liner.strip(), "summary": x.summary.strip(),
            "points": [p.strip() for p in x.points if p.strip()], "static_gk": x.static_gk.strip(),
            "mcqs": [{"question": q.question.strip(), "options": [o.strip() for o in q.options],
                      "explanation": q.explanation.strip()} for q in x.mcqs]}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------- steps ----------------
def shortlist(cands: list) -> list:
    listing = [{"i": i, "source": c["source"], "title": c["title"], "start": c["body"][:250]}
               for i, c in enumerate(cands)]
    r = ask(SHORTLIST_SYS, json.dumps(listing, ensure_ascii=False), Shortlist, 2000)
    return list(dict.fromkeys(i for i in r.indices if 0 <= i < len(cands)))[:MAX_PER_RUN]


def make_items(batch: list, date: str, time: str) -> list:
    payload = [{"n": n, "source": c["source"], "title": c["title"], "text": c["body"]}
               for n, c in enumerate(batch)]
    cores = ask(CORE_SYS, json.dumps(payload, ensure_ascii=False), Cores).items
    items = {}
    for core in cores:
        if not 0 <= core.n < len(batch) or core.n in items:
            continue
        src = batch[core.n]
        source_text = src["title"] + "\n" + src["body"]
        answers = [q.answer for q in core.mcqs]
        en = lang_block(core)
        reason = check_lang(en, answers, source_text, None)
        if reason:
            log(f"  reject en ({reason}): {core.title[:70]}")
            src["status"] = "rejected"
            continue
        en["static_gk"] = safe_static_gk(en["static_gk"], source_text)
        # AI-detected state > the PIB office's state > national
        region = core.region if core.region in STATES else (src["region"] or "national")
        items[core.n] = {
            "id": hashlib.sha1(src["link"].encode()).hexdigest()[:12],
            "date": date, "time": time, "region": region,
            "category": core.category if core.category in CATEGORIES else "national",
            "tags": [t for t in core.tags if t in EXAM_TAGS],
            "source_name": src["source"], "source_url": src["link"],
            "answers": answers, "langs": {"en": en}, "_source": source_text,
            "entities": [e.model_dump() for e in core.entities][:4],
            "importance": max(1, min(10, core.importance)),
        }
        try:
            items[core.n]["gk"] = facts_for(items[core.n]["entities"])  # verified Wikidata facts
        except Exception as exc:
            log(f"  ! related GK failed: {exc}")
            items[core.n]["gk"] = []

    for lang, cfg in LANGS.items():
        if lang == "en":
            continue
        todo = items
        if not todo:
            continue
        payload = [{"n": n, **{k: v for k, v in it["langs"]["en"].items()}} for n, it in todo.items()]
        try:
            out = ask(translate_sys(lang), json.dumps(payload, ensure_ascii=False), TItems).items
        except QuotaExhausted:
            raise
        except Exception as exc:
            log(f"  ! {lang} translation failed: {exc}")
            continue
        for t in out:
            it = todo.get(t.n)
            if not it or lang in it["langs"]:
                continue
            block = lang_block(t)
            if len(block["mcqs"]) != 2:
                log(f"  reject {lang} (mcq count): {block['title'][:60]}")
                continue
            reason = check_lang(block, it["answers"], it["_source"], cfg["script"])
            if reason:
                log(f"  reject {lang} ({reason}): {block['title'][:60]}")
                continue
            block["static_gk"] = safe_static_gk(block["static_gk"], it["_source"])
            it["langs"][lang] = block
    for c in batch:
        if c["status"] == "new":
            c["status"] = "done"
    out = []
    for it in items.values():
        it.pop("_source")
        out.append(it)  # English passed; each app takes the items in its language
    return out


def main() -> None:
    pool = load(POOL, {})
    cands = [v for v in pool.values() if v["status"] == "new" and len(v["body"]) >= MIN_BODY_CHARS]
    for v in pool.values():
        if v["status"] == "new" and len(v["body"]) < MIN_BODY_CHARS:
            v["status"] = "skipped"
    log(f"[pool] {len(cands)} new releases")
    now = now_ist()
    date, time = now.date().isoformat(), now.isoformat(timespec="minutes")
    published = []
    try:
        if cands:
            chosen_idx = shortlist(cands[:150])
            chosen = [cands[i] for i in chosen_idx]
            for i, c in enumerate(cands[:150]):
                if i not in chosen_idx:
                    c["status"] = "skipped"
            log(f"[shortlist] {len(chosen)}")
            for k in range(0, len(chosen), BATCH):
                published += make_items(chosen[k:k + BATCH], date, time)
    except QuotaExhausted as exc:
        log(f"[quota] free quota used up; the rest waits for the next run ({exc})")
    except RuntimeError as exc:  # models busy (503) etc.: keep what's done, retry the rest next run
        log(f"[busy] AI unavailable, the rest waits for the next run ({str(exc)[:200]})")
    finally:
        save(POOL, pool)

    if published:
        by_month = defaultdict(list)
        for it in published:
            by_month[it["date"][:7]].append(it)
        for m, new in by_month.items():
            path = ITEMS / f"{m}.json"
            old = load(path, [])
            ids = {i["id"] for i in new}
            save(path, new + [i for i in old if i["id"] not in ids])
        for it in published:
            log(f"[+] {it['region']}/{it['category']} {sorted(it['langs'])}: {it['langs']['en']['title']}")
        export.main()
    log(f"[ok] published {len(published)} items")


if __name__ == "__main__":
    main()
