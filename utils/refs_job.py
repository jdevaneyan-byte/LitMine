"""Background reference-harvest worker: for a chosen set of library papers,
fetch each paper's reference list (free sources first, OpenAlex fallback) and
persist it to `references_json`. Parallel, resumable, cancelable, cached
(papers already extracted are skipped).

Progress/cancel use the shared job_io helpers.
"""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from utils.job_io import is_cancelled as _is_cancelled
from utils.job_io import patch as _patch
from utils.job_io import read_json as _read_json
from utils.job_io import request_cancel as _request_cancel
from utils.job_io import write_atomic as _write

JOB_DIR = Path("refs_jobs")
JOB_DIR.mkdir(exist_ok=True)


def start_refs_job(project_id: int, article_ids: list[int]) -> str:
    job_id = str(uuid.uuid4())[:8]
    job_file = JOB_DIR / f"{job_id}.json"
    _write(job_file, {
        "job_id": job_id,
        "project_id": project_id,
        "requested": 0,
        "skipped_no_doi": 0,
        "skipped_done": 0,
        "total": 0,
        "completed": 0,
        "with_refs": 0,
        "total_refs": 0,
        "current": "",
        "log": [],
        "done": False,
        "error": None,
    })
    threading.Thread(target=_run, args=(job_file, project_id, article_ids), daemon=True).start()
    return job_id


def get_status(job_id: str) -> dict | None:
    f = JOB_DIR / f"{job_id}.json"
    return _read_json(f) if f.exists() else None


def request_cancel(job_id: str):
    _request_cancel(JOB_DIR / f"{job_id}.json")


def find_active_job(project_id: int) -> str | None:
    best = None
    for f in JOB_DIR.glob("*.json"):
        d = _read_json(f)
        if d and d.get("project_id") == project_id and not d.get("done"):
            if best is None or f.stat().st_mtime > best[0]:
                best = (f.stat().st_mtime, d.get("job_id", f.stem))
    return best[1] if best else None


def _run(job_file: Path, project_id: int, article_ids: list[int]):
    from database import init_db, new_session, CollectedArticle
    from api.references import fetch_references, ReferenceFetchError

    init_db()
    try:
        # Resolve targets: requested ids that have a DOI and aren't done yet.
        session = new_session()
        try:
            q = session.query(CollectedArticle).filter_by(project_id=project_id)
            if article_ids:
                q = q.filter(CollectedArticle.id.in_(article_ids))
            arts = q.all()
            no_doi = sum(1 for a in arts if not (a.doi or "").strip())
            already = sum(1 for a in arts if (a.doi or "").strip() and a.references_extracted)
            targets = [
                (a.id, (a.doi or "").strip(), (a.title or "")[:70])
                for a in arts
                if (a.doi or "").strip() and not a.references_extracted
            ]
        finally:
            session.close()

        _patch(
            job_file,
            total=len(targets),
            requested=len(arts),
            skipped_no_doi=no_doi,
            skipped_done=already,
        )
        completed = 0
        with_refs = 0
        total_refs = 0

        def fetch(item):
            aid, doi, label = item
            try:
                return aid, label, fetch_references(doi), None
            except ReferenceFetchError as exc:
                return aid, label, [], str(exc)
            except Exception as exc:  # never let one paper kill the run
                return aid, label, [], str(exc)

        # Fetch in parallel; persist results as they arrive.
        with ThreadPoolExecutor(max_workers=6) as pool:
            for aid, label, refs, err in pool.map(fetch, targets):
                if _is_cancelled(job_file):
                    data = _read_json(job_file) or {}
                    data.setdefault("log", []).append(f"Cancelled after {completed} of {len(targets)}.")
                    data["done"] = True
                    _write(job_file, data)
                    return

                session = new_session()
                try:
                    art = session.get(CollectedArticle, aid)
                    if art is not None:
                        art.references_json = json.dumps(refs)
                        art.references_extracted = True
                        art.references_count = len(refs)
                        session.commit()
                finally:
                    session.close()

                completed += 1
                if refs:
                    with_refs += 1
                    total_refs += len(refs)
                data = _read_json(job_file) or {}
                data["completed"] = completed
                data["with_refs"] = with_refs
                data["total_refs"] = total_refs
                data["current"] = label
                if err and len(data.get("log", [])) < 200:
                    data.setdefault("log", []).append(f"[{completed}] {label}: {err}")
                _write(job_file, data)

        _patch(job_file, done=True, completed=completed)
    except Exception as exc:
        _patch(job_file, done=True, error=str(exc))
