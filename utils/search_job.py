"""
Background search job manager.
Runs API searches in a daemon thread and writes progress to a JSON file.
The UI polls the file via st.fragment without blocking the page.
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

JOB_DIR = Path("search_jobs")
JOB_DIR.mkdir(exist_ok=True)


def start_job(
    queries: list[str],
    settings: dict,
    mode: str,           # "reviews" or "articles"
    project_id: int,
    title_keyword: str = "",   # comma-separated keywords; empty = no filter
    title_match_mode: str = "any",  # "any" or "all"
) -> str:
    job_id = str(uuid.uuid4())[:8]
    job_file = JOB_DIR / f"{job_id}.json"

    _write(job_file, {
        "job_id": job_id,
        "project_id": project_id,
        "mode": mode,
        "total": len(queries),
        "completed": 0,
        "current_query": "",
        "log": [],
        "total_added": 0,
        "total_skipped": 0,
        "done": False,
        "error": None,
    })

    thread = threading.Thread(
        target=_run,
        args=(job_file, queries, settings, mode, project_id, title_keyword, title_match_mode),
        daemon=True,
    )
    thread.start()
    return job_id


def get_status(job_id: str) -> dict | None:
    job_file = JOB_DIR / f"{job_id}.json"
    if not job_file.exists():
        return None
    try:
        return json.loads(job_file.read_text())
    except Exception:
        return None


def clear_job(job_id: str):
    job_file = JOB_DIR / f"{job_id}.json"
    if job_file.exists():
        job_file.unlink()


def find_active_job(project_id: int, mode: str) -> str | None:
    """Return the job_id of the most recently active job for this project+mode,
    or None. 'Active' means the JSON file exists and `done` is False (or missing).

    Used by pages on load to re-attach the progress UI after a browser refresh
    that lost session_state."""
    candidates = []
    for f in JOB_DIR.glob("*.json"):
        if f.name.startswith("queues_"):
            continue
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        if data.get("project_id") != project_id or data.get("mode") != mode:
            continue
        if data.get("done"):
            continue
        candidates.append((f.stat().st_mtime, data.get("job_id", f.stem)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


# Internal

def _write(path: Path, data: dict):
    path.write_text(json.dumps(data))


def _patch(path: Path, **kwargs):
    try:
        data = json.loads(path.read_text())
        data.update(kwargs)
        _write(path, data)
    except Exception:
        pass


def _parse_keywords(raw: str) -> list[str]:
    """Split comma- or newline-separated keyword string into clean lowercase tokens."""
    if not raw or not raw.strip():
        return []
    parts = raw.replace("\n", ",").split(",")
    return [p.strip().lower() for p in parts if p.strip()]


def _title_matches(title: str, keywords: list[str], mode: str = "any") -> bool:
    if not keywords:
        return True
    title_l = title.lower()
    if mode == "all":
        return all(kw in title_l for kw in keywords)
    return any(kw in title_l for kw in keywords)


def _run(job_file: Path, queries: list[str], settings: dict, mode: str, project_id: int, title_keyword: str = "", title_match_mode: str = "any"):
    from utils.search_runner import (
        run_review_search_with_status,
        run_article_search_with_status,
        run_both_search_with_status,
    )
    from database import init_db, new_session, CollectedArticle, Project

    init_db()
    total_added = 0
    total_skipped = 0
    keywords = _parse_keywords(title_keyword)
    _runner = {
        "reviews": run_review_search_with_status,
        "both": run_both_search_with_status,
    }.get(mode, run_article_search_with_status)

    try:
        for i, q in enumerate(queries):
            _patch(job_file, current_query=q, completed=i)

            fn = _runner
            results, source_errors = fn(q, **settings)

            # Apply title keyword filter before saving
            if keywords:
                filtered = [r for r in results if _title_matches(r["title"], keywords, title_match_mode)]
                skipped_this = len(results) - len(filtered)
                results = filtered
            else:
                skipped_this = 0

            session = new_session()
            try:
                # The unified Workspace always collects into the library
                # (CollectedArticle), regardless of review/article/both mode.
                existing_dois = {
                    a.doi.lower()
                    for a in session.query(CollectedArticle).filter_by(project_id=project_id).all()
                    if a.doi
                }
                existing_titles = {
                    a.title.lower()
                    for a in session.query(CollectedArticle).filter_by(project_id=project_id).all()
                }

                added = 0
                for art in results:
                    doi_l = (art.get("doi") or "").lower()
                    title_l = art["title"].lower()
                    if doi_l and doi_l in existing_dois:
                        continue
                    if title_l in existing_titles:
                        continue

                    record = CollectedArticle(
                        project_id=project_id,
                        title=art["title"],
                        doi=art.get("doi", ""),
                        abstract=art.get("abstract", ""),
                        authors=art.get("authors", ""),
                        year=art.get("year"),
                        source=art["source"],
                        url=art.get("url", ""),
                        pub_type=art.get("pub_type", ""),
                        screening_status="unscreened",
                    )
                    session.add(record)
                    existing_titles.add(title_l)
                    if doi_l:
                        existing_dois.add(doi_l)
                    added += 1

                proj = session.get(Project, project_id)
                if proj and proj.stage < 4:
                    proj.stage = 4

                session.commit()
                total_added += added
                total_skipped += skipped_this
            finally:
                session.close()

            data = json.loads(job_file.read_text())
            skip_note = f", {skipped_this} title-filtered" if skipped_this else ""
            error_note = f" (source warning: {', '.join(source_errors.keys())})" if source_errors else ""
            data["log"].append(
                f"[{i+1}/{len(queries)}] `{q}` -> {len(results)} matched, **{added} new saved**{skip_note}{error_note}"
            )
            data["completed"] = i + 1
            data["total_added"] = total_added
            data["total_skipped"] = total_skipped
            _write(job_file, data)

        _patch(job_file, done=True, completed=len(queries))

    except Exception as e:
        _patch(job_file, done=True, error=str(e))
