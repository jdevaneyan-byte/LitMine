"""Build network graphs for a project from the collected corpus.

Rebuilt to read `CollectedArticle` (the search/reference library) instead of the
retired Streamlit tables — search-based projects have no CuratedReview /
CitedArticle rows, which is why the old builder rendered blank.

Three modes, all derived from existing rows (no new API calls):

- "citation": paper -> paper, from `referenced_ids` (OpenAlex ids). An edge
  A->B exists when B's OpenAlex id appears in A's reference ids and both are in
  the corpus. Node weight = in-degree (how many of your papers cite it).
- "author":   co-authorship — authors linked when they share a paper.
- "journal":  venue -> venue, aggregated from the citation edges (citing
  paper's venue cites the cited paper's venue).

Optional filters narrow the corpus first: year range, included-only, and a
minimum global citation count.

Returns {"nodes": [...], "edges": [...], "stats": {...}}; sizes pre-computed.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from itertools import combinations

from database import CollectedArticle, new_session

MAX_NODES = 800  # cap so the browser graph stays responsive


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _short(oa: str | None) -> str:
    return (oa or "").rsplit("/", 1)[-1]


def _ref_ids(raw: str | None) -> list[str]:
    try:
        v = json.loads(raw or "[]")
        return [_short(x) for x in v] if isinstance(v, list) else []
    except Exception:
        return []


def _split_authors(raw: str | None) -> list[str]:
    if not raw:
        return []
    cleaned = raw.replace(" and ", ",").replace(";", ",")
    out = []
    for part in cleaned.split(","):
        name = _norm(part)
        if name and not name.lower().startswith("et al"):
            out.append(name)
    return out


def _load_rows(project_id: int, year_min: int, year_max: int, included_only: bool, min_citations: int):
    session = new_session()
    try:
        q = (
            session.query(CollectedArticle)
            .filter_by(project_id=project_id)
            .filter((CollectedArticle.is_deleted == False) | (CollectedArticle.is_deleted == None))  # noqa: E711,E712
        )
        if year_min:
            q = q.filter(CollectedArticle.year != None).filter(CollectedArticle.year >= year_min)  # noqa: E711
        if year_max:
            q = q.filter(CollectedArticle.year != None).filter(CollectedArticle.year <= year_max)  # noqa: E711
        if included_only:
            q = q.filter(CollectedArticle.screening_status == "include")
        if min_citations:
            q = q.filter(CollectedArticle.citation_count != None).filter(  # noqa: E711
                CollectedArticle.citation_count >= min_citations
            )
        return [
            {
                "id": a.id,
                "title": a.title or "",
                "year": a.year,
                "doi": a.doi or "",
                "venue": _norm(a.venue),
                "oa": a.openalex_id or "",
                "refs": a.referenced_ids or "",
                "authors": a.authors or "",
                "citation_count": a.citation_count,
                "origin": a.origin or "search",
            }
            for a in q.all()
        ]
    finally:
        session.close()


def build_network(
    project_id: int,
    mode: str = "citation",
    year_min: int = 0,
    year_max: int = 0,
    included_only: bool = False,
    min_citations: int = 0,
) -> dict:
    rows = _load_rows(project_id, year_min, year_max, included_only, min_citations)
    if mode == "author":
        return _author_network(rows)
    if mode == "journal":
        return _journal_network(rows)
    return _citation_network(rows)


# Citation: paper -> paper, from referenced_ids

def _citation_network(rows: list[dict]) -> dict:
    oa_to_id = {r["oa"]: r["id"] for r in rows if r["oa"]}
    by_id = {r["id"]: r for r in rows}

    # Directed edges + in-degree (how many corpus papers cite each target).
    edge_pairs = set()
    indeg: Counter[int] = Counter()
    for r in rows:
        for cid in _ref_ids(r["refs"]):
            tgt = oa_to_id.get(cid)
            if tgt and tgt != r["id"]:
                edge_pairs.add((r["id"], tgt))
    for _src, tgt in edge_pairs:
        indeg[tgt] += 1

    # Keep nodes that participate in at least one edge, ranked by in-degree.
    connected = {s for s, _ in edge_pairs} | {t for _, t in edge_pairs}
    ranked = sorted(connected, key=lambda i: -indeg.get(i, 0))
    kept = set(ranked[:MAX_NODES])

    nodes = []
    for nid in kept:
        r = by_id[nid]
        nodes.append({
            "id": str(nid),
            "article_id": nid,
            "label": (r["title"] or "")[:90],
            "type": "reference" if r["origin"] == "reference" else "paper",
            "year": r["year"],
            "doi": r["doi"],
            "weight": 1 + indeg.get(nid, 0),
            "cited_by_count": indeg.get(nid, 0),
        })
    edges = [
        {"source": str(s), "target": str(t), "type": "cites"}
        for (s, t) in edge_pairs
        if s in kept and t in kept
    ]
    return {
        "mode": "citation",
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "papers": len(rows),
            "nodes": len(nodes),
            "edges": len(edges),
            "truncated": len(connected) > MAX_NODES,
        },
    }


# Author co-authorship

def _author_network(rows: list[dict]) -> dict:
    paper_count: Counter[str] = Counter()
    co: Counter[tuple[str, str]] = Counter()
    for r in rows:
        authors = _split_authors(r["authors"])[:10]
        for a in authors:
            paper_count[a] += 1
        for a, b in combinations(sorted(set(authors)), 2):
            co[(a, b)] += 1

    top = [a for a, _ in paper_count.most_common(MAX_NODES)]
    keep = set(top)
    nodes = [
        {"id": a, "label": a, "type": "author", "weight": 1 + paper_count[a], "papers": paper_count[a]}
        for a in top
    ]
    edges = [
        {"source": a, "target": b, "type": "coauthor", "weight": n}
        for (a, b), n in co.items()
        if a in keep and b in keep
    ]
    return {
        "mode": "author",
        "nodes": nodes,
        "edges": edges,
        "stats": {"authors": len(nodes), "edges": len(edges), "truncated": len(paper_count) > MAX_NODES},
    }


# Journal-to-journal, aggregated from citation edges

def _journal_network(rows: list[dict]) -> dict:
    oa_to_id = {r["oa"]: r["id"] for r in rows if r["oa"]}
    by_id = {r["id"]: r for r in rows}

    paper_count: Counter[str] = Counter()
    for r in rows:
        if r["venue"]:
            paper_count[r["venue"]] += 1

    flow: Counter[tuple[str, str]] = Counter()
    for r in rows:
        src = r["venue"]
        if not src:
            continue
        for cid in _ref_ids(r["refs"]):
            tgt_id = oa_to_id.get(cid)
            if not tgt_id or tgt_id == r["id"]:
                continue
            dst = by_id[tgt_id]["venue"]
            if dst and dst != src:
                flow[(src, dst)] += 1

    top = [j for j, _ in paper_count.most_common(MAX_NODES)]
    keep = set(top)
    nodes = [
        {"id": j, "label": j, "type": "journal", "weight": 1 + paper_count[j], "papers": paper_count[j]}
        for j in top
    ]
    edges = [
        {"source": s, "target": d, "type": "journal-cites", "weight": n}
        for (s, d), n in flow.items()
        if s in keep and d in keep
    ]
    return {
        "mode": "journal",
        "nodes": nodes,
        "edges": edges,
        "stats": {"journals": len(nodes), "edges": len(edges), "truncated": len(paper_count) > MAX_NODES},
    }
