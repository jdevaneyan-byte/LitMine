"""Build network graphs for a project from data already in the database.

Three modes, all derived from existing rows (no new API calls):

- "citation": curated reviews -> the references they cite. A cited paper's
  node weight is the number of distinct reviews that cite it ("cited more").
- "author":   co-authorship — authors linked when they share a paper.
- "journal":  journal-to-journal — a review's journal linked to the venue of
  each paper it cites, weighted by how often.

Returns Cytoscape-friendly dicts: {"nodes": [...], "edges": [...], "stats": {...}}.
Node/edge sizes are pre-computed so the frontend can render directly.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from itertools import combinations

from database import CitedArticle, CollectedArticle, CuratedReview, new_session

MAX_NODES = 800  # cap so the browser graph stays responsive


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _split_authors(raw: str | None) -> list[str]:
    if not raw:
        return []
    cleaned = raw.replace(" and ", ",").replace(";", ",")
    out = []
    for part in cleaned.split(","):
        name = _norm(part)
        if name and name.lower() != "et al." and not name.lower().startswith("et al"):
            out.append(name)
    return out


def build_network(project_id: int, mode: str = "citation") -> dict:
    if mode == "author":
        return _author_network(project_id)
    if mode == "journal":
        return _journal_network(project_id)
    return _citation_network(project_id)


# Citation: review -> cited reference

def _citation_network(project_id: int) -> dict:
    session = new_session()
    try:
        reviews = session.query(CuratedReview).filter_by(project_id=project_id).all()
        cited = (
            session.query(CitedArticle)
            .filter_by(project_id=project_id, status="kept")
            .all()
        )
    finally:
        session.close()

    # How many distinct reviews cite each paper (by DOI, else normalized title).
    def cited_key(a):
        return (a.doi or "").lower() or _norm(a.title).lower()

    citers = defaultdict(set)
    for a in cited:
        citers[cited_key(a)].add(a.curated_review_id)

    nodes, edges = [], []
    seen = set()

    for r in reviews:
        nid = f"R{r.id}"
        nodes.append({
            "id": nid,
            "label": (r.title or f"Review {r.id}")[:90],
            "type": "review",
            "year": r.year,
            "doi": r.doi or "",
            "weight": 3,
        })
        seen.add(nid)

    # Add cited papers, sized by how many reviews cite them; keep the most-cited.
    by_key: dict[str, CitedArticle] = {}
    for a in cited:
        by_key.setdefault(cited_key(a), a)
    ranked = sorted(by_key.items(), key=lambda kv: -len(citers[kv[0]]))
    kept_keys = set()
    for key, a in ranked[: MAX_NODES - len(reviews)]:
        nid = f"C{a.id}"
        kept_keys.add(key)
        nodes.append({
            "id": nid,
            "label": (a.title or "")[:90],
            "type": "review-ref" if a.is_review else "paper",
            "year": a.year,
            "doi": a.doi or "",
            "weight": 1 + len(citers[key]),  # cited-more = bigger
            "cited_by_count": len(citers[key]),
        })

    # Edges review -> cited (only for kept cited nodes).
    key_to_node = {cited_key(a): f"C{a.id}" for a in by_key.values()}
    for a in cited:
        key = cited_key(a)
        if key not in kept_keys:
            continue
        edges.append({
            "source": f"R{a.curated_review_id}",
            "target": key_to_node[key],
            "type": "cites",
        })

    return {
        "mode": "citation",
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "reviews": len(reviews),
            "cited_nodes": len(kept_keys),
            "edges": len(edges),
            "truncated": len(by_key) > (MAX_NODES - len(reviews)),
        },
    }


# Author co-authorship

def _author_network(project_id: int) -> dict:
    session = new_session()
    try:
        rows = session.query(CollectedArticle).filter_by(project_id=project_id).all()
        if not rows:
            rows = session.query(CitedArticle).filter_by(project_id=project_id, status="kept").all()
    finally:
        session.close()

    paper_count = Counter()
    co = Counter()
    for r in rows:
        authors = _split_authors(getattr(r, "authors", ""))[:10]
        for a in authors:
            paper_count[a] += 1
        for a, b in combinations(sorted(set(authors)), 2):
            co[(a, b)] += 1

    top_authors = [a for a, _ in paper_count.most_common(MAX_NODES)]
    keep = set(top_authors)
    nodes = [
        {"id": a, "label": a, "type": "author", "weight": 1 + paper_count[a], "papers": paper_count[a]}
        for a in top_authors
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


# Journal-to-journal citation

def _journal_network(project_id: int) -> dict:
    session = new_session()
    try:
        reviews = {r.id: r for r in session.query(CuratedReview).filter_by(project_id=project_id).all()}
        cited = session.query(CitedArticle).filter_by(project_id=project_id, status="kept").all()
    finally:
        session.close()

    paper_count = Counter()
    flow = Counter()
    for a in cited:
        dest = _norm(a.venue)
        if dest:
            paper_count[dest] += 1
        review = reviews.get(a.curated_review_id)
        src = _norm(review.journal) if review else ""
        if src and dest and src != dest:
            flow[(src, dest)] += 1
        if src:
            paper_count[src] += 0  # ensure source journals appear

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
