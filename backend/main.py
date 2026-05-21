"""FastAPI backend for the LitMine React frontend.

Serves the existing SQLite data (projects, library articles, curated reviews,
cited articles) and the project network graphs as JSON. Reuses the same
`database`, `api/` and `utils/` modules as the Streamlit app, so both
frontends read and write the one local database.

Run locally:
    uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.network import build_network
from database import (
    CitedArticle,
    CollectedArticle,
    CuratedReview,
    Project,
    init_db,
    new_session,
)

app = FastAPI(title="LitMine API", version="0.2.0")

# Local-first: the Next.js dev server (3000) and prod build talk to this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

UNSCREENED = (None, "", "unscreened", "identified")


# Schemas

class ArticleEdit(BaseModel):
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    abstract: Optional[str] = None
    pub_type: Optional[str] = None
    screening_status: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    decision_reason: Optional[str] = None


class ProjectCreate(BaseModel):
    name: str
    topic: str
    type: str = "both"  # review | research | both
    description: str = ""


class SearchRequest(BaseModel):
    queries: list[str]
    type: str = "both"  # review | research | both
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    sources: list[str] = ["openalex", "pubmed", "s2", "arxiv"]
    max_per_source: int = 100
    title_keyword: str = ""   # comma/newline-separated; empty = no filter
    match_mode: str = "any"   # any | all


# review/research/both maps to the search engine's mode + the stored label.
_TYPE_TO_MODE = {"review": "reviews", "research": "articles", "both": "both"}
_TYPE_TO_LABEL = {
    "review": "Review articles",
    "research": "Research articles",
    "both": "Review + research articles",
}


def _article_dict(a: CollectedArticle) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "authors": a.authors,
        "year": a.year,
        "doi": a.doi,
        "url": a.url,
        "abstract": a.abstract,
        "source": a.source,
        "pub_type": a.pub_type,
        "category": a.category or "Unclassified",
        "venue": a.venue or "",
        "citation_count": a.citation_count,
        "screening_status": a.screening_status or "unscreened",
        "tags": a.tags or "",
        "notes": a.notes or "",
        "decision_reason": a.decision_reason or "",
        "is_deleted": bool(a.is_deleted),
        "abstract_unavailable": bool(a.abstract_unavailable),
        "origin": a.origin or "search",
        "references_extracted": bool(a.references_extracted),
        "references_count": a.references_count or 0,
        "edited_by_user": bool((a.notes or "").startswith("[edited]") or (a.imported_from == "manual-edit")),
    }


# Projects

@app.get("/api/projects")
def list_projects():
    session = new_session()
    try:
        out = []
        for p in session.query(Project).order_by(Project.created_at.desc()).all():
            out.append({
                "id": p.id,
                "name": p.name,
                "topic": p.topic,
                "literature_type": p.literature_type or "Review + research articles",
                "description": p.description or "",
                "library": session.query(CollectedArticle).filter_by(project_id=p.id).count(),
                "curated_reviews": session.query(CuratedReview).filter_by(project_id=p.id).count(),
                "cited": session.query(CitedArticle).filter_by(project_id=p.id).count(),
            })
        return out
    finally:
        session.close()


@app.post("/api/projects")
def create_project(body: ProjectCreate):
    name = body.name.strip()
    topic = body.topic.strip()
    if not name or not topic:
        raise HTTPException(400, "name and topic are required")
    session = new_session()
    try:
        p = Project(
            name=name,
            topic=topic,
            literature_type=_TYPE_TO_LABEL.get(body.type, _TYPE_TO_LABEL["both"]),
            description=body.description.strip(),
            stage=3,  # ready to collect
        )
        session.add(p)
        session.commit()
        return {"id": p.id, "name": p.name, "topic": p.topic, "literature_type": p.literature_type}
    finally:
        session.close()


@app.get("/api/projects/{project_id}")
def get_project(project_id: int):
    session = new_session()
    try:
        p = session.get(Project, project_id)
        if not p:
            raise HTTPException(404, "project not found")
        return {
            "id": p.id,
            "name": p.name,
            "topic": p.topic,
            "literature_type": p.literature_type or "Review + research articles",
            "description": p.description or "",
        }
    finally:
        session.close()


# Library articles

@app.get("/api/projects/{project_id}/articles")
def list_articles(
    project_id: int,
    q: str = "",
    decision: str = "all",
    year_min: int = 0,
    year_max: int = 0,
    pub_type: str = "all",
    category: str = "all",
    journal: str = "",
    origin: str = "all",  # all | search | reference
    view: str = "active",  # "active" (default) hides trash; "trash" shows only deleted
    sort: str = "year",
    limit: int = Query(100, le=2000),
    offset: int = 0,
):
    session = new_session()
    try:
        query = session.query(CollectedArticle).filter_by(project_id=project_id)
        if view == "trash":
            query = query.filter(CollectedArticle.is_deleted == True)  # noqa: E712
        else:
            query = query.filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
        if q.strip():
            query = query.filter(CollectedArticle.title.ilike(f"%{q.strip()}%"))
        if journal.strip():
            query = query.filter(CollectedArticle.venue.ilike(f"%{journal.strip()}%"))
        if origin == "search":
            query = query.filter((CollectedArticle.origin == "search") | (CollectedArticle.origin == None))  # noqa: E711
        elif origin == "reference":
            query = query.filter(CollectedArticle.origin == "reference")
        if decision == "unscreened":
            query = query.filter(CollectedArticle.screening_status.in_([v for v in UNSCREENED if v is not None]))
        elif decision != "all":
            query = query.filter(CollectedArticle.screening_status == decision)
        if year_min:
            query = query.filter(CollectedArticle.year != None).filter(CollectedArticle.year >= year_min)  # noqa: E711
        if year_max:
            query = query.filter(CollectedArticle.year != None).filter(CollectedArticle.year <= year_max)  # noqa: E711
        if pub_type != "all":
            query = query.filter(CollectedArticle.pub_type == pub_type)
        if category != "all":
            if category == "Unclassified":
                query = query.filter((CollectedArticle.category == "") | (CollectedArticle.category == None) | (CollectedArticle.category == "Unclassified"))  # noqa: E711
            else:
                query = query.filter(CollectedArticle.category == category)
        if sort == "citations":
            ordered = query.order_by(CollectedArticle.citation_count.desc().nullslast(), CollectedArticle.id.desc())
        else:
            ordered = query.order_by(CollectedArticle.year.desc().nullslast(), CollectedArticle.id.desc())
        total = ordered.count()
        rows = ordered.offset(offset).limit(limit).all()
        return {"total": total, "items": [_article_dict(a) for a in rows]}
    finally:
        session.close()


@app.get("/api/articles/{article_id}")
def get_article(article_id: int, with_references: bool = False):
    session = new_session()
    try:
        a = session.get(CollectedArticle, article_id)
        if not a:
            raise HTTPException(404, "article not found")
        data = _article_dict(a)
        stored = a.references_json
    finally:
        session.close()

    if with_references:
        # Prefer already-extracted (persisted) references; never re-fetch.
        if stored:
            try:
                data["references"] = json.loads(stored)
            except Exception:
                data["references"] = []
        else:
            data["references"] = []
    return data


@app.post("/api/articles/{article_id}/extract")
def extract_references(article_id: int):
    """Fetch this article's reference list once and persist it, so the article
    becomes a mined 'seed' (works for any article, not just curated reviews)."""
    session = new_session()
    try:
        a = session.get(CollectedArticle, article_id)
        if not a:
            raise HTTPException(404, "article not found")
        doi = (a.doi or "").strip()
    finally:
        session.close()

    if not doi:
        raise HTTPException(400, "this article has no DOI to extract references from")

    from api.references import fetch_references, ReferenceFetchError

    try:
        refs = fetch_references(doi)
    except ReferenceFetchError as exc:
        raise HTTPException(502, f"could not fetch references: {exc}")

    session = new_session()
    try:
        a = session.get(CollectedArticle, article_id)
        a.references_json = json.dumps(refs)
        a.references_extracted = True
        a.references_count = len(refs)
        session.commit()
        return {"ok": True, "count": len(refs), "references": refs}
    finally:
        session.close()


@app.patch("/api/articles/{article_id}")
def edit_article(article_id: int, edit: ArticleEdit):
    """Manual edit. Any change marks the row as user-edited (audited)."""
    session = new_session()
    try:
        a = session.get(CollectedArticle, article_id)
        if not a:
            raise HTTPException(404, "article not found")
        changed = []
        for field, value in edit.model_dump(exclude_none=True).items():
            if getattr(a, field, None) != value:
                setattr(a, field, value)
                changed.append(field)
        if changed:
            note = a.notes or ""
            if not note.startswith("[edited]"):
                a.notes = f"[edited] {note}".strip()
            a.imported_from = "manual-edit"
            session.commit()
        return {"ok": True, "changed": changed, "article": _article_dict(a)}
    finally:
        session.close()


# Trash (soft delete) — distinct from the "exclude" screening decision

@app.post("/api/articles/{article_id}/trash")
def trash_article(article_id: int):
    session = new_session()
    try:
        a = session.get(CollectedArticle, article_id)
        if not a:
            raise HTTPException(404, "article not found")
        a.is_deleted = True
        a.deleted_at = datetime.now(timezone.utc)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.post("/api/articles/{article_id}/restore")
def restore_article(article_id: int):
    session = new_session()
    try:
        a = session.get(CollectedArticle, article_id)
        if not a:
            raise HTTPException(404, "article not found")
        a.is_deleted = False
        a.deleted_at = None
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.delete("/api/articles/{article_id}")
def delete_article_permanently(article_id: int):
    """Permanent delete — only allowed for items already in the trash."""
    session = new_session()
    try:
        a = session.get(CollectedArticle, article_id)
        if not a:
            raise HTTPException(404, "article not found")
        if not a.is_deleted:
            raise HTTPException(400, "move the article to trash before deleting permanently")
        session.delete(a)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.post("/api/projects/{project_id}/trash/empty")
def empty_trash(project_id: int):
    session = new_session()
    try:
        n = (
            session.query(CollectedArticle)
            .filter_by(project_id=project_id, is_deleted=True)
            .delete(synchronize_session=False)
        )
        session.commit()
        return {"ok": True, "deleted": n}
    finally:
        session.close()


# Bulk actions (keyboard-driven multi-select in the Library)

class BulkDecision(BaseModel):
    ids: list[int]
    status: str  # unscreened | include | maybe | exclude


class BulkIds(BaseModel):
    ids: list[int]


@app.post("/api/projects/{project_id}/bulk-decision")
def bulk_decision(project_id: int, body: BulkDecision):
    if not body.ids:
        return {"ok": True, "updated": 0}
    session = new_session()
    try:
        n = (
            session.query(CollectedArticle)
            .filter(CollectedArticle.project_id == project_id, CollectedArticle.id.in_(body.ids))
            .update({CollectedArticle.screening_status: body.status}, synchronize_session=False)
        )
        session.commit()
        return {"ok": True, "updated": n}
    finally:
        session.close()


@app.post("/api/projects/{project_id}/bulk-trash")
def bulk_trash(project_id: int, body: BulkIds):
    if not body.ids:
        return {"ok": True, "updated": 0}
    session = new_session()
    try:
        n = (
            session.query(CollectedArticle)
            .filter(CollectedArticle.project_id == project_id, CollectedArticle.id.in_(body.ids))
            .update(
                {CollectedArticle.is_deleted: True, CollectedArticle.deleted_at: datetime.now(timezone.utc)},
                synchronize_session=False,
            )
        )
        session.commit()
        return {"ok": True, "updated": n}
    finally:
        session.close()


# Screening stats (decision tallies for the Library summary cards)

@app.get("/api/projects/{project_id}/screening-stats")
def screening_stats(project_id: int):
    session = new_session()
    try:
        base = (
            session.query(CollectedArticle)
            .filter_by(project_id=project_id)
            .filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
        )
        unscreened_vals = [v for v in UNSCREENED if v is not None]
        return {
            "total": base.count(),
            "unscreened": base.filter(CollectedArticle.screening_status.in_(unscreened_vals)).count(),
            "include": base.filter(CollectedArticle.screening_status == "include").count(),
            "maybe": base.filter(CollectedArticle.screening_status == "maybe").count(),
            "exclude": base.filter(CollectedArticle.screening_status == "exclude").count(),
            "from_search": base.filter((CollectedArticle.origin == "search") | (CollectedArticle.origin == None)).count(),  # noqa: E711
            "from_reference": base.filter(CollectedArticle.origin == "reference").count(),
            "refs_extracted": base.filter(CollectedArticle.references_extracted == True).count(),  # noqa: E712
        }
    finally:
        session.close()


# Reference harvest + analysis (snowballing / gap detection)

class HarvestRequest(BaseModel):
    article_ids: list[int] = []   # empty = all papers in the project with a DOI
    scope: str = "all"            # all | included | selected (informational)


class CollectRefs(BaseModel):
    items: list[dict]             # reference entries chosen from the missing list


@app.post("/api/projects/{project_id}/harvest-refs")
def harvest_refs(project_id: int, body: HarvestRequest):
    from utils.refs_job import find_active_job, start_refs_job

    existing = find_active_job(project_id)
    if existing:
        return {"job_id": existing, "already_running": True}
    return {"job_id": start_refs_job(project_id, body.article_ids), "already_running": False}


@app.get("/api/refs/{job_id}")
def refs_status(job_id: str):
    from utils.refs_job import get_status

    s = get_status(job_id)
    if s is None:
        raise HTTPException(404, "job not found")
    return s


@app.post("/api/refs/{job_id}/cancel")
def refs_cancel(job_id: str):
    from utils.refs_job import request_cancel

    request_cancel(job_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/refs/active")
def refs_active(project_id: int):
    from utils.refs_job import find_active_job

    return {"job_id": find_active_job(project_id)}


@app.post("/api/projects/{project_id}/capture-refs")
def capture_refs(project_id: int, body: HarvestRequest):
    """Background OpenAlex reference capture (batched). Skips papers already done."""
    from utils.refs_capture import find_active_job, start_capture_job

    existing = find_active_job(project_id)
    if existing:
        return {"job_id": existing, "already_running": True}
    return {"job_id": start_capture_job(project_id, body.article_ids), "already_running": False}


@app.get("/api/capture/{job_id}")
def capture_status(job_id: str):
    from utils.refs_capture import get_status

    s = get_status(job_id)
    if s is None:
        raise HTTPException(404, "job not found")
    return s


@app.post("/api/capture/{job_id}/cancel")
def capture_cancel(job_id: str):
    from utils.refs_capture import request_cancel

    request_cancel(job_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/capture/active")
def capture_active(project_id: int):
    from utils.refs_capture import find_active_job, latest_result

    return {"job_id": find_active_job(project_id), "latest_result": latest_result(project_id)}


@app.post("/api/projects/{project_id}/analysis/build")
def analysis_build(project_id: int):
    """Dedupe + cross-match references (local). Auto-copies cross-project
    matches; returns the de-duplicated 'missing papers' gap list."""
    from utils.ref_analysis import build_analysis

    return build_analysis(project_id)


@app.get("/api/projects/{project_id}/insights")
def project_insights(project_id: int):
    """Fast, local corpus analytics: year trend + saturation, top authors/venues,
    and the foundational core (most internally-cited papers). No API calls."""
    from utils.insights import build_insights

    return build_insights(project_id)


@app.post("/api/projects/{project_id}/collect-refs")
def collect_refs(project_id: int, body: CollectRefs):
    """Add chosen missing references to the library (origin='reference')."""
    from utils.ref_analysis import insert_references

    return {"added": insert_references(project_id, body.items)}


# Export (full-metadata download — CSV / JSON / Excel)

@app.get("/api/projects/{project_id}/export")
def export_articles(
    project_id: int,
    format: str = Query("csv", pattern="^(csv|json|xlsx)$"),
    view: str = "active",  # active (default) | trash | all
):
    from utils.excel_export import articles_to_excel, filename_for
    from utils.export import articles_to_csv, articles_to_json

    session = new_session()
    try:
        proj = session.get(Project, project_id)
        if not proj:
            raise HTTPException(404, "project not found")
        query = session.query(CollectedArticle).filter_by(project_id=project_id)
        if view == "trash":
            query = query.filter(CollectedArticle.is_deleted == True)  # noqa: E712
        elif view == "active":
            query = query.filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
        rows = query.order_by(CollectedArticle.year.desc().nullslast(), CollectedArticle.id.desc()).all()

        if format == "csv":
            content: bytes | str = articles_to_csv(rows)
            media = "text/csv"
        elif format == "json":
            content = articles_to_json(rows)
            media = "application/json"
        else:
            content = articles_to_excel(rows)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        fname = filename_for(proj.name, "library", format)
    finally:
        session.close()

    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# Data quality (completeness audit + multi-source gap-fill worker)

@app.get("/api/projects/{project_id}/completeness")
def completeness(project_id: int):
    from utils.completeness import audit_project

    return audit_project(project_id)


@app.get("/api/projects/{project_id}/incomplete")
def incomplete(project_id: int, limit: int = Query(500, le=2000)):
    """The actual incomplete papers, for the per-paper 'fix this one' list."""
    from utils.completeness import list_incomplete

    return {"items": list_incomplete(project_id, limit)}


@app.post("/api/projects/{project_id}/enrich")
def start_enrich(project_id: int):
    from utils.enrich_job import find_active_job, start_enrich_job

    existing = find_active_job(project_id)
    if existing:
        return {"job_id": existing, "already_running": True}
    return {"job_id": start_enrich_job(project_id), "already_running": False}


@app.get("/api/enrich/{job_id}")
def enrich_status(job_id: str):
    from utils.enrich_job import get_status

    s = get_status(job_id)
    if s is None:
        raise HTTPException(404, "job not found")
    return s


@app.post("/api/enrich/{job_id}/cancel")
def enrich_cancel(job_id: str):
    from utils.enrich_job import request_cancel

    request_cancel(job_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/enrich/active")
def enrich_active(project_id: int):
    from utils.enrich_job import find_active_job

    return {"job_id": find_active_job(project_id)}


# Search / collect (exposes the existing background search engine)

@app.post("/api/projects/{project_id}/search")
def start_search(project_id: int, req: SearchRequest):
    session = new_session()
    try:
        if not session.get(Project, project_id):
            raise HTTPException(404, "project not found")
    finally:
        session.close()

    queries = [q.strip() for q in req.queries if q.strip()]
    if not queries:
        raise HTTPException(400, "at least one search query is required")

    from utils.search_job import find_active_job, start_job

    mode = _TYPE_TO_MODE.get(req.type, "both")
    existing = find_active_job(project_id, mode)
    if existing:
        return {"job_id": existing, "already_running": True}

    settings = {
        "max_per_source": max(1, min(req.max_per_source, 500)),
        "year_from": req.year_from or 0,
        "use_openalex": "openalex" in req.sources,
        "use_pubmed": "pubmed" in req.sources,
        "use_s2": "s2" in req.sources,
        "use_arxiv": "arxiv" in req.sources,
    }
    job_id = start_job(
        queries, settings, mode, project_id, req.title_keyword, req.match_mode, req.year_to or 0,
    )
    return {"job_id": job_id, "already_running": False}


@app.get("/api/search/{job_id}")
def search_status(job_id: str):
    from utils.search_job import get_status

    s = get_status(job_id)
    if s is None:
        raise HTTPException(404, "job not found")
    return s


@app.post("/api/search/{job_id}/cancel")
def search_cancel(job_id: str):
    from utils.search_job import request_cancel

    request_cancel(job_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/search/active")
def search_active(project_id: int, type: str = "both"):
    # Mode-agnostic so the UI re-attaches after a refresh regardless of the
    # search type that was used.
    from utils.search_job import find_active_any

    return {"job_id": find_active_any(project_id)}


# Network

@app.get("/api/projects/{project_id}/network")
def project_network(project_id: int, mode: str = Query("citation", pattern="^(citation|author|journal)$")):
    session = new_session()
    try:
        if not session.get(Project, project_id):
            raise HTTPException(404, "project not found")
    finally:
        session.close()
    return build_network(project_id, mode)


@app.get("/api/health")
def health():
    return {"status": "ok"}
