"""Find probable duplicate rows in CollectedArticle that slipped past
the at-insert dedup (e.g. punctuation/whitespace differences when DOIs
were missing or differed across sources)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from database import CollectedArticle, new_session

SIM_THRESHOLD = 0.94
MIN_TITLE_LEN = 35


@dataclass
class DupCluster:
    cluster_id: int
    members: list[CollectedArticle]


def normalize_title(title: str | None) -> str:
    t = (title or "").strip().lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def find_clusters(project_id: int, max_clusters: int = 50) -> list[DupCluster]:
    """Return groups of probable duplicate articles within one project.

    Strategy:
    1. Exact DOI matches (deterministic) → cluster.
    2. Same normalized title → cluster.
    3. Fuzzy title match within the same year (>=SIM_THRESHOLD) → cluster.

    Limited to `max_clusters` to keep the UI manageable. Sorted by cluster
    size descending so the worst offenders surface first.
    """

    session = new_session()
    try:
        rows = session.query(CollectedArticle).filter_by(project_id=project_id).all()
    finally:
        session.close()

    parent = {a.id: a.id for a in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    # Same-DOI clusters (lowercased).
    by_doi: dict[str, list[CollectedArticle]] = defaultdict(list)
    for a in rows:
        if a.doi:
            by_doi[a.doi.strip().lower()].append(a)
    for group in by_doi.values():
        for other in group[1:]:
            union(group[0].id, other.id)

    # Same normalized-title clusters.
    by_title: dict[str, list[CollectedArticle]] = defaultdict(list)
    for a in rows:
        key = normalize_title(a.title)
        if len(key) >= MIN_TITLE_LEN:
            by_title[key].append(a)
    for group in by_title.values():
        for other in group[1:]:
            union(group[0].id, other.id)

    # Fuzzy within same year — bucket by year and only compare within bucket
    # to keep it O(n^2/k) instead of O(n^2). Skip groups bigger than 600 (slow).
    by_year: dict[int | None, list[CollectedArticle]] = defaultdict(list)
    for a in rows:
        by_year[a.year].append(a)
    for year, group in by_year.items():
        if len(group) > 600:
            continue
        keys = [(a, normalize_title(a.title)) for a in group]
        for i in range(len(keys)):
            a_i, k_i = keys[i]
            if len(k_i) < MIN_TITLE_LEN:
                continue
            for j in range(i + 1, len(keys)):
                a_j, k_j = keys[j]
                if len(k_j) < MIN_TITLE_LEN:
                    continue
                if find(a_i.id) == find(a_j.id):
                    continue
                if abs(len(k_i) - len(k_j)) > max(15, int(0.15 * min(len(k_i), len(k_j)))):
                    continue
                if SequenceMatcher(None, k_i, k_j).ratio() >= SIM_THRESHOLD:
                    union(a_i.id, a_j.id)

    groups: dict[int, list[CollectedArticle]] = defaultdict(list)
    for a in rows:
        groups[find(a.id)].append(a)

    clusters = [DupCluster(cluster_id=cid, members=members) for cid, members in groups.items() if len(members) > 1]
    clusters.sort(key=lambda c: (-len(c.members), c.cluster_id))
    return clusters[:max_clusters]


def merge_into(keeper_id: int, dropped_ids: list[int]) -> int:
    """Delete the dropped rows after copying any non-empty fields from them
    into the keeper. Returns count of rows deleted."""
    if not dropped_ids:
        return 0

    session = new_session()
    try:
        keeper = session.get(CollectedArticle, keeper_id)
        if keeper is None:
            return 0
        dropped = (
            session.query(CollectedArticle)
            .filter(CollectedArticle.id.in_(dropped_ids))
            .filter(CollectedArticle.id != keeper_id)
            .all()
        )
        for src in dropped:
            for field in ("abstract", "doi", "url", "authors", "notes", "tags", "pdf_path"):
                if not getattr(keeper, field, None) and getattr(src, field, None):
                    setattr(keeper, field, getattr(src, field))
            if not keeper.year and src.year:
                keeper.year = src.year
        for src in dropped:
            session.delete(src)
        session.commit()
        return len(dropped)
    finally:
        session.close()


def pick_keeper(members: list[CollectedArticle]) -> CollectedArticle:
    """Score each member and pick the row that should remain after merge.
    Priority: has DOI · longer abstract · longer authors · longer title · lowest id."""
    return max(
        members,
        key=lambda m: (
            bool(m.doi),
            len(m.abstract or ""),
            len(m.authors or ""),
            len(m.title or ""),
            -m.id,
        ),
    )


def merge_all_clusters(clusters: list[DupCluster]) -> tuple[int, int]:
    """For each cluster, auto-pick the keeper and merge all other members
    into it. Returns (groups_merged, rows_deleted)."""
    groups = 0
    deleted = 0
    for c in clusters:
        if len(c.members) < 2:
            continue
        keeper = pick_keeper(c.members)
        dropped_ids = [m.id for m in c.members if m.id != keeper.id]
        if not dropped_ids:
            continue
        n = merge_into(keeper.id, dropped_ids)
        if n:
            groups += 1
            deleted += n
    return groups, deleted
