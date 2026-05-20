"""FastAPI backend for the LitMine React frontend.

Serves the existing SQLite data (projects, library articles, curated reviews,
cited articles) and the project network graphs as JSON. Reuses the same
`database`, `api/` and `utils/` modules as the Streamlit app, so both
frontends read and write the one local database.

Run locally:
    uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
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
        "screening_status": a.screening_status or "unscreened",
        "tags": a.tags or "",
        "notes": a.notes or "",
        "decision_reason": a.decision_reason or "",
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
                "literature_type": p.literature_type or "Both",
                "description": p.description or "",
                "library": session.query(CollectedArticle).filter_by(project_id=p.id).count(),
                "curated_reviews": session.query(CuratedReview).filter_by(project_id=p.id).count(),
                "cited": session.query(CitedArticle).filter_by(project_id=p.id).count(),
            })
        return out
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
            "literature_type": p.literature_type or "Both",
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
    pub_type: str = "all",
    limit: int = Query(100, le=2000),
    offset: int = 0,
):
    session = new_session()
    try:
        query = session.query(CollectedArticle).filter_by(project_id=project_id)
        if q.strip():
            query = query.filter(CollectedArticle.title.ilike(f"%{q.strip()}%"))
        if decision == "unscreened":
            query = query.filter(CollectedArticle.screening_status.in_([v for v in UNSCREENED if v is not None]))
        elif decision != "all":
            query = query.filter(CollectedArticle.screening_status == decision)
        if year_min:
            query = query.filter(CollectedArticle.year != None).filter(CollectedArticle.year >= year_min)  # noqa: E711
        if pub_type != "all":
            query = query.filter(CollectedArticle.pub_type == pub_type)
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
    finally:
        session.close()

    if with_references and data.get("doi"):
        # Fetch the paper's reference list on demand (Semantic Scholar + Crossref).
        try:
            from api.references import fetch_references

            data["references"] = fetch_references(data["doi"])
        except Exception as exc:
            data["references"] = []
            data["references_error"] = str(exc)
    return data


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
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            note = a.notes or ""
            if not note.startswith("[edited]"):
                a.notes = f"[edited] {note}".strip()
            a.imported_from = "manual-edit"
            session.commit()
        return {"ok": True, "changed": changed, "article": _article_dict(a)}
    finally:
        session.close()


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
