"""Fetch the reference list of a paper given its DOI.

Tries Semantic Scholar first (rich metadata: title, year, authors, DOI,
publicationTypes). Falls back to Crossref if S2 has no record.

Returns a list of dicts with keys:
    title, doi, year, authors, venue, abstract, url,
    is_review, publication_types, source
"""

from __future__ import annotations

import os
import re
import time
from typing import Iterable

import requests

S2_BASE = "https://api.semanticscholar.org/graph/v1"
CROSSREF_BASE = "https://api.crossref.org"
OPENALEX_BASE = "https://api.openalex.org"

S2_REF_FIELDS = (
    "title,year,authors,externalIds,venue,abstract,publicationTypes,openAccessPdf,url"
)


class ReferenceFetchError(RuntimeError):
    pass


def _s2_headers() -> dict:
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    return {"x-api-key": key} if key else {}


def _crossref_headers() -> dict:
    mailto = os.getenv("CROSSREF_MAILTO", "")
    ua = "litmine/1.0"
    if mailto:
        ua += f" (mailto:{mailto})"
    return {"User-Agent": ua}


def fetch_references(doi: str) -> list[dict]:
    """Fetch the reference list for the paper at this DOI.

    Order: Semantic Scholar -> Crossref. The first source that returns a
    non-empty list wins. Raises ReferenceFetchError if no source has data."""

    doi = (doi or "").strip().lower()
    if not doi:
        raise ReferenceFetchError("missing DOI")

    errors = []
    # Free sources first (Semantic Scholar, Crossref), then OpenAlex as fallback.
    for name, fn in (("S2", _from_semantic_scholar), ("Crossref", _from_crossref), ("OpenAlex", _from_openalex)):
        try:
            refs = fn(doi)
            if refs:
                return refs
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    if errors:
        raise ReferenceFetchError(" | ".join(errors))
    return []


# Semantic Scholar

def _from_semantic_scholar(doi: str) -> list[dict]:
    """One-shot graph endpoint: /paper/DOI:{doi}/references with paging."""

    url = f"{S2_BASE}/paper/DOI:{doi}/references"
    out: list[dict] = []
    offset = 0
    limit = 100
    while True:
        params = {"fields": S2_REF_FIELDS, "limit": limit, "offset": offset}
        resp = requests.get(url, params=params, headers=_s2_headers(), timeout=30)
        if resp.status_code == 404:
            return []
        if resp.status_code == 429:
            time.sleep(3)
            continue
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("data", []) or []
        for item in items:
            cited = (item or {}).get("citedPaper") or {}
            parsed = _parse_s2_paper(cited)
            if parsed["title"]:
                out.append(parsed)
        if not payload.get("next"):
            break
        offset = payload.get("next") or (offset + limit)
        time.sleep(0.5)
    return out


def _parse_s2_paper(p: dict) -> dict:
    ext = p.get("externalIds") or {}
    doi = (ext.get("DOI") or "").strip().lower()
    pub_types = p.get("publicationTypes") or []
    is_review = _looks_like_review(p.get("title") or "", pub_types)
    is_book = _looks_like_book(pub_types)
    authors = ", ".join(_take_author_names(p.get("authors") or [])) or ""
    return {
        "title": (p.get("title") or "").strip(),
        "doi": doi,
        "year": _safe_int(p.get("year")),
        "authors": authors,
        "venue": (p.get("venue") or "").strip(),
        "abstract": (p.get("abstract") or "").strip(),
        "url": (p.get("url") or (f"https://doi.org/{doi}" if doi else "")),
        "is_review": is_review,
        "is_book": is_book,
        "publication_types": ", ".join(pub_types) if pub_types else "",
        "source": "Semantic Scholar",
    }


def _take_author_names(authors: Iterable[dict], limit: int = 8) -> list[str]:
    names = []
    for a in authors:
        name = (a or {}).get("name", "")
        if name:
            names.append(name)
        if len(names) >= limit:
            break
    return names


# OpenAlex (fallback): a paper's referenced_works are clean OA IDs; resolve them
# to titles in batches of 50 (one call each). The DOI lookup itself is OpenAlex's
# free "singleton" tier.

def _openalex_auth() -> dict:
    key = os.getenv("OPENALEX_API_KEY", "").strip()
    return {"api_key": key} if key else {}


def _from_openalex(doi: str) -> list[dict]:
    try:
        resp = requests.get(
            f"{OPENALEX_BASE}/works/https://doi.org/{doi}",
            params={"select": "referenced_works", **_openalex_auth()},
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        ref_ids = (resp.json() or {}).get("referenced_works") or []
    except Exception:
        return []
    if not ref_ids:
        return []

    out: list[dict] = []
    sel = "id,doi,title,publication_year,authorships,primary_location,type"
    for i in range(0, min(len(ref_ids), 600), 50):
        batch = ref_ids[i : i + 50]
        ids = "|".join(b.rsplit("/", 1)[-1] for b in batch)
        try:
            r = requests.get(
                f"{OPENALEX_BASE}/works",
                params={"filter": f"openalex_id:{ids}", "per-page": 50, "select": sel, **_openalex_auth()},
                timeout=30,
            )
            if r.status_code != 200:
                continue
            for w in (r.json() or {}).get("results", []) or []:
                out.append(_parse_openalex_work(w))
        except Exception:
            continue
        time.sleep(0.1)
    return [o for o in out if o["title"] or o["doi"]]


def _parse_openalex_work(w: dict) -> dict:
    doi = (w.get("doi") or "").replace("https://doi.org/", "").strip().lower()
    authors = [a.get("author", {}).get("display_name", "") for a in (w.get("authorships") or [])[:8] if a.get("author")]
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    ptype = (w.get("type") or "").lower()
    return {
        "title": (w.get("title") or "").strip(),
        "doi": doi,
        "year": _safe_int(w.get("publication_year")),
        "authors": ", ".join(a for a in authors if a),
        "venue": (src.get("display_name") or "").strip(),
        "abstract": "",
        "url": (loc.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else "")),
        "is_review": ptype == "review",
        "is_book": "book" in ptype,
        "publication_types": ptype,
        "source": "OpenAlex",
    }


# Crossref

def _from_crossref(doi: str) -> list[dict]:
    url = f"{CROSSREF_BASE}/works/{doi}"
    resp = requests.get(url, headers=_crossref_headers(), timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    msg = (resp.json() or {}).get("message") or {}
    refs = msg.get("reference") or []
    out: list[dict] = []
    for ref in refs:
        out.append(_parse_crossref_ref(ref))
    # Crossref refs are very sparse; for entries with a DOI we can enrich them
    # in a single batch query. Cheap call: /works?filter=doi:a,doi:b,... but
    # that has practical limits, so we only enrich ones missing year+title.
    out = _enrich_crossref_refs(out)
    return [o for o in out if o["title"] or o["doi"]]


def _parse_crossref_ref(ref: dict) -> dict:
    doi = (ref.get("DOI") or "").strip().lower()
    title = (
        ref.get("article-title")
        or ref.get("series-title")
        or ref.get("volume-title")
        or ref.get("unstructured")
        or ""
    ).strip()
    year = _safe_int(ref.get("year"))
    authors = (ref.get("author") or "").strip()
    venue = (ref.get("journal-title") or "").strip()
    # Crossref references that carry only a volume/series title (no
    # article-title) are usually book or book-series entries.
    is_book = bool(
        (ref.get("volume-title") or ref.get("series-title"))
        and not ref.get("article-title")
    )
    return {
        "title": title,
        "doi": doi,
        "year": year,
        "authors": authors,
        "venue": venue,
        "abstract": "",
        "url": f"https://doi.org/{doi}" if doi else "",
        "is_review": _looks_like_review(title, []),
        "is_book": is_book,
        "publication_types": "",
        "source": "Crossref",
    }


# Max per-review Crossref enrichment lookups. A typical review cites
# 30-150 papers; 250 covers almost all without unbounded runtime. Refs
# beyond this keep whatever sparse metadata Crossref returned inline.
CROSSREF_ENRICH_CAP = 250


def _enrich_one_crossref_ref(r: dict) -> None:
    """Fill one sparse reference (DOI only) with title/year/venue/authors."""
    try:
        resp = requests.get(
            f"{CROSSREF_BASE}/works/{r['doi']}",
            headers=_crossref_headers(),
            timeout=15,
        )
        if resp.status_code != 200:
            return
        m = (resp.json() or {}).get("message") or {}
    except Exception:
        return
    if not r["title"]:
        t = m.get("title") or []
        r["title"] = (t[0] if t else "").strip()
    if not r["year"]:
        issued = (m.get("issued") or {}).get("date-parts") or []
        if issued and issued[0]:
            r["year"] = _safe_int(issued[0][0])
    if not r["venue"]:
        container = m.get("container-title") or []
        r["venue"] = (container[0] if container else "").strip()
    if not r["authors"]:
        names = []
        for a in (m.get("author") or [])[:8]:
            name = " ".join(filter(None, [a.get("given", ""), a.get("family", "")])).strip()
            if name:
                names.append(name)
        r["authors"] = ", ".join(names)
    ctype = (m.get("type") or "").lower()
    if ctype:
        r["publication_types"] = ctype
    if "review" in ctype:
        r["is_review"] = True
    if "book" in ctype or "monograph" in ctype:
        r["is_book"] = True


def _enrich_crossref_refs(refs: list[dict]) -> list[dict]:
    """For refs that have a DOI but no year/title, look them up in parallel.

    Bounded by CROSSREF_ENRICH_CAP. Parallelized (8 workers) so a 60-reference
    list resolves in ~3s instead of ~25s of sequential lookups."""
    from concurrent.futures import ThreadPoolExecutor

    needs = [r for r in refs if r["doi"] and (not r["title"] or not r["year"])][:CROSSREF_ENRICH_CAP]
    if needs:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(_enrich_one_crossref_ref, needs))
    return refs


# Helpers

_REVIEW_TITLE_PATTERNS = re.compile(
    r"\b(review|advances?|perspective|overview|survey|state[- ]of[- ]the[- ]art|recent (advances|developments|progress)|tutorial|primer)\b",
    re.IGNORECASE,
)


def _looks_like_review(title: str, publication_types: Iterable[str]) -> bool:
    for pt in publication_types or []:
        if pt and pt.strip().lower() in {"review", "metaanalysis", "meta-analysis"}:
            return True
    if title and _REVIEW_TITLE_PATTERNS.search(title):
        return True
    return False


def _looks_like_book(publication_types: Iterable[str]) -> bool:
    for pt in publication_types or []:
        if pt and pt.strip().lower() in {"book", "booksection", "book-chapter", "monograph"}:
            return True
    return False


def _safe_int(value) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (ValueError, TypeError):
        return None
