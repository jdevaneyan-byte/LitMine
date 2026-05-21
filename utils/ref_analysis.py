"""Local (no-API) analysis of harvested references for a project.

Aggregates every reference across the project's papers, de-duplicates them
(by DOI, else normalized title), counts how many of the project's papers cite
each one, then cross-checks each against the current library and ALL other
projects:

  - already in this library            -> skip
  - collected in another project       -> auto-copied into this library
  - not collected anywhere ("missing") -> returned as gap candidates

This is pure computation over rows already in the database.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from database import CollectedArticle, Project, new_session


def _norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def _key(doi: str | None, title: str | None) -> str:
    d = (doi or "").replace("https://doi.org/", "").strip().lower()
    return f"doi:{d}" if d else f"t:{_norm_title(title)}"


def build_analysis(project_id: int) -> dict:
    session = new_session()
    try:
        # 1. Aggregate references from this project's harvested, non-deleted papers.
        papers = (
            session.query(CollectedArticle)
            .filter_by(project_id=project_id)
            .filter(CollectedArticle.references_extracted == True)  # noqa: E712
            .filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
            .all()
        )
        citers: dict[str, set[int]] = defaultdict(set)
        meta: dict[str, dict] = {}
        for p in papers:
            try:
                refs = json.loads(p.references_json or "[]")
            except Exception:
                refs = []
            for r in refs:
                if not (r.get("title") or r.get("doi")):
                    continue
                k = _key(r.get("doi"), r.get("title"))
                citers[k].add(p.id)
                meta.setdefault(k, r)

        # 2. Index every collected article across ALL projects (for cross-match).
        proj_names = {p.id: p.name for p in session.query(Project).all()}
        index: dict[str, tuple[int, int]] = {}  # key -> (project_id, article_id)
        for a in (
            session.query(
                CollectedArticle.id, CollectedArticle.project_id, CollectedArticle.doi, CollectedArticle.title
            )
            .filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
            .all()
        ):
            k = _key(a.doi, a.title)
            index.setdefault(k, (a.project_id, a.id))

        # 3. Classify; auto-copy cross-project matches into this library.
        missing: list[dict] = []
        copied = 0
        in_library = 0
        for k, cited_by in citers.items():
            hit = index.get(k)
            if hit and hit[0] == project_id:
                in_library += 1
                continue
            if hit and hit[0] != project_id:
                src = session.get(CollectedArticle, hit[1])
                if src is not None:
                    session.add(_clone_for_project(src, project_id))
                    copied += 1
                continue
            r = meta[k]
            missing.append({
                "key": k,
                "title": (r.get("title") or "").strip() or "(untitled)",
                "doi": (r.get("doi") or "").replace("https://doi.org/", "").strip().lower(),
                "year": r.get("year"),
                "venue": (r.get("venue") or "").strip(),
                "authors": (r.get("authors") or "").strip(),
                "cited_by": len(cited_by),
            })
        if copied:
            session.commit()

        missing.sort(key=lambda m: -m["cited_by"])
        return {
            "papers_analyzed": len(papers),
            "unique_references": len(citers),
            "in_library": in_library,
            "copied_from_other_projects": copied,
            "missing_count": len(missing),
            "missing": missing[:1000],
            "other_project_names": list({proj_names.get(pid, "") for pid, _ in index.values() if pid != project_id}),
        }
    finally:
        session.close()


def _clone_for_project(src: CollectedArticle, project_id: int) -> CollectedArticle:
    return CollectedArticle(
        project_id=project_id,
        title=src.title,
        doi=src.doi,
        abstract=src.abstract,
        authors=src.authors,
        year=src.year,
        source=src.source,
        url=src.url,
        pub_type=src.pub_type,
        category=src.category,
        venue=src.venue,
        citation_count=src.citation_count,
        screening_status="unscreened",
        origin="reference",
    )


def insert_references(project_id: int, items: list[dict]) -> int:
    """Add chosen missing references to the library as origin='reference'.
    Uses the metadata already present in the reference entry — no API call."""
    from utils.pub_category import categorize

    session = new_session()
    try:
        existing = {
            _key(a.doi, a.title)
            for a in session.query(CollectedArticle.doi, CollectedArticle.title)
            .filter_by(project_id=project_id)
            .all()
        }
        added = 0
        for r in items:
            k = _key(r.get("doi"), r.get("title"))
            if k in existing:
                continue
            doi = (r.get("doi") or "").replace("https://doi.org/", "").strip().lower()
            session.add(CollectedArticle(
                project_id=project_id,
                title=(r.get("title") or "").strip() or "(untitled)",
                doi=doi,
                authors=(r.get("authors") or "").strip(),
                year=r.get("year"),
                venue=(r.get("venue") or "").strip(),
                url=f"https://doi.org/{doi}" if doi else "",
                source="reference",
                category=categorize(None, "reference", r.get("title")),
                screening_status="unscreened",
                origin="reference",
            ))
            existing.add(k)
            added += 1
        session.commit()
        return added
    finally:
        session.close()
