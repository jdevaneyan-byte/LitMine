"""Background data-quality worker: walks the incomplete articles of a project
and fills their missing fields by cascading across open sources (Crossref ->
OpenAlex -> Semantic Scholar). Only papers with a DOI are auto-filled; the
rest are reported as needing manual attention.

Progress/cancel use the shared job_io helpers (atomic writes + cancel token).
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from utils.job_io import is_cancelled as _is_cancelled
from utils.job_io import patch as _patch
from utils.job_io import read_json as _read_json
from utils.job_io import request_cancel as _request_cancel
from utils.job_io import write_atomic as _write

JOB_DIR = Path("enrich_jobs")
JOB_DIR.mkdir(exist_ok=True)


def start_enrich_job(project_id: int) -> str:
    job_id = str(uuid.uuid4())[:8]
    job_file = JOB_DIR / f"{job_id}.json"
    _write(job_file, {
        "job_id": job_id,
        "project_id": project_id,
        "total": 0,
        "completed": 0,
        "current": "",
        "filled_fields": 0,
        "records_improved": 0,
        "log": [],
        "done": False,
        "error": None,
    })
    threading.Thread(target=_run, args=(job_file, project_id), daemon=True).start()
    return job_id


def get_status(job_id: str) -> dict | None:
    f = JOB_DIR / f"{job_id}.json"
    return _read_json(f) if f.exists() else None


def request_cancel(job_id: str):
    _request_cancel(JOB_DIR / f"{job_id}.json")


def clear_job(job_id: str):
    f = JOB_DIR / f"{job_id}.json"
    if f.exists():
        f.unlink()


def find_active_job(project_id: int) -> str | None:
    candidates = []
    for f in JOB_DIR.glob("*.json"):
        data = _read_json(f)
        if data and data.get("project_id") == project_id and not data.get("done"):
            candidates.append((f.stat().st_mtime, data.get("job_id", f.stem)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _run(job_file: Path, project_id: int):
    from database import init_db, new_session, CollectedArticle
    from utils.completeness import missing_fields
    from utils.enrich import fill_gaps

    init_db()
    try:
        session = new_session()
        try:
            rows = (
                session.query(CollectedArticle)
                .filter_by(project_id=project_id)
                .filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
                .all()
            )
            # Only incomplete records with a DOI can be auto-filled.
            targets = [a.id for a in rows if missing_fields(a) and (a.doi or "").strip()]
        finally:
            session.close()

        _patch(job_file, total=len(targets))
        filled_total = 0
        improved = 0

        for i, art_id in enumerate(targets):
            if _is_cancelled(job_file):
                data = _read_json(job_file) or {}
                data.setdefault("log", []).append(f"Cancelled after {i} of {len(targets)}.")
                data["done"] = True
                _write(job_file, data)
                return

            session = new_session()
            try:
                art = session.get(CollectedArticle, art_id)
                if art is None:
                    continue
                rec = {
                    "doi": art.doi,
                    "title": art.title,
                    "authors": art.authors,
                    "year": art.year,
                    "abstract": art.abstract,
                    "venue": art.venue,
                    "pub_type": art.pub_type,
                    "citation_count": art.citation_count,
                    "url": art.url,
                }
                label = (art.title or art.doi or f"#{art_id}")[:70]
            finally:
                session.close()

            filled = fill_gaps(rec)

            if filled:
                session = new_session()
                try:
                    art = session.get(CollectedArticle, art_id)
                    if art is not None:
                        for f in filled:
                            setattr(art, f, rec[f])
                        # Refresh the normalized category if the type was filled.
                        if "pub_type" in filled:
                            from utils.pub_category import categorize

                            art.category = categorize(art.pub_type, art.source, art.title)
                        session.commit()
                        improved += 1
                        filled_total += len(filled)
                finally:
                    session.close()

            data = _read_json(job_file) or {}
            data["completed"] = i + 1
            data["current"] = label
            data["filled_fields"] = filled_total
            data["records_improved"] = improved
            if filled:
                data.setdefault("log", []).append(f"[{i+1}/{len(targets)}] `{label}` -> filled {', '.join(filled)}")
            _write(job_file, data)

        _patch(job_file, done=True, completed=len(targets))
    except Exception as exc:
        _patch(job_file, done=True, error=str(exc))
