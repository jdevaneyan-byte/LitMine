from __future__ import annotations

import re
from difflib import SequenceMatcher


def normalize_doi(doi: str | None) -> str:
    doi = (doi or "").strip().lower()
    doi = doi.removeprefix("https://doi.org/")
    doi = doi.removeprefix("http://doi.org/")
    return doi.strip()


def normalize_title(title: str | None) -> str:
    title = (title or "").strip().lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _same_title(candidate: str, seen_titles: set[str]) -> bool:
    if not candidate:
        return False
    if candidate in seen_titles:
        return True
    for existing in seen_titles:
        if not existing:
            continue
        shorter = min(len(candidate), len(existing))
        if shorter < 35:
            continue
        if SequenceMatcher(None, candidate, existing).ratio() >= 0.94:
            return True
    return False


def deduplicate(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles by DOI, stable external IDs, or fuzzy-normalized title."""
    seen_dois: set[str] = set()
    seen_external_ids: set[str] = set()
    seen_titles: set[str] = set()
    unique = []

    for art in articles:
        doi = normalize_doi(art.get("doi"))
        title_key = normalize_title(art.get("title"))
        external_ids = [
            str(art.get(k) or "").strip().lower()
            for k in ("pmid", "openalex_id", "semantic_scholar_id")
            if art.get(k)
        ]

        if doi and doi in seen_dois:
            continue
        if external_ids and any(ext in seen_external_ids for ext in external_ids):
            continue
        if _same_title(title_key, seen_titles):
            continue

        if doi:
            seen_dois.add(doi)
            art["doi"] = doi
        for ext in external_ids:
            seen_external_ids.add(ext)
        if title_key:
            seen_titles.add(title_key)

        unique.append(art)

    return unique
