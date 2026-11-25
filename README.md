# CA Hub: one data source for every current-affairs app

One pipeline collects official releases, writes exam notes once, translates them, checks them,
and auto-publishes each app's JSON. **Cost: ₹0** (GitHub Actions + raw GitHub hosting + Gemini free tier).

```
hourly         hub/collect.py   PIB "All Releases" pages of all 28 offices (Delhi + 27 state offices),
                                RBI, MahaSamvad -> store/pool.json                            (no AI)
6 AM, 12 PM,   hub/generate.py  1 shortlist call -> English core (facts + 2 MCQs) -> translate to bn / mr
6 PM, 10 PM IST                 -> automatic checks -> store/items/<YYYY-MM>.json
                                -> hub/export.py writes apps/<app>/ in each app's own format
```

| App | Reads | Gets |
|---|---|---|
| current_affairs_today | `apps/today/` | English + Bengali; categories + West Bengal, Tripura/NE, States (with state name) |
| current_affairs_in_bengali | `apps/bengali/` | Bengali; categories + west_bengal, tripura, north_east, states |
| current_affairs_marathi | `apps/marathi/` | Marathi; categories + महाराष्ट्र (own tab), इतर राज्ये |

Every app gets national news **and news from every state/UT**. Each item has a `region` (`national` or a
state key from `STATES` in `hub/config.py`). The AI picks the state, and if it can't, the PIB office's state is used.

Base URL: `https://raw.githubusercontent.com/pipansarkar/ca-hub/main/apps/<app>`

## Automatic checks (no human review)
Items are published only if they pass every check, per language:
- Correct shape: 2–5 points, exactly 2 MCQs, 4 distinct options, a valid answer.
- Written in the right script (Bengali or Devanagari).
- **Every number in the title, line, summary, points, question, correct answer and explanation appears
  in the official release.** Bengali and Marathi digits are converted before comparing.
- Static GK is dropped if it states a number the release doesn't contain.
- The answer key is set once in English and shared by all languages, and translators must keep option order.

A language that fails is skipped for that item only. The other languages still publish.

**Take down a wrong item from every app:** go to Actions → CA Hub → Run workflow, set task `retract`, and enter
the item id or source URL. Or run locally: `python hub/retract.py <id>`, then commit and push.

## Sources: official only
PIB allows free reuse with prominent credit, provided material is reproduced accurately and not used
in a misleading or derogatory way. Every item carries `source_name` and `source_url`, and the apps show them.
Never add newspapers or current-affairs sites. Add official state feeds (West Bengal, Tripura) to `FEEDS`
in `hub/collect.py`.

## Setup (once)
1. Create a **public** repo `pipansarkar/ca-hub` and push this folder to it.
2. Get a free key at https://aistudio.google.com/apikey and add it as the repo secret `GEMINI_API_KEY`.
   **Don't add billing** to that Google project. Without billing it can never charge you.
3. Run Actions → CA Hub → Run workflow with task `generate` once, then check `apps/*/`.

## Adding an app or a language
- New language (e.g. Hindi): add it to `LANGS` in `hub/config.py` with its script regex and style, and set its regions.
- New app: write an `export_<name>()` in `hub/export.py` and register it in `EXPORTERS`. Point the app at `apps/<name>/`.

## Limits
- Gemini free tier: about 16 calls a run (up to 20 items), about 64 a day. Lower `MAX_PER_RUN` if you hit limits. If the quota runs out, unprocessed releases wait for the next run.
- The repo grows by roughly 100–250 MB a year. Archive old `store/items` months when it gets big.
- The apps' old standalone pipelines were moved to `_legacy_pipeline/` in each app and no longer run.
- PIB's regional RSS feeds are empty, so the collector reads the HTML release lists. If PIB redesigns
  its site, fix `pib_list()` in `hub/collect.py`.
