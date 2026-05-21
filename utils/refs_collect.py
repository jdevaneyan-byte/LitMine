"""Collect a paper's references into the Library, with provenance.

Backs the references companion panel and its Collect / Collect-all buttons:

  * `annotate(article_id)` — the paper's fetched reference list, each entry
    tagged in_library / collectable / no_doi, plus headline counts.
  * `collect_one(article_id, doi)` — resolve one reference's full metadata
    (OpenAlex by DOI), add it to the Library (origin="reference") if new, and
    record a CitationLink from the paper to it.
  * `collect_all(article_id)` — the same for every collectable reference, in
    batched OpenAlex lookups.

A reference already in the Library is linked, never duplicated. References
without a DOI can't be resolved, so they're shown but not collectable.
"""

from __future__ import annotations

import json
import time

import requests

from api.openalex import BASE_URL, FIELDS, _auth_params, _parse_work


def _doi(d: str | None) -> str:
    return (d or "").replace("https://doi.org/", "").replace("http://doi.org/", "").strip().lower()


def _refs_of(article) -> list[dict]:
    try:
        v = json.loads(article.references_json or "[]")
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _batch(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _resolve_by_doi(dois: list[str]) -> dict[str, dict]:
    """DOI (lowercased, bare) -> parsed OpenAlex work. Batched 50/call."""
    out: dict[str, dict] = {}
    clean = [d for d in {_doi(x) for x in dois} if d]
    for chunk in _batch(clean, 50):
        try:
            r = requests.get(
                f"{BASE_URL}/works",
                params={"filter": f"doi:{'|'.join(chunk)}", "per-page": 50, "select": FIELDS, **_auth_params()},
                timeout=30,
            )
            if r.status_code != 200:
                continue
            for w in (r.json() or {}).get("results", []) or []:
                parsed = _parse_work(w)
                key = _doi(parsed.get("doi"))
                if key:
                    out[key] = parsed
        except Exception:
            continue
        time.sleep(0.1)
    return out


def _corpus_index(session, project_id: int):
    """Maps for this project's live papers: doi -> id, openalex_id -> id."""
    from database import CollectedArticle

    by_doi: dict[str, int] = {}
    by_oa: dict[str, int] = {}
    for a in (
        session.query(CollectedArticle.id, CollectedArticle.doi, CollectedArticle.openalex_id)
        .filter_by(project_id=project_id)
        .filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
        .all()
    ):
        if a.doi:
            by_doi.setdefault(_doi(a.doi), a.id)
        if a.openalex_id:
            by_oa.setdefault(a.openalex_id, a.id)
    return by_doi, by_oa


def annotate(article_id: int) -> dict:
    from database import CitationLink, CollectedArticle, new_session

    session = new_session()
    try:
        art = session.get(CollectedArticle, article_id)
        if art is None:
            return {"error": "article not found"}
        project_id = art.project_id
        refs = _refs_of(art)
        by_doi, _ = _corpus_index(session, project_id)
        linked = {
            cid for (cid,) in session.query(CitationLink.cited_id).filter_by(citing_id=article_id).all()
        }

        items = []
        in_library = collectable = no_doi = 0
        for r in refs:
            d = _doi(r.get("doi"))
            lib_id = by_doi.get(d) if d else None
            if lib_id is not None:
                status = "in_library"
                in_library += 1
            elif d:
                status = "collectable"
                collectable += 1
            else:
                status = "no_doi"
                no_doi += 1
            items.append({
                "title": (r.get("title") or "").strip() or "(untitled)",
                "doi": d,
                "year": r.get("year"),
                "authors": r.get("authors") or "",
                "venue": r.get("venue") or "",
                "status": status,
                "library_id": lib_id,
                "linked": lib_id in linked if lib_id is not None else False,
            })
        return {
            "article_id": article_id,
            "total": len(refs),
            "in_library": in_library,
            "collectable": collectable,
            "no_doi": no_doi,
            "added": len(linked),
            "references": items,
        }
    finally:
        session.close()


def _upsert_and_link(session, project_id: int, citing_id: int, parsed: dict, by_doi, by_oa) -> bool:
    """Add the resolved reference if new, then link citing -> it. Returns True if
    a NEW library row was created (vs linking an existing one)."""
    from database import CitationLink, CollectedArticle
    from utils.pub_category import categorize

    d = _doi(parsed.get("doi"))
    oa = parsed.get("openalex_id") or ""
    cited_id = (by_doi.get(d) if d else None) or (by_oa.get(oa) if oa else None)
    created = False
    if cited_id is None:
        row = CollectedArticle(
            project_id=project_id,
            title=parsed.get("title") or "(untitled)",
            doi=parsed.get("doi") or "",
            abstract=parsed.get("abstract") or "",
            authors=parsed.get("authors") or "",
            year=parsed.get("year"),
            source=parsed.get("source") or "OpenAlex",
            url=parsed.get("url") or "",
            pub_type=parsed.get("pub_type") or "",
            category=categorize(parsed.get("pub_type"), parsed.get("source"), parsed.get("title")),
            venue=parsed.get("venue") or "",
            citation_count=parsed.get("citation_count"),
            openalex_id=oa,
            referenced_ids=json.dumps(parsed.get("referenced_ids") or []),
            screening_status="unscreened",
            origin="reference",
        )
        session.add(row)
        session.flush()  # assign id
        cited_id = row.id
        if d:
            by_doi[d] = cited_id
        if oa:
            by_oa[oa] = cited_id
        created = True

    if cited_id != citing_id:
        exists = (
            session.query(CitationLink.id)
            .filter_by(citing_id=citing_id, cited_id=cited_id)
            .first()
        )
        if not exists:
            session.add(CitationLink(project_id=project_id, citing_id=citing_id, cited_id=cited_id))
    return created


def collect_one(article_id: int, doi: str) -> dict:
    from database import CollectedArticle, new_session

    target = _doi(doi)
    if not target:
        return {"added": 0, "linked": 0, "error": "reference has no DOI"}

    session = new_session()
    try:
        art = session.get(CollectedArticle, article_id)
        if art is None:
            return {"error": "article not found"}
        project_id = art.project_id
        by_doi, by_oa = _corpus_index(session, project_id)
    finally:
        session.close()

    meta = _resolve_by_doi([target])
    parsed = meta.get(target)
    if not parsed:
        return {"added": 0, "linked": 0, "error": "could not resolve this reference"}

    session = new_session()
    try:
        created = _upsert_and_link(session, project_id, article_id, parsed, by_doi, by_oa)
        session.commit()
        return {"added": 1 if created else 0, "linked": 1}
    except Exception as exc:
        session.rollback()
        return {"added": 0, "linked": 0, "error": str(exc)}
    finally:
        session.close()


def collect_all(article_id: int) -> dict:
    from database import CollectedArticle, new_session

    session = new_session()
    try:
        art = session.get(CollectedArticle, article_id)
        if art is None:
            return {"error": "article not found"}
        project_id = art.project_id
        refs = _refs_of(art)
        by_doi, by_oa = _corpus_index(session, project_id)
    finally:
        session.close()

    # Only the collectable ones: have a DOI and aren't already in the library.
    targets = sorted({_doi(r.get("doi")) for r in refs if _doi(r.get("doi")) and _doi(r.get("doi")) not in by_doi})
    if not targets:
        return {"added": 0, "linked": 0, "resolved": 0, "requested": 0}

    meta = _resolve_by_doi(targets)
    added = linked = 0
    session = new_session()
    try:
        for d in targets:
            parsed = meta.get(d)
            if not parsed:
                continue
            try:
                created = _upsert_and_link(session, project_id, article_id, parsed, by_doi, by_oa)
                added += 1 if created else 0
                linked += 1
            except Exception:
                session.rollback()
                continue
        session.commit()
    finally:
        session.close()
    return {"added": added, "linked": linked, "resolved": len(meta), "requested": len(targets)}
