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
EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"

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


def _openalex_auth() -> dict:
    key = os.getenv("OPENALEX_API_KEY", "").strip()
    if key:
        return {"api_key": key}
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    return {"mailto": mailto} if mailto else {}


def _openalex_fields(doi: str, timeout: int = 20) -> dict:
    url = f"{OPENALEX_BASE}/works/https://doi.org/{doi}"
    try:
        resp = requests.get(url, params=_openalex_auth(), timeout=timeout)
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


def _europepmc_fields(doi: str, timeout: int = 20) -> dict:
    """Europe PMC by DOI. It holds full abstracts for a lot of chemistry and
    life-science articles that Crossref/OpenAlex/S2 leave blank, so it is a
    valuable extra abstract source. Matched on DOI, so the join is exact."""
    try:
        resp = requests.get(
            f"{EPMC_BASE}/search",
            params={"query": f'DOI:"{doi}"', "format": "json", "resultType": "core", "pageSize": 1},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return {}
        res = ((resp.json() or {}).get("resultList") or {}).get("result") or []
    except Exception:
        return {}
    if not res:
        return {}
    r = res[0]
    out: dict = {}
    if r.get("title"):
        out["title"] = r["title"].strip().rstrip(".")
    if r.get("abstractText"):
        out["abstract"] = re.sub(r"<[^>]+>", "", r["abstractText"]).strip()
    if r.get("authorString"):
        out["authors"] = r["authorString"].strip().rstrip(".")
    if r.get("pubYear"):
        try:
            out["year"] = int(r["pubYear"])
        except (TypeError, ValueError):
            pass
    if r.get("journalInfo", {}).get("journal", {}).get("title"):
        out["venue"] = r["journalInfo"]["journal"]["title"]
    if r.get("citedByCount") is not None:
        out["citation_count"] = r["citedByCount"]
    return out


def recover_doi_by_title(title: str, *, timeout: int = 20, threshold: float = 0.95) -> str:
    """Find a DOI for a record that has none, by searching Crossref's
    bibliographic index for the title. Returns a DOI ONLY when the top hit's
    title is a near-exact match (>= `threshold`), so the worker never attaches
    a different paper's metadata to this record. Returns "" otherwise."""
    from difflib import SequenceMatcher

    from utils.dedup import normalize_title

    title = (title or "").strip()
    if len(title) < 15:
        return ""
    try:
        resp = requests.get(
            f"{CROSSREF_BASE}/works",
            params={"query.bibliographic": title[:200], "rows": 3},
            headers=_headers(),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return ""
        items = (resp.json() or {}).get("message", {}).get("items") or []
    except Exception:
        return ""
    want = normalize_title(title)
    for it in items:
        cand_title = (it.get("title") or [""])[0]
        doi = (it.get("DOI") or "").strip()
        if not cand_title or not doi:
            continue
        if SequenceMatcher(None, want, normalize_title(cand_title)).ratio() >= threshold:
            return doi
    return ""


# ---- Title-search fallback (fills journal/type/etc. when a DOI lookup can't) ----
# This is the part that closes most of the gap: even when the abstract is
# paywalled, a title search usually still returns the journal and type. To avoid
# attaching a *different* paper's data (the failure mode we observed in testing),
# every candidate must clear a strict gate before any field is taken from it.

# Field-specific acceptance: reject repository/aggregator names masquerading as a
# journal (e.g. "CINECA IRIS …", "Zenodo", "ResearchGate").
_BAD_VENUE_HINTS = (
    "repository", "institutional research", " iris ", "figshare", "researchgate",
    "(cern", "zenodo", "preprint server", "ssrn electronic", "osf.io", "datacite",
)


def _venue_ok(value: str) -> bool:
    v = (value or "").lower().strip()
    return bool(v) and not any(h in v for h in _BAD_VENUE_HINTS)


def _accept_field(field: str, value) -> bool:
    if field == "venue":
        return _venue_ok(str(value))
    return True


def _surnames(authors: str) -> set:
    out = set()
    for a in re.split(r"[,;]| and ", authors or ""):
        toks = [t for t in re.split(r"\s+", a.strip()) if t.isalpha()]
        if toks:
            out.add(toks[-1].lower())
    return out


def _candidate_matches(record: dict, cand: dict, *, threshold: float = 0.95) -> bool:
    """The safety gate: a title-search hit is only trusted when the title is a
    near-exact match AND (when both are known) the year is within 1 and at least
    one author surname overlaps. Prevents wrong-paper metadata contamination."""
    from difflib import SequenceMatcher

    from utils.dedup import normalize_title

    rt, ct = normalize_title(record.get("title")), normalize_title(cand.get("title"))
    if not rt or not ct or SequenceMatcher(None, rt, ct).ratio() < threshold:
        return False
    ry, cy = record.get("year"), cand.get("year")
    try:
        if ry and cy and abs(int(ry) - int(cy)) > 1:
            return False
    except (TypeError, ValueError):
        pass
    rs, cs = _surnames(record.get("authors") or ""), _surnames(cand.get("authors") or "")
    if rs and cs and not (rs & cs):
        return False
    return True


def _crossref_search(title: str, timeout: int = 20) -> list[dict]:
    try:
        resp = requests.get(
            f"{CROSSREF_BASE}/works",
            params={"query.bibliographic": title[:200], "rows": 3},
            headers=_headers(),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
        items = (resp.json() or {}).get("message", {}).get("items") or []
    except Exception:
        return []
    out = []
    for m in items:
        c: dict = {}
        titles = m.get("title") or []
        if titles:
            c["title"] = titles[0].strip()
        if m.get("DOI"):
            c["doi"] = m["DOI"]
        for key in ("published-print", "published-online", "issued", "created"):
            parts = (m.get(key) or {}).get("date-parts") or []
            if parts and parts[0]:
                c["year"] = parts[0][0]
                break
        names = [" ".join(filter(None, [a.get("given", ""), a.get("family", "")])).strip()
                 for a in (m.get("author") or [])[:8]]
        names = [n for n in names if n]
        if names:
            c["authors"] = ", ".join(names)
        cont = m.get("container-title") or []
        if cont:
            c["venue"] = cont[0]
        if m.get("abstract"):
            c["abstract"] = re.sub(r"<[^>]+>", "", m["abstract"]).strip()
        if m.get("type"):
            c["pub_type"] = m["type"]
        if m.get("is-referenced-by-count") is not None:
            c["citation_count"] = m["is-referenced-by-count"]
        out.append(c)
    return out


def _openalex_search(title: str, timeout: int = 20) -> list[dict]:
    params = {"search": title[:200], "per-page": 3}
    key = os.getenv("OPENALEX_API_KEY", "")
    if key:
        params["api_key"] = key
    try:
        resp = requests.get(f"{OPENALEX_BASE}/works", params=params, timeout=timeout)
        if resp.status_code != 200:
            return []
        results = (resp.json() or {}).get("results") or []
    except Exception:
        return []
    out = []
    for w in results:
        c: dict = {}
        if w.get("title"):
            c["title"] = w["title"]
        if w.get("doi"):
            c["doi"] = w["doi"]
        if w.get("publication_year"):
            c["year"] = w["publication_year"]
        auths = [a.get("author", {}).get("display_name", "") for a in (w.get("authorships") or [])[:8] if a.get("author")]
        auths = [a for a in auths if a]
        if auths:
            c["authors"] = ", ".join(auths)
        inv = w.get("abstract_inverted_index")
        if inv:
            pos: dict[int, str] = {}
            for word, idxs in inv.items():
                for p in idxs:
                    pos[p] = word
            if pos:
                c["abstract"] = " ".join(pos[i] for i in sorted(pos))
        src = (w.get("primary_location") or {}).get("source") or {}
        if src.get("display_name"):
            c["venue"] = src["display_name"]
        if w.get("type"):
            c["pub_type"] = w["type"]
        if w.get("cited_by_count") is not None:
            c["citation_count"] = w["cited_by_count"]
        out.append(c)
    return out


def _s2_search(title: str, timeout: int = 20) -> list[dict]:
    headers = {}
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if key:
        headers["x-api-key"] = key
    fields = "title,year,authors,abstract,venue,publicationTypes,citationCount,journal,externalIds"
    try:
        resp = requests.get(
            f"{S2_BASE}/paper/search/match",
            params={"query": title[:200], "fields": fields},
            headers=headers,
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
        items = (resp.json() or {}).get("data") or []
    except Exception:
        return []
    out = []
    for p in items:
        c: dict = {}
        if p.get("title"):
            c["title"] = p["title"]
        ids = p.get("externalIds") or {}
        if ids.get("DOI"):
            c["doi"] = ids["DOI"]
        if p.get("year"):
            c["year"] = p["year"]
        names = [a.get("name", "") for a in (p.get("authors") or [])[:8] if a.get("name")]
        if names:
            c["authors"] = ", ".join(names)
        if p.get("abstract"):
            c["abstract"] = p["abstract"]
        venue = ((p.get("journal") or {}).get("name") or p.get("venue") or "").strip()
        if venue:
            c["venue"] = venue
        pts = p.get("publicationTypes") or []
        if pts:
            c["pub_type"] = "Review" if "Review" in pts else pts[0]
        if p.get("citationCount") is not None:
            c["citation_count"] = p["citationCount"]
        out.append(c)
    return out


_TITLE_SOURCES = [
    ("Semantic Scholar (title)", _s2_search),
    ("OpenAlex (title)", _openalex_search),
    ("Crossref (title)", _crossref_search),
]


def _fill_from_title(record: dict, missing: list[str], *, sleep: float = 0.05) -> list[str]:
    """Fill the still-empty `missing` fields from a title search, taking values
    only from a candidate that clears `_candidate_matches`. Never fills `doi`
    (DOI recovery stays in the validated `recover_doi_by_title` path)."""
    title = (record.get("title") or "").strip()
    if len(title) < 15:
        return []
    filled: list[str] = []
    for _name, search in _TITLE_SOURCES:
        remaining = [f for f in missing if _empty(record.get(f))]
        if not remaining:
            break
        try:
            candidates = search(title)
        except Exception:
            candidates = []
        time.sleep(sleep)
        cand = next((c for c in candidates if _candidate_matches(record, c)), None)
        if not cand:
            continue
        for f in remaining:
            v = cand.get(f)
            if not _empty(v) and _accept_field(f, v):
                record[f] = v
                filled.append(f)
    return filled


_SOURCES = [
    ("Crossref", _crossref_fields),
    ("OpenAlex", _openalex_fields),
    ("Semantic Scholar", _s2_fields),
    ("Europe PMC", _europepmc_fields),
]


def fill_gaps(record: dict, *, sleep: float = 0.05) -> list[str]:
    """Fill the empty GAP_FIELDS of `record` from open sources. First recovers a
    DOI from the title if missing (strictly matched), runs the by-DOI cascade
    (Crossref -> OpenAlex -> Semantic Scholar -> Europe PMC), then a strictly-gated
    multi-source title search for anything still empty (which fills journal/type
    even when the abstract is paywalled). Mutates the record; returns the list of
    fields filled. Never raises."""
    filled: list[str] = []
    doi = (record.get("doi") or "").strip()
    if not doi:
        # No DOI on file — try to recover one from the title (strictly matched),
        # since the DOI is the join key every by-DOI source needs.
        recovered = recover_doi_by_title(record.get("title") or "")
        if recovered:
            record["doi"] = doi = recovered
            filled.append("doi")
    if doi:
        for _name, fetch in _SOURCES:
            missing = [f for f in GAP_FIELDS if _empty(record.get(f))]
            if not missing:
                break
            data = fetch(doi)
            time.sleep(sleep)
            if not data:
                continue
            for f in missing:
                if not _empty(data.get(f)) and _accept_field(f, data[f]):
                    record[f] = data[f]
                    filled.append(f)
    # Title-search fallback for whatever the DOI lookups left empty.
    missing = [f for f in GAP_FIELDS if _empty(record.get(f))]
    if missing:
        filled += _fill_from_title(record, missing, sleep=sleep)
    return filled
