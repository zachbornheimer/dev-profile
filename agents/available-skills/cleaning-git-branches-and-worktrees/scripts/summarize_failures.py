#!/usr/bin/env python3
"""Group verify_adoption.py JSONL output by slug and error class."""

import collections
import json
import sys
from pathlib import Path

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/grok-adoption-integrity.jsonl"
by = collections.Counter()
rows = collections.defaultdict(list)
summary = None
strings = 0
for line in Path(path).read_text(errors="replace").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    if not isinstance(row, dict):
        strings += 1
        continue
    if "summary" in row:
        summary = row["summary"]
        continue
    if row.get("ok"):
        by[("OK", "")] += 1
        continue
    err = row.get("error", "?").split(":")[0]
    slug = row["backup"].split("/")[-2]
    by[(slug, err)] += 1
    rows[(slug, err)].append(row.get("backup"))
print("summary line:", summary, "| non-object lines:", strings)
for (slug, err), n in by.most_common():
    print(f"{n:4d}  {slug:45s} {err}")
if len(sys.argv) > 3:
    for b in rows.get((sys.argv[2], sys.argv[3]), [])[:5]:
        print(" e.g.", b)
