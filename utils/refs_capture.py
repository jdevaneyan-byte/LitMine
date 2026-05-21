"""Background gap-analysis worker (OpenAlex, batched, ID-matching).

One manual action — "Find missing papers" — runs three fast phases:

  1. Link citations: backfill each paper's `referenced_works` (OA ids) for any
     that don't have them yet, via a batched OpenAlex DOI lookup. New OpenAlex
     papers already carry them, so this is usually cheap.
  2. Match by id (local, no API): compare the cited ids against the library's
     own OA ids — instant. Anything already collected (here or in another
     project) is recognized; cross-project matches are auto-copied in.
  3. Resolve only the missing: look up titles for the top missing candidates
     (not all of them), so the gap list is ready in seconds, not minutes.

The de-duplicated "missing papers" result is stored in the job file.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from utils.job_io import is_cancelled as _is_cancelled
from utils.job_io import patch as _patch
from utils.job_io import read_json as _read_json
from utils.job_io import request_cancel as _request_cancel
from utils.job_io import write_atomic as _write

OPENALEX = "https://api.openalex.org"
JOB_DIR = Path("capture_jobs")
JOB_DIR.mkdir(exist_ok=True)
RESOLVE_CAP = 1000  # resolve titles for at most the top-N missing candidates


def _auth() -> dict:
    key = os.getenv("OPENALEX_API_KEY", "").strip()
    return {"api_key": key} if key else {}


def _short(oa: str) -> str:
    return (oa or "").rsplit("/", 1)[-1]


def _doi(d: str | None) -> str:
    return (d or "").replace("https://doi.org/", "").strip().lower()


def start_capture_job(project_id: int, article_ids: list[int]) -> str:
    job_id = str(uuid.uuid4())[:8]
    job_file = JOB_DIR / f"{job_id}.json"
    _write(job_file, {
        "job_id": job_id,
        "project_id": project_id,
        "phase": "starting",
        "total": 0,
        "completed": 0,
        "no_doi": 0,
        "done": False,
        "error": None,
        "result": None,
    })
    threading.Thread(target=_run, args=(job_file, project_id, article_ids), daemon=True).start()
    return job_id


def get_status(job_id: str) -> dict | None:
    f = JOB_DIR / f"{job_id}.json"
    return _read_json(f) if f.exists() else None


def request_cancel(job_id: str):
    _request_cancel(JOB_DIR / f"{job_id}.json")


def latest_result(project_id: int) -> dict | None:
    # The most recently finished job's gap result for this project, so the tab
    # can display what the post-search background run already found without
    # kicking off a fresh run.
    best = None
    for f in JOB_DIR.glob("*.json"):
        d = _read_json(f)
        if d and d.get("project_id") == project_id and d.get("done") and d.get("result"):
            if best is None or f.stat().st_mtime > best[0]:
                best = (f.stat().st_mtime, d["result"])
    return best[1] if best else None


def find_active_job(project_id: int) -> str | None:
    # A live job updates its file every few seconds; if a file hasn't changed in
    # a while it's an orphan (its worker thread died, e.g. on a server restart),
    # so we don't report it as active and block the user.
    best = None
    for f in JOB_DIR.glob("*.json"):
        d = _read_json(f)
        if d and d.get("project_id") == project_id and not d.get("done"):
            if time.time() - f.stat().st_mtime > 120:
                continue
            if best is None or f.stat().st_mtime > best[0]:
                best = (f.stat().st_mtime, d.get("job_id", f.stem))
    return best[1] if best else None


def _batch(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _resolve(oa_ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    sel = "id,doi,title,publication_year,authorships,primary_location,type"
    for chunk in _batch(oa_ids, 50):
        try:
            r = requests.get(
                f"{OPENALEX}/works",
                params={"filter": f"openalex_id:{'|'.join(chunk)}", "per-page": 50, "select": sel, **_auth()},
                timeout=30,
            )
            if r.status_code != 200:
                continue
            for w in (r.json() or {}).get("results", []) or []:
                authors = [a.get("author", {}).get("display_name", "") for a in (w.get("authorships") or [])[:8] if a.get("author")]
                src = (w.get("primary_location") or {}).get("source") or {}
                out[_short(w.get("id") or "")] = {
                    "title": (w.get("title") or "").strip(),
                    "doi": _doi(w.get("doi")),
                    "year": w.get("publication_year"),
                    "authors": ", ".join(a for a in authors if a),
                    "venue": (src.get("display_name") or "").strip(),
                }
        except Exception:
            continue
        time.sleep(0.1)
    return out


def _aslist(raw: str) -> list[str]:
    try:
        v = json.loads(raw or "[]")
        return [_short(x) for x in v] if isinstance(v, list) else []
    except Exception:
        return []


def _run(job_file: Path, project_id: int, article_ids: list[int]):
    from collections import defaultdict

    from database import CollectedArticle, Project, init_db, new_session

    init_db()
    try:
        # Load this project's non-deleted papers (the citing set).
        session = new_session()
        try:
            # Snowball ONLY from the keyword-collected papers — never from papers
            # that were themselves added via snowballing, or the missing list
            # would expand without bound (2nd-degree, 3rd-degree, …).
            q = (
                session.query(CollectedArticle)
                .filter_by(project_id=project_id)
                .filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
                .filter((CollectedArticle.origin == "search") | (CollectedArticle.origin == None))  # noqa: E711
            )
            if article_ids:
                q = q.filter(CollectedArticle.id.in_(article_ids))
            rows = [
                {"id": a.id, "doi": (a.doi or "").strip(), "oa": a.openalex_id or "", "refs": a.referenced_ids or ""}
                for a in q.all()
            ]
        finally:
            session.close()

        # Phase 1 — Link citations: backfill referenced ids for papers missing them.
        need = [r for r in rows if not _aslist(r["refs"]) and r["doi"]]
        no_doi = sum(1 for r in rows if not _aslist(r["refs"]) and not r["doi"])
        _patch(job_file, phase="linking citations", total=len(need), completed=0, no_doi=no_doi)
        done = 0
        for chunk in _batch(need, 50):
            if _is_cancelled(job_file):
                _patch(job_file, done=True)
                return
            dmap = {}
            try:
                resp = requests.get(
                    f"{OPENALEX}/works",
                    params={"filter": f"doi:{'|'.join(r['doi'] for r in chunk)}", "per-page": 50,
                            "select": "id,doi,referenced_works", **_auth()},
                    timeout=30,
                )
                if resp.status_code == 200:
                    for w in (resp.json() or {}).get("results", []) or []:
                        dmap[_doi(w.get("doi"))] = (_short(w.get("id") or ""), [_short(x) for x in (w.get("referenced_works") or [])])
            except Exception:
                pass
            session = new_session()
            try:
                for r in chunk:
                    hit = dmap.get(r["doi"].lower())
                    if hit:
                        r["oa"], r["refs"] = hit[0], json.dumps(hit[1])
                        art = session.get(CollectedArticle, r["id"])
                        if art is not None:
                            art.openalex_id = hit[0]
                            art.referenced_ids = r["refs"]
                session.commit()
            finally:
                session.close()
            done += len(chunk)
            _patch(job_file, completed=done)
            time.sleep(0.05)

        # Phase 2 — Match by id (local, no API).
        _patch(job_file, phase="finding gaps", completed=0, total=0)
        citers: dict[str, set[int]] = defaultdict(set)
        for r in rows:
            for cid in _aslist(r["refs"]):
                citers[cid].add(r["id"])

        session = new_session()
        try:
            names = {p.id: p.name for p in session.query(Project).all()}
            corpus_oa: dict[str, tuple[int, int]] = {}
            corpus_doi: dict[str, tuple[int, int]] = {}
            for a in (
                session.query(CollectedArticle.id, CollectedArticle.project_id, CollectedArticle.doi, CollectedArticle.openalex_id)
                .filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
                .all()
            ):
                if a.openalex_id:
                    corpus_oa.setdefault(a.openalex_id, (a.project_id, a.id))
                if a.doi:
                    corpus_doi.setdefault(_doi(a.doi), (a.project_id, a.id))

            in_library = 0
            copied = 0
            candidates: list[tuple[str, int]] = []  # (oa_id, cited_by)
            for cid, who in citers.items():
                hit = corpus_oa.get(cid)
                if hit and hit[0] == project_id:
                    in_library += 1
                elif hit:
                    src = session.get(CollectedArticle, hit[1])
                    if src is not None:
                        session.add(_clone(src, project_id))
                        copied += 1
                else:
                    candidates.append((cid, len(who)))
            if copied:
                session.commit()
        finally:
            session.close()

        candidates.sort(key=lambda c: -c[1])
        top = candidates[:RESOLVE_CAP]

        # Phase 3 — Resolve only the missing candidates' titles.
        _patch(job_file, phase="resolving missing", completed=0, total=len(top))
        meta = _resolve([c[0] for c in top])

        missing = []
        for cid, cited_by in top:
            m = meta.get(cid)
            if not m:
                continue
            # A resolved candidate might already be in the corpus under a DOI
            # (papers collected without an OA id) — skip those.
            if m["doi"] and _doi(m["doi"]) in corpus_doi:
                continue
            if not (m["title"] or m["doi"]):
                continue
            missing.append({
                "key": f"oa:{cid}",
                "title": m["title"] or "(untitled)",
                "doi": m["doi"],
                "year": m["year"],
                "venue": m["venue"],
                "authors": m["authors"],
                "cited_by": cited_by,
            })

        capped = len(candidates) > RESOLVE_CAP
        result = {
            "papers_analyzed": len(rows),
            "unique_references": len(citers),
            "in_library": in_library,
            "copied_from_other_projects": copied,
            # When we resolved every candidate, the shown count IS the true count;
            # only report a larger total when we actually hit the resolve cap.
            "missing_total": len(candidates) if capped else len(missing),
            "missing_count": len(missing),
            "missing": missing,
        }
        _patch(job_file, done=True, phase="done", result=result, no_doi=no_doi)
    except Exception as exc:
        _patch(job_file, done=True, error=str(exc))


def _clone(src, project_id: int):
    from database import CollectedArticle

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
        openalex_id=src.openalex_id or "",
        screening_status="unscreened",
        origin="reference",
    )
