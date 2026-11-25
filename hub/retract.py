"""Take a wrong item down from every app.

  python hub/retract.py <item-id-or-source-url>

The id is in each app's JSON ("id"); the source URL is shown on the item.
Commit and push afterwards (or run it from the GitHub "Retract item" workflow).
"""
import json
import sys

import export
from config import ITEMS

key = sys.argv[1].strip()
hits = 0
for f in ITEMS.glob("*.json"):
    items = json.loads(f.read_text(encoding="utf-8"))
    for i in items:
        if key in (i["id"], i["source_url"]) and not i.get("retracted"):
            i["retracted"] = True
            hits += 1
            print("retracted:", i["langs"]["en"]["title"])
    f.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
if not hits:
    sys.exit(f"No item matches {key!r}")
export.main()
