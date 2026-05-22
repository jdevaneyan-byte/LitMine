"""Developer tool (run once, not by end users): build the shipped journal->field
lookup from OpenAlex's CC0 `sources` data.

Usage:
    OPENALEX_API_KEY=... python scripts/build_journal_fields.py --limit 25000 \
        --out data/journal_fields.json.gz

Fetches the top-N journals by works_count (coverage is heavily concentrated in the
top journals), derives each journal's dominant field + a multidisciplinary flag, and
writes a compact gzip JSON consumed by utils/field_classifier.py."""

from __future__ import annotations

import argparse
import gzip
import json
import os
from collections import Counter

import requests

from utils.field_classifier import normalize_issn, normalize_name

BASE_URL = "https://api.openalex.org/sources"
SELECT = "id,display_name,issn_l,issn,alternate_titles,abbreviated_title,works_count,topics"


def build_entry(source: dict, multi_threshold: float = 0.5):
    """Aggregate a source's topics into one dominant field + multidisciplinary flag.
    Returns {field, multi, issns, names} or None if there's no usable topic data."""
    counts: Counter = Counter()
    for t in source.get("topics") or []:
        field = (t.get("field") or {}).get("display_name")
        if field:
            counts[field] += int(t.get("count") or 0)
    total = sum(counts.values())
    if total == 0:
        return None
    field, top = counts.most_common(1)[0]
    multi = (top / total) < multi_threshold

    issns = []
    for v in [source.get("issn_l")] + list(source.get("issn") or []):
        n = normalize_issn(v)
        if n and n not in issns:
            issns.append(n)
    names = []
    raw_names = [source.get("display_name"), source.get("abbreviated_title")] + list(source.get("alternate_titles") or [])
    for v in raw_names:
        n = normalize_name(v)
        if n and n not in names:
            names.append(n)
    return {"field": field, "multi": multi, "issns": issns, "names": names}


def build_table(limit: int, multi_threshold: float = 0.5) -> dict:
    by_issn: dict = {}
    by_name: dict = {}
    key = os.getenv("OPENALEX_API_KEY", "").strip()
    auth = {"api_key": key} if key else {"mailto": "research@litmine.app"}
    cursor = "*"
    fetched = 0
    while fetched < limit and cursor:
        resp = requests.get(
            BASE_URL,
            params={"select": SELECT, "per-page": 200, "sort": "works_count:desc", "cursor": cursor, **auth},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            break
        for src in results:
            fetched += 1
            entry = build_entry(src, multi_threshold)
            if not entry:
                continue
            compact = {"f": entry["field"], "m": 1 if entry["multi"] else 0}
            for issn in entry["issns"]:
                by_issn.setdefault(issn, compact)
            for nm in entry["names"]:
                by_name.setdefault(nm, compact)
            if fetched >= limit:
                break
        cursor = data.get("meta", {}).get("next_cursor")
    return {"by_issn": by_issn, "by_name": by_name}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25000)
    ap.add_argument("--out", default="data/journal_fields.json.gz")
    ap.add_argument("--multi-threshold", type=float, default=0.5)
    args = ap.parse_args()
    table = build_table(args.limit, args.multi_threshold)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with gzip.open(args.out, "wt", encoding="utf-8") as f:
        json.dump(table, f, separators=(",", ":"))
    print(f"Wrote {args.out}: {len(table['by_issn'])} ISSNs, {len(table['by_name'])} names")


if __name__ == "__main__":
    main()
