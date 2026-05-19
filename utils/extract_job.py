"""Background job that walks each curated review, fetches its references,
applies the year/review filter, and writes results to the CitedArticle table."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

JOB_DIR = Path("extract_jobs")
JOB_DIR.mkdir(exist_ok=True)


def start_extract_job(
    project_id: int,
    review_ids: list[int],
    year_floor: int = 2019,
    keep_reviews_regardless_of_year: bool = True,
) -> str:
    job_id = str(uuid.uuid4())[:8]
    job_file = JOB_DIR / f"{job_id}.json"
    _write(
        job_file,
        {
            "job_id": job_id,
            "project_id": project_id,
            "total": len(review_ids),
            "completed": 0,
            "current_review": "",
            "log": [],
            "totals": {"kept": 0, "rejected": 0, "reviews_flagged": 0, "no_refs": 0},
            "done": False,
            "error": None,
        },
    )

    thread = threading.Thread(
        target=_run,
        args=(job_file, project_id, review_ids, year_floor, keep_reviews_regardless_of_year),
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


def find_active_job(project_id: int) -> str | None:
    """Return the job_id of the most recently active extract job for this
    project, or None. Used to re-attach the progress UI after a refresh."""
    candidates = []
    for f in JOB_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        if data.get("project_id") != project_id:
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


def _run(
    job_file: Path,
    project_id: int,
    review_ids: list[int],
    year_floor: int,
    keep_reviews_regardless_of_year: bool,
):
    from api.references import fetch_references, ReferenceFetchError
    from database import init_db, new_session, CuratedReview, CitedArticle

    init_db()

    try:
        for i, review_id in enumerate(review_ids):
            session = new_session()
            try:
                review = session.get(CuratedReview, review_id)
                if review is None:
                    continue
                review_label = f"{review.title[:80]}" if review.title else f"#{review.id}"
                review_doi = (review.doi or "").strip().lower()
                _patch(job_file, current_review=review_label, completed=i)
                review.extraction_status = "running"
                review.extraction_error = ""
                session.commit()

                if not review_doi:
                    review.extraction_status = "no_refs"
                    review.extraction_error = "No DOI on this review; cannot fetch references."
                    session.commit()
                    _append_log(job_file, f"[{i+1}/{len(review_ids)}] `{review_label}` -> skipped (no DOI)")
                    _bump(job_file, no_refs=1)
                    continue

                # Existing dedup keys for this project (cited articles).
                existing = {
                    (a.curated_review_id, (a.doi or "").lower(), (a.title or "").lower())
                    for a in session.query(CitedArticle).filter_by(
                        project_id=project_id, curated_review_id=review.id
                    )
                }
            finally:
                session.close()

            try:
                refs = fetch_references(review_doi)
            except ReferenceFetchError as exc:
                _set_review_failure(review_id, f"Fetch failed: {exc}")
                _append_log(job_file, f"[{i+1}/{len(review_ids)}] `{review_label}` -> ERROR: {exc}")
                _bump(job_file, no_refs=1)
                continue

            if not refs:
                _set_review_status(
                    review_id,
                    status="no_refs",
                    error="Reference list not available from S2 or Crossref.",
                    totals=(0, 0, 0),
                )
                _append_log(job_file, f"[{i+1}/{len(review_ids)}] `{review_label}` -> no references published")
                _bump(job_file, no_refs=1)
                continue

            kept = 0
            rejected = 0
            reviews_flagged = 0

            session = new_session()
            try:
                for ref in refs:
                    title_l = (ref.get("title") or "").lower()
                    doi_l = (ref.get("doi") or "").lower()
                    key = (review_id, doi_l, title_l)
                    if key in existing:
                        continue
                    existing.add(key)

                    year = ref.get("year")
                    is_review = bool(ref.get("is_review"))
                    status = "kept"
                    rejected_reason = ""

                    if is_review:
                        reviews_flagged += 1
                        if not keep_reviews_regardless_of_year and year is not None and year < year_floor:
                            status = "rejected"
                            rejected_reason = f"Review article older than {year_floor}"
                    else:
                        if year is None:
                            status = "rejected"
                            rejected_reason = "Year missing; cannot verify >= year_floor"
                        elif year < year_floor:
                            status = "rejected"
                            rejected_reason = f"Published {year} (< {year_floor})"

                    if status == "kept":
                        kept += 1
                    else:
                        rejected += 1

                    session.add(
                        CitedArticle(
                            project_id=project_id,
                            curated_review_id=review_id,
                            title=ref.get("title") or "",
                            doi=ref.get("doi") or "",
                            year=year,
                            authors=ref.get("authors") or "",
                            venue=ref.get("venue") or "",
                            abstract=ref.get("abstract") or "",
                            url=ref.get("url") or "",
                            is_review=is_review,
                            publication_types=ref.get("publication_types") or "",
                            source=ref.get("source") or "",
                            status=status,
                            rejected_reason=rejected_reason,
                        )
                    )

                review = session.get(CuratedReview, review_id)
                review.extraction_status = "done"
                review.references_total = len(refs)
                review.references_kept = kept
                review.references_rejected = rejected
                review.last_extracted_at = datetime.now(timezone.utc)
                session.commit()
            finally:
                session.close()

            _append_log(
                job_file,
                f"[{i+1}/{len(review_ids)}] `{review_label}` -> {len(refs)} refs, "
                f"**{kept} kept**, {rejected} rejected, {reviews_flagged} flagged-as-review",
            )
            _bump(job_file, kept=kept, rejected=rejected, reviews_flagged=reviews_flagged)

        _patch(job_file, done=True, completed=len(review_ids))

    except Exception as exc:
        _patch(job_file, done=True, error=str(exc))


def _set_review_status(review_id: int, *, status: str, error: str, totals: tuple[int, int, int]):
    from database import new_session, CuratedReview

    session = new_session()
    try:
        review = session.get(CuratedReview, review_id)
        if review:
            review.extraction_status = status
            review.extraction_error = error
            review.references_total, review.references_kept, review.references_rejected = totals
            review.last_extracted_at = datetime.now(timezone.utc)
            session.commit()
    finally:
        session.close()


def _set_review_failure(review_id: int, error: str):
    from database import new_session, CuratedReview

    session = new_session()
    try:
        review = session.get(CuratedReview, review_id)
        if review:
            review.extraction_status = "failed"
            review.extraction_error = error
            session.commit()
    finally:
        session.close()


def _append_log(job_file: Path, line: str):
    try:
        data = json.loads(job_file.read_text())
        data["log"].append(line)
        _write(job_file, data)
    except Exception:
        pass


def _bump(job_file: Path, **deltas):
    try:
        data = json.loads(job_file.read_text())
        for k, v in deltas.items():
            data["totals"][k] = data["totals"].get(k, 0) + v
        _write(job_file, data)
    except Exception:
        pass
