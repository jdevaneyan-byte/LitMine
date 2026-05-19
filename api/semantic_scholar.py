import os
import requests
import time
from typing import Optional

BASE_URL = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,abstract,year,authors,externalIds,url,publicationTypes"


def _headers() -> dict:
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    return {"x-api-key": key} if key else {}


def search_reviews(
    topic: str, max_results: int = 50, year_from: Optional[int] = None
) -> list[dict]:
    return _search(topic, max_results, year_from, review_only=True)


def search_articles(
    topic: str, max_results: int = 100, year_from: Optional[int] = None
) -> list[dict]:
    return _search(topic, max_results, year_from, review_only=False)


def _search(
    topic: str, max_results: int, year_from: Optional[int], review_only: bool
) -> list[dict]:
    results = []
    offset = 0
    limit = min(100, max_results)

    while len(results) < max_results:
        params: dict = {
            "query": topic,
            "fields": FIELDS,
            "limit": limit,
            "offset": offset,
        }
        if review_only:
            params["publicationTypes"] = "Review"
        if year_from:
            params["year"] = f"{year_from}-"

        try:
            resp = requests.get(
                f"{BASE_URL}/paper/search",
                params=params,
                headers=_headers(),
                timeout=30,
            )
            if resp.status_code == 429:
                time.sleep(3)
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Semantic Scholar request failed: {exc}") from exc

        papers = data.get("data", [])
        if not papers:
            break

        for paper in papers:
            parsed = _parse_paper(paper)
            if parsed["title"]:
                results.append(parsed)
            if len(results) >= max_results:
                break

        if len(papers) < limit:
            break

        offset += limit
        time.sleep(0.5)

    return results


def _parse_paper(paper: dict) -> dict:
    title = paper.get("title") or ""
    abstract = paper.get("abstract") or ""
    year = paper.get("year")

    all_authors = paper.get("authors", [])
    authors = [a.get("name", "") for a in all_authors[:5] if a.get("name")]
    authors_str = ", ".join(authors)
    if len(all_authors) > 5:
        authors_str += " et al."

    ext = paper.get("externalIds") or {}
    doi = ext.get("DOI", "")

    url = paper.get("url") or ""
    if not url and ext.get("PubMed"):
        url = f"https://pubmed.ncbi.nlm.nih.gov/{ext['PubMed']}/"

    return {
        "title": title,
        "doi": doi,
        "abstract": abstract,
        "authors": authors_str,
        "year": year,
        "source": "Semantic Scholar",
        "url": url,
    }
