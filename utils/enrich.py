"""Enrich sparse imported records (typically DOI-only lists) with real
metadata from Crossref, so they are screenable instead of showing a
placeholder title like "DOI 10.xxxx/...".

Crossref is used because it is free, needs no key, covers all disciplines,
and is the registration agency for most DOIs. Records without a DOI, or
whose lookup fails, are returned unchanged.
"""

from __future__ import annotations

import os
import time

import requests

CROSSREF_BASE = "https://api.crossref.org"


def _headers() -> dict:
    mailto = os.getenv("CROSSREF_MAILTO", "")
    ua = "litmine/1.0"
    if mailto:
        ua += f" (mailto:{mailto})"
    return {"User-Agent": ua}


def _is_placeholder(record: dict) -> bool:
    title = (record.get("title") or "").strip()
    return (not title) or title.lower().startswith("doi ")


def needs_enrichment(record: dict) -> bool:
    """A record is worth enriching if it has a DOI but a placeholder/empty
    title or is missing year or authors."""
    if not (record.get("doi") or "").strip():
        return False
    return _is_placeholder(record) or not record.get("year") or not record.get("authors")


def enrich_record(record: dict, *, timeout: int = 15) -> dict:
    """Fill missing title/authors/year/abstract/url for one record via
    Crossref. Mutates and returns the record. Never raises."""
    doi = (record.get("doi") or "").strip()
    if not doi:
        return record
    try:
        resp = requests.get(f"{CROSSREF_BASE}/works/{doi}", headers=_headers(), timeout=timeout)
        if resp.status_code != 200:
            return record
        msg = (resp.json() or {}).get("message") or {}
    except Exception:
        return record

    if _is_placeholder(record):
        titles = msg.get("title") or []
        if titles:
            record["title"] = titles[0].strip()

    if not record.get("year"):
        for key in ("published-print", "published-online", "issued", "created"):
            parts = (msg.get(key) or {}).get("date-parts") or []
            if parts and parts[0]:
                record["year"] = parts[0][0]
                break

    if not record.get("authors"):
        names = []
        for a in (msg.get("author") or [])[:8]:
            name = " ".join(filter(None, [a.get("given", ""), a.get("family", "")])).strip()
            if name:
                names.append(name)
        if names:
            record["authors"] = ", ".join(names)

    if not record.get("abstract") and msg.get("abstract"):
        # Crossref abstracts are JATS XML; strip tags for a plain-text version.
        import re

        record["abstract"] = re.sub(r"<[^>]+>", "", msg["abstract"]).strip()

    if not record.get("url"):
        record["url"] = f"https://doi.org/{doi}"

    if not record.get("pub_type"):
        ctype = (msg.get("type") or "").strip()
        if ctype:
            record["pub_type"] = ctype

    return record


def enrich_records(records: list[dict], *, cap: int = 300, sleep: float = 0.05, progress=None) -> int:
    """Enrich up to `cap` records in place. Returns the number enriched.

    `progress` is an optional callable(done, total) for UI feedback."""
    targets = [r for r in records if needs_enrichment(r)][:cap]
    total = len(targets)
    for i, rec in enumerate(targets, 1):
        enrich_record(rec)
        if progress:
            progress(i, total)
        time.sleep(sleep)
    return total
