from concurrent.futures import ThreadPoolExecutor, as_completed
from api import arxiv, openalex, pubmed, semantic_scholar
from utils.dedup import deduplicate


def run_review_search(
    query: str,
    max_per_source: int,
    year_from: int,
    use_openalex: bool,
    use_pubmed: bool,
    use_s2: bool,
    use_arxiv: bool = False,
) -> list[dict]:
    """Search all enabled sources in parallel, return deduplicated review articles."""
    results, _errors = _run(
        query, max_per_source, year_from,
        use_openalex, use_pubmed, use_s2, use_arxiv,
        mode="reviews",
    )
    return results


def run_article_search(
    query: str,
    max_per_source: int,
    year_from: int,
    use_openalex: bool,
    use_pubmed: bool,
    use_s2: bool,
    use_arxiv: bool = False,
) -> list[dict]:
    """Search all enabled sources in parallel, return deduplicated articles."""
    results, _errors = _run(
        query, max_per_source, year_from,
        use_openalex, use_pubmed, use_s2, use_arxiv,
        mode="articles",
    )
    return results


def run_review_search_with_status(
    query: str,
    max_per_source: int,
    year_from: int,
    use_openalex: bool,
    use_pubmed: bool,
    use_s2: bool,
    use_arxiv: bool = False,
) -> tuple[list[dict], dict[str, str]]:
    return _run(query, max_per_source, year_from, use_openalex, use_pubmed, use_s2, use_arxiv, mode="reviews")


def run_article_search_with_status(
    query: str,
    max_per_source: int,
    year_from: int,
    use_openalex: bool,
    use_pubmed: bool,
    use_s2: bool,
    use_arxiv: bool = False,
) -> tuple[list[dict], dict[str, str]]:
    return _run(query, max_per_source, year_from, use_openalex, use_pubmed, use_s2, use_arxiv, mode="articles")


def run_both_search_with_status(
    query: str,
    max_per_source: int,
    year_from: int,
    use_openalex: bool,
    use_pubmed: bool,
    use_s2: bool,
    use_arxiv: bool = False,
) -> tuple[list[dict], dict[str, str]]:
    return _run(query, max_per_source, year_from, use_openalex, use_pubmed, use_s2, use_arxiv, mode="both")


def _pick(module, mode):
    """Return the right search function on a source module for the mode.
    mode is one of 'reviews', 'articles', 'both'."""
    if mode == "reviews":
        return module.search_reviews
    if mode == "both":
        return module.search_both
    return module.search_articles


def _run(query, max_per_source, year_from, use_openalex, use_pubmed, use_s2, use_arxiv, mode):
    tasks = {}
    errors = {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        if use_openalex:
            tasks["OpenAlex"] = pool.submit(_pick(openalex, mode), query, max_per_source, year_from)

        if use_pubmed:
            tasks["PubMed"] = pool.submit(_pick(pubmed, mode), query, max_per_source, year_from)

        if use_s2:
            tasks["Semantic Scholar"] = pool.submit(_pick(semantic_scholar, mode), query, max_per_source, year_from)

        if use_arxiv:
            tasks["arXiv"] = pool.submit(_pick(arxiv, mode), query, max_per_source, year_from)

        all_results = []
        for name, future in tasks.items():
            try:
                results = future.result(timeout=90)
                all_results.extend(results)
            except Exception as exc:
                errors[name] = str(exc) or "Search failed"

    return deduplicate(all_results), errors
