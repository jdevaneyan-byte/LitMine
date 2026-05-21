"""Local, fast corpus analytics for the Analysis page.

Everything here is computed straight from the project's collected papers — no
API calls, no background job. It powers three panels:

  * Research landscape — top authors, top venues, publications per year.
  * Saturation / year trend — per-year counts + the cumulative growth curve.
  * Foundational core — which papers in YOUR library are cited the most by your
    OTHER library papers (internal citation influence, via `referenced_ids`).

Designed to return in well under a second even for tens of thousands of rows.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict


def _short(oa: str) -> str:
    return (oa or "").rsplit("/", 1)[-1]


def _aslist(raw: str) -> list[str]:
    try:
        v = json.loads(raw or "[]")
        return [_short(x) for x in v] if isinstance(v, list) else []
    except Exception:
        return []


def _authors(raw: str) -> list[str]:
    if not raw:
        return []
    return [a.strip() for a in raw.replace(";", ",").split(",") if a.strip()]


def build_insights(project_id: int, top_n: int = 15) -> dict:
    from database import CollectedArticle, init_db, new_session

    init_db()
    session = new_session()
    try:
        rows = (
            session.query(
                CollectedArticle.id,
                CollectedArticle.title,
                CollectedArticle.authors,
                CollectedArticle.year,
                CollectedArticle.venue,
                CollectedArticle.citation_count,
                CollectedArticle.openalex_id,
                CollectedArticle.referenced_ids,
                CollectedArticle.origin,
                CollectedArticle.screening_status,
            )
            .filter_by(project_id=project_id)
            .filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
            .all()
        )
    finally:
        session.close()

    total = len(rows)

    # ── Year trend + saturation ───────────────────────────────────────────
    year_counts: Counter[int] = Counter()
    for r in rows:
        if r.year:
            year_counts[int(r.year)] += 1
    years_sorted = sorted(year_counts)
    by_year = []
    running = 0
    for y in years_sorted:
        running += year_counts[y]
        by_year.append({"year": y, "count": year_counts[y], "cumulative": running})

    # ── Top authors / venues ──────────────────────────────────────────────
    author_counts: Counter[str] = Counter()
    venue_counts: Counter[str] = Counter()
    for r in rows:
        for a in _authors(r.authors or ""):
            author_counts[a] += 1
        if (r.venue or "").strip():
            venue_counts[r.venue.strip()] += 1
    top_authors = [{"name": n, "count": c} for n, c in author_counts.most_common(top_n)]
    top_venues = [{"name": n, "count": c} for n, c in venue_counts.most_common(top_n)]

    # ── Foundational core (internal citation influence) ───────────────────
    # Map each library paper's OpenAlex id to its row, then count how many of
    # the OTHER library papers reference it.
    by_oa: dict[str, dict] = {}
    for r in rows:
        if r.openalex_id:
            by_oa[_short(r.openalex_id)] = {
                "id": r.id,
                "title": r.title,
                "year": r.year,
                "venue": r.venue or "",
                "citation_count": r.citation_count,
            }
    internal: Counter[str] = Counter()
    papers_with_refs = 0
    for r in rows:
        refs = _aslist(r.referenced_ids or "")
        if refs:
            papers_with_refs += 1
        for cid in refs:
            if cid in by_oa:
                internal[cid] += 1
    foundational = []
    for cid, n in internal.most_common(top_n):
        meta = by_oa[cid]
        foundational.append({
            "id": meta["id"],
            "title": meta["title"],
            "year": meta["year"],
            "venue": meta["venue"],
            "internal_cited_by": n,
            "citation_count": meta["citation_count"],
        })

    # ── Composition / screening tallies (small extras for the header) ─────
    screening: Counter[str] = Counter()
    from_search = 0
    for r in rows:
        screening[(r.screening_status or "unscreened")] += 1
        if (r.origin or "search") == "search":
            from_search += 1

    return {
        "total": total,
        "from_search": from_search,
        "from_reference": total - from_search,
        "papers_with_refs": papers_with_refs,
        "year_min": years_sorted[0] if years_sorted else None,
        "year_max": years_sorted[-1] if years_sorted else None,
        "by_year": by_year,
        "top_authors": top_authors,
        "top_venues": top_venues,
        "foundational": foundational,
        "screening": dict(screening),
    }
