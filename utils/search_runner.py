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


def _run(query, max_per_source, year_from, use_openalex, use_pubmed, use_s2, use_arxiv, mode):
    tasks = {}
    errors = {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        if use_openalex:
            fn = openalex.search_reviews if mode == "reviews" else openalex.search_articles
            tasks["OpenAlex"] = pool.submit(fn, query, max_per_source, year_from)

        if use_pubmed:
            fn = pubmed.search_reviews if mode == "reviews" else pubmed.search_articles
            tasks["PubMed"] = pool.submit(fn, query, max_per_source, year_from)

        if use_s2:
            fn = semantic_scholar.search_reviews if mode == "reviews" else semantic_scholar.search_articles
            tasks["Semantic Scholar"] = pool.submit(fn, query, max_per_source, year_from)

        if use_arxiv:
            fn = arxiv.search_reviews if mode == "reviews" else arxiv.search_articles
            tasks["arXiv"] = pool.submit(fn, query, max_per_source, year_from)

        all_results = []
        for name, future in tasks.items():
            try:
                results = future.result(timeout=90)
                all_results.extend(results)
            except Exception as exc:
                errors[name] = str(exc) or "Search failed"

    return deduplicate(all_results), errors
