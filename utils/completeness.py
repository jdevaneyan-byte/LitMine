"""Data-quality audit: which metadata fields are missing on collected
articles, per record and summarized per project. Pairs with utils.enrich's
gap-filling worker."""

from __future__ import annotations

from database import CollectedArticle, new_session

# Fields a complete record should have. (citation_count/category are nice to
# have but excluded from "incomplete" so the audit focuses on core metadata.)
REQUIRED_FIELDS = ["title", "authors", "year", "doi", "abstract", "venue"]


def _empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def missing_fields(article) -> list[str]:
    out = []
    for f in REQUIRED_FIELDS:
        if _empty(getattr(article, f, None)):
            out.append(f)
    return out


def audit_project(project_id: int) -> dict:
    """Return per-field missing counts + how many records are complete /
    incomplete / fixable (have a DOI to look up)."""
    session = new_session()
    try:
        rows = (
            session.query(CollectedArticle)
            .filter_by(project_id=project_id)
            .filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
            .all()
        )
        total = len(rows)
        per_field = {f: 0 for f in REQUIRED_FIELDS}
        complete = 0
        fixable = 0  # incomplete but has a DOI we can look up
        no_doi_incomplete = 0
        for a in rows:
            miss = missing_fields(a)
            for f in miss:
                per_field[f] += 1
            if not miss:
                complete += 1
            else:
                if (a.doi or "").strip():
                    fixable += 1
                else:
                    no_doi_incomplete += 1
        return {
            "total": total,
            "complete": complete,
            "incomplete": total - complete,
            "fixable_with_doi": fixable,
            "incomplete_no_doi": no_doi_incomplete,
            "missing_by_field": per_field,
        }
    finally:
        session.close()
