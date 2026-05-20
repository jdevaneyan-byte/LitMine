"""Backfill global citation counts for library rows that don't have one yet.

Uses OpenAlex, which lets us look up many DOIs in a single request
(filter=doi:a|b|c..., up to 50 per call). Polite-pool friendly.

Run from the project root:
    python -m backend.backfill_citations            # all projects
    python -m backend.backfill_citations 2          # only project id 2
"""

from __future__ import annotations

import os
import sys
import time

import requests

from database import CollectedArticle, init_db, new_session
from utils.pub_category import categorize

OPENALEX = "https://api.openalex.org/works"
BATCH = 50


def _norm(doi: str) -> str:
    d = (doi or "").strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d


def backfill(project_id: int | None = None) -> None:
    init_db()
    session = new_session()
    try:
        # Rows missing a citation count, a journal name, or a category.
        q = session.query(CollectedArticle).filter(
            (CollectedArticle.citation_count.is_(None))
            | (CollectedArticle.venue.is_(None))
            | (CollectedArticle.venue == "")
            | (CollectedArticle.category.is_(None))
            | (CollectedArticle.category == "")
        )
        if project_id is not None:
            q = q.filter_by(project_id=project_id)
        rows = [r for r in q.all() if r.doi]
    finally:
        session.close()

    print(f"{len(rows)} rows with a DOI need a citation count, journal and/or category.")
    if not rows:
        return

    mailto = os.getenv("CROSSREF_MAILTO", "")
    by_doi = {_norm(r.doi): r.id for r in rows if _norm(r.doi)}
    dois = list(by_doi.keys())
    updated = 0

    for i in range(0, len(dois), BATCH):
        chunk = dois[i : i + BATCH]
        filt = "doi:" + "|".join(chunk)
        params = {"filter": filt, "per-page": BATCH, "select": "doi,cited_by_count,primary_location,type"}
        if mailto:
            params["mailto"] = mailto
        try:
            resp = requests.get(OPENALEX, params=params, timeout=40)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as exc:
            print(f"  batch {i // BATCH + 1}: error {exc}")
            time.sleep(1.0)
            continue

        found = {}
        for w in results:
            wd = _norm((w.get("doi") or ""))
            if wd:
                source = (w.get("primary_location") or {}).get("source") or {}
                found[wd] = (w.get("cited_by_count", 0), source.get("display_name") or "", w.get("type") or "")

        sess = new_session()
        try:
            for d, (count, venue, oa_type) in found.items():
                rid = by_doi.get(d)
                if rid is not None:
                    art = sess.get(CollectedArticle, rid)
                    if art is not None:
                        if art.citation_count is None:
                            art.citation_count = count
                        if not art.venue and venue:
                            art.venue = venue
                        if not art.pub_type and oa_type:
                            art.pub_type = oa_type
                        if not art.category:
                            art.category = categorize(oa_type or art.pub_type, art.source, art.title)
                        updated += 1
            sess.commit()
        finally:
            sess.close()

        print(f"  batch {i // BATCH + 1}/{(len(dois) + BATCH - 1) // BATCH}: matched {len(found)} (total updated {updated})")
        time.sleep(0.2)

    print(f"Done. Updated {updated} rows.")


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    backfill(pid)
