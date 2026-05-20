"""arXiv search via the public Atom API.

No auth required. Polite rate-limit is 1 request per 3 seconds (we comply).
arXiv covers physics, math, CS, quantitative biology, statistics, finance, EE.
DOIs are filled in when arXiv has them; many preprints have none until
published in a journal.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Optional

import requests

BASE_URL = "http://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def search_articles(
    topic: str, max_results: int = 100, year_from: Optional[int] = None
) -> list[dict]:
    return _search(topic, max_results, year_from, review_only=False)


def search_reviews(
    topic: str, max_results: int = 50, year_from: Optional[int] = None
) -> list[dict]:
    # arXiv has no "review" publication type. We coarse-filter on the title.
    return _search(topic, max_results, year_from, review_only=True)


def search_both(
    topic: str, max_results: int = 100, year_from: Optional[int] = None
) -> list[dict]:
    # arXiv items are all preprints; "both" is the same as the article search.
    return _search(topic, max_results, year_from, review_only=False)


def _search(
    topic: str, max_results: int, year_from: Optional[int], review_only: bool
) -> list[dict]:
    if not topic.strip():
        return []
    # arXiv "all:" matches title + abstract + authors + comment.
    params = {
        "search_query": f"all:{topic}",
        "start": 0,
        "max_results": min(max(max_results, 1), 200),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    last_err = None
    for attempt in range(4):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=60)
            if resp.status_code == 429:
                # Rate-limited; back off and retry with growing delay.
                time.sleep(5.0 * (attempt + 1))
                last_err = RuntimeError("arXiv 429 rate-limited")
                continue
            resp.raise_for_status()
            last_err = None
            break
        except requests.exceptions.Timeout as exc:
            last_err = exc
            time.sleep(5.0)
        except Exception as exc:
            raise RuntimeError(f"arXiv search failed: {exc}") from exc
    if last_err is not None:
        raise RuntimeError(f"arXiv search failed after retries: {last_err}") from last_err

    # Polite back-off between calls (per arXiv API guidance: 1 req / 3 sec).
    time.sleep(3.0)

    results: list[dict] = []
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return []

    for entry in root.findall("a:entry", NS):
        parsed = _parse_entry(entry)
        if not parsed["title"]:
            continue
        if year_from and parsed["year"] and parsed["year"] < year_from:
            continue
        if review_only and not _looks_like_review(parsed["title"]):
            continue
        results.append(parsed)
    return results


def _parse_entry(entry: ET.Element) -> dict:
    title = _text(entry.find("a:title", NS))
    summary = _text(entry.find("a:summary", NS))
    published = _text(entry.find("a:published", NS))
    year = None
    if published and len(published) >= 4 and published[:4].isdigit():
        year = int(published[:4])

    authors = []
    for a in entry.findall("a:author", NS):
        name = _text(a.find("a:name", NS))
        if name:
            authors.append(name)
    authors_str = ", ".join(authors[:5])
    if len(authors) > 5:
        authors_str += " et al."

    # arXiv ID lives in the <id> element: http://arxiv.org/abs/2401.12345v1
    arxiv_url = _text(entry.find("a:id", NS))
    # DOI may appear in <arxiv:doi>.
    doi_el = entry.find("arxiv:doi", NS)
    doi = doi_el.text.strip() if (doi_el is not None and doi_el.text) else ""

    return {
        "title": title,
        "doi": doi,
        "abstract": summary,
        "authors": authors_str,
        "year": year,
        "source": "arXiv",
        "url": arxiv_url,
        "pub_type": "Preprint",
    }


def _text(node: Optional[ET.Element]) -> str:
    if node is None or node.text is None:
        return ""
    return " ".join(node.text.split())


_REVIEW_HINTS = ("review", "advances", "overview", "perspective", "survey", "tutorial")


def _looks_like_review(title: str) -> bool:
    t = (title or "").lower()
    return any(h in t for h in _REVIEW_HINTS)
