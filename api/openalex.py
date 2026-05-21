import os
import requests
import time
from typing import Optional

BASE_URL = "https://api.openalex.org"
MAILTO = "research@litmine.app"
FIELDS = "title,doi,abstract_inverted_index,authorships,publication_year,primary_location,id,type,cited_by_count,referenced_works"


def _auth_params() -> dict:
    """OpenAlex requires an API key since Feb 2026 (the mailto polite pool was
    retired). Send the key when configured; fall back to mailto otherwise."""
    key = os.getenv("OPENALEX_API_KEY", "").strip()
    return {"api_key": key} if key else {"mailto": MAILTO}


def _reconstruct_abstract(inverted_index: Optional[dict]) -> str:
    if not inverted_index:
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words.keys()))


def _parse_work(work: dict) -> dict:
    title = work.get("title") or ""

    doi = work.get("doi", "") or ""
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

    authorships = work.get("authorships", [])
    authors = [
        a.get("author", {}).get("display_name", "")
        for a in authorships[:5]
        if a.get("author", {}).get("display_name")
    ]
    authors_str = ", ".join(authors)
    if len(authorships) > 5:
        authors_str += " et al."

    year = work.get("publication_year")

    loc = work.get("primary_location") or {}
    url = loc.get("landing_page_url") or work.get("id", "")
    source_obj = loc.get("source") or {}
    venue = source_obj.get("display_name") or ""

    oa_id = (work.get("id") or "").rsplit("/", 1)[-1] if work.get("id") else ""
    referenced = work.get("referenced_works") or []
    return {
        "title": title,
        "doi": doi,
        "abstract": abstract,
        "authors": authors_str,
        "year": year,
        "source": "OpenAlex",
        "url": url,
        "pub_type": work.get("type") or "",
        "citation_count": work.get("cited_by_count"),
        "venue": venue,
        "openalex_id": oa_id,
        "referenced_ids": [r.rsplit("/", 1)[-1] for r in referenced],
    }


def search_reviews(
    topic: str, max_results: int = 50, year_from: Optional[int] = None
) -> list[dict]:
    filters = "type:review"
    if year_from:
        filters += f",publication_year:>{year_from - 1}"
    return _fetch(topic, filters, max_results)


def search_articles(
    topic: str, max_results: int = 100, year_from: Optional[int] = None
) -> list[dict]:
    filters = "type:article"
    if year_from:
        filters += f",publication_year:>{year_from - 1}"
    return _fetch(topic, filters, max_results)


def search_both(
    topic: str, max_results: int = 100, year_from: Optional[int] = None
) -> list[dict]:
    """Research articles and reviews together. OpenAlex treats 'review' as a
    distinct type from 'article', so searching 'article' alone silently drops
    reviews; the pipe is OpenAlex's OR operator within a filter key."""
    filters = "type:article|review"
    if year_from:
        filters += f",publication_year:>{year_from - 1}"
    return _fetch(topic, filters, max_results)


def _fetch(topic: str, filters: str, max_results: int) -> list[dict]:
    results = []
    page = 1
    per_page = min(max_results, 200)

    while len(results) < max_results:
        try:
            resp = requests.get(
                f"{BASE_URL}/works",
                params={
                    "search": topic,
                    "filter": filters,
                    "per-page": per_page,
                    "page": page,
                    "select": FIELDS,
                    **_auth_params(),
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"OpenAlex request failed: {exc}") from exc

        works = data.get("results", [])
        if not works:
            break

        for work in works:
            parsed = _parse_work(work)
            if parsed["title"]:
                results.append(parsed)
            if len(results) >= max_results:
                break

        if len(works) < per_page:
            break

        page += 1
        time.sleep(0.1)

    return results
