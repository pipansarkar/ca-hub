"""Central settings for the CA hub. Edit here, not in the scripts."""
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "store"          # canonical data (all languages)
POOL = STORE / "pool.json"      # collected releases + processing status
ITEMS = STORE / "items"         # items/<YYYY-MM>.json
APPS = ROOT / "apps"            # per-app exports, read by the apps
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# ---- languages ------------------------------------------------------------
# Every item is written once in English (the "core"), then translated.
# Every language gets national news and news from every state.
LANGS = {
    "en": {"name": "English"},
    "bn": {"name": "Bengali", "script": r"[\u0980-\u09FF]",
           "style": "simple standard Bengali (চলিত ভাষা), as written in Bengali exam books. "
                    "Keep proper nouns recognisable; give the English name in brackets the first time "
                    "for schemes/organisations, e.g. প্রধানমন্ত্রী আবাস যোজনা (PMAY)."},
    "mr": {"name": "Marathi", "script": r"[\u0900-\u097F]",
           "style": "simple Marathi as used in MPSC / Police Bharti study material. Keep proper nouns "
                    "recognisable; give the English name in brackets the first time for schemes/organisations."},
}

# ---- regions ----------------------------------------------------------------
# "national" or one state / UT key. Display names per language are in export.py.
STATES = {
    "andhra_pradesh": "Andhra Pradesh", "arunachal_pradesh": "Arunachal Pradesh", "assam": "Assam",
    "bihar": "Bihar", "chhattisgarh": "Chhattisgarh", "goa": "Goa", "gujarat": "Gujarat",
    "haryana": "Haryana", "himachal_pradesh": "Himachal Pradesh", "jharkhand": "Jharkhand",
    "karnataka": "Karnataka", "kerala": "Kerala", "madhya_pradesh": "Madhya Pradesh",
    "maharashtra": "Maharashtra", "manipur": "Manipur", "meghalaya": "Meghalaya", "mizoram": "Mizoram",
    "nagaland": "Nagaland", "odisha": "Odisha", "punjab": "Punjab", "rajasthan": "Rajasthan",
    "sikkim": "Sikkim", "tamil_nadu": "Tamil Nadu", "telangana": "Telangana", "tripura": "Tripura",
    "uttar_pradesh": "Uttar Pradesh", "uttarakhand": "Uttarakhand", "west_bengal": "West Bengal",
    # Union territories
    "andaman_nicobar": "Andaman and Nicobar Islands", "chandigarh": "Chandigarh",
    "dadra_nagar_haveli_daman_diu": "Dadra and Nagar Haveli and Daman and Diu", "delhi": "Delhi",
    "jammu_kashmir": "Jammu and Kashmir", "ladakh": "Ladakh", "lakshadweep": "Lakshadweep",
    "puducherry": "Puducherry",
}
NORTH_EAST = {"arunachal_pradesh", "assam", "manipur", "meghalaya", "mizoram", "nagaland", "sikkim", "tripura"}
REGIONS = ["national", *STATES]

# Language-neutral category keys. Each app maps them to its own labels (export.py).
CATEGORIES = ["national", "international", "economy", "schemes", "appointments", "awards",
              "sports", "defence", "science", "environment"]

EXAM_TAGS = ["UPSC", "Bank", "SSC", "Railways", "State PSC", "WBCS", "TPSC", "MPSC", "Police Bharti"]

# ---- AI (free Gemini tier by default) --------------------------------------
# Tried in order on every call. Flash-Lite models are the ones that reliably answer free-tier
# requests; the bigger Flash models are often "503 high demand" for free users.
GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-3.6-flash"]
SECONDS_BETWEEN_CALLS = 7      # stay under free-tier requests/minute
MAX_PER_RUN = 20               # exam-relevant items processed per run (4 runs/day)
BATCH = 4                      # releases per AI call
MIN_BODY_CHARS = 150


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)
