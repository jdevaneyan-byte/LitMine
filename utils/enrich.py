"""Enrich sparse imported records (typically DOI-only lists) with real
metadata from Crossref, so they are screenable instead of showing a
placeholder title like "DOI 10.xxxx/...".

Crossref is used because it is free, needs no key, covers all disciplines,
and is the registration agency for most DOIs. Records without a DOI, or
whose lookup fails, are returned unchanged.
"""

from __future__ import annotations

import os
import re
import time

import requests

CROSSREF_BASE = "https://api.crossref.org"
OPENALEX_BASE = "https://api.openalex.org"
S2_BASE = "https://api.semanticscholar.org/graph/v1"

# Fields the data-quality worker tries to complete, in the order the cascade
# fills them. The reliable join key across sources is the DOI.
GAP_FIELDS = ["title", "authors", "year", "abstract", "venue", "pub_type", "citation_count", "url"]


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


# Multi-source by-DOI fetchers — each returns a normalized field dict.

def _empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _crossref_fields(doi: str, timeout: int = 15) -> dict:
    try:
        resp = requests.get(f"{CROSSREF_BASE}/works/{doi}", headers=_headers(), timeout=timeout)
        if resp.status_code != 200:
            return {}
        m = (resp.json() or {}).get("message") or {}
    except Exception:
        return {}
    out: dict = {}
    titles = m.get("title") or []
    if titles:
        out["title"] = titles[0].strip()
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (m.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            out["year"] = parts[0][0]
            break
    names = []
    for a in (m.get("author") or [])[:8]:
        name = " ".join(filter(None, [a.get("given", ""), a.get("family", "")])).strip()
        if name:
            names.append(name)
    if names:
        out["authors"] = ", ".join(names)
    if m.get("abstract"):
        out["abstract"] = re.sub(r"<[^>]+>", "", m["abstract"]).strip()
    container = m.get("container-title") or []
    if container:
        out["venue"] = container[0]
    if m.get("type"):
        out["pub_type"] = m["type"]
    if m.get("is-referenced-by-count") is not None:
        out["citation_count"] = m["is-referenced-by-count"]
    out["url"] = f"https://doi.org/{doi}"
    return out


def _openalex_fields(doi: str, timeout: int = 20) -> dict:
    mailto = os.getenv("CROSSREF_MAILTO", "")
    url = f"{OPENALEX_BASE}/works/https://doi.org/{doi}"
    try:
        resp = requests.get(url, params={"mailto": mailto} if mailto else {}, timeout=timeout)
        if resp.status_code != 200:
            return {}
        w = resp.json() or {}
    except Exception:
        return {}
    out: dict = {}
    if w.get("title"):
        out["title"] = w["title"]
    if w.get("publication_year"):
        out["year"] = w["publication_year"]
    authors = [a.get("author", {}).get("display_name", "") for a in (w.get("authorships") or [])[:8] if a.get("author")]
    authors = [a for a in authors if a]
    if authors:
        out["authors"] = ", ".join(authors)
    inv = w.get("abstract_inverted_index")
    if inv:
        positions: dict[int, str] = {}
        for word, idxs in inv.items():
            for p in idxs:
                positions[p] = word
        if positions:
            out["abstract"] = " ".join(positions[i] for i in sorted(positions))
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    if src.get("display_name"):
        out["venue"] = src["display_name"]
    if w.get("type"):
        out["pub_type"] = w["type"]
    if w.get("cited_by_count") is not None:
        out["citation_count"] = w["cited_by_count"]
    if loc.get("landing_page_url"):
        out["url"] = loc["landing_page_url"]
    return out


def _s2_fields(doi: str, timeout: int = 20) -> dict:
    headers = {}
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if key:
        headers["x-api-key"] = key
    fields = "title,year,authors,abstract,venue,publicationTypes,citationCount,url"
    try:
        resp = requests.get(f"{S2_BASE}/paper/DOI:{doi}", params={"fields": fields}, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return {}
        p = resp.json() or {}
    except Exception:
        return {}
    out: dict = {}
    if p.get("title"):
        out["title"] = p["title"]
    if p.get("year"):
        out["year"] = p["year"]
    names = [a.get("name", "") for a in (p.get("authors") or [])[:8] if a.get("name")]
    if names:
        out["authors"] = ", ".join(names)
    if p.get("abstract"):
        out["abstract"] = p["abstract"]
    if p.get("venue"):
        out["venue"] = p["venue"]
    pts = p.get("publicationTypes") or []
    if pts:
        out["pub_type"] = "Review" if "Review" in pts else pts[0]
    if p.get("citationCount") is not None:
        out["citation_count"] = p["citationCount"]
    if p.get("url"):
        out["url"] = p["url"]
    return out


_SOURCES = [("Crossref", _crossref_fields), ("OpenAlex", _openalex_fields), ("Semantic Scholar", _s2_fields)]


def fill_gaps(record: dict, *, sleep: float = 0.05) -> list[str]:
    """Fill only the empty GAP_FIELDS of `record` by cascading across sources
    (Crossref -> OpenAlex -> Semantic Scholar). Requires a DOI. Mutates the
    record; returns the list of fields that got filled. Never raises."""
    doi = (record.get("doi") or "").strip()
    if not doi:
        return []
    filled: list[str] = []
    for _name, fetch in _SOURCES:
        missing = [f for f in GAP_FIELDS if _empty(record.get(f))]
        if not missing:
            break
        data = fetch(doi)
        time.sleep(sleep)
        if not data:
            continue
        for f in missing:
            if not _empty(data.get(f)):
                record[f] = data[f]
                filled.append(f)
    return filled
