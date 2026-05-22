import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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
    should_cancel=None,
) -> tuple[list[dict], dict[str, str]]:
    return _run(query, max_per_source, year_from, use_openalex, use_pubmed, use_s2, use_arxiv, mode="reviews", should_cancel=should_cancel)


def run_article_search_with_status(
    query: str,
    max_per_source: int,
    year_from: int,
    use_openalex: bool,
    use_pubmed: bool,
    use_s2: bool,
    use_arxiv: bool = False,
    should_cancel=None,
) -> tuple[list[dict], dict[str, str]]:
    return _run(query, max_per_source, year_from, use_openalex, use_pubmed, use_s2, use_arxiv, mode="articles", should_cancel=should_cancel)


def run_both_search_with_status(
    query: str,
    max_per_source: int,
    year_from: int,
    use_openalex: bool,
    use_pubmed: bool,
    use_s2: bool,
    use_arxiv: bool = False,
    should_cancel=None,
) -> tuple[list[dict], dict[str, str]]:
    return _run(query, max_per_source, year_from, use_openalex, use_pubmed, use_s2, use_arxiv, mode="both", should_cancel=should_cancel)


def _pick(module, mode):
    """Return the right search function on a source module for the mode.
    mode is one of 'reviews', 'articles', 'both'."""
    if mode == "reviews":
        return module.search_reviews
    if mode == "both":
        return module.search_both
    return module.search_articles


def _run(query, max_per_source, year_from, use_openalex, use_pubmed, use_s2, use_arxiv, mode, should_cancel=None):
    """Search all enabled sources in parallel.

    `should_cancel` is an optional zero-arg callable; when it returns True we stop
    waiting immediately and return whatever has come back so far. In-flight HTTP
    calls are abandoned (the pool is shut down without waiting) so the caller can
    react to a cancel request within a fraction of a second instead of blocking on
    a slow source for up to 90s."""
    errors = {}
    all_results = []

    pool = ThreadPoolExecutor(max_workers=4)
    future_names = {}
    try:
        if use_openalex:
            future_names[pool.submit(_pick(openalex, mode), query, max_per_source, year_from)] = "OpenAlex"
        if use_pubmed:
            future_names[pool.submit(_pick(pubmed, mode), query, max_per_source, year_from)] = "PubMed"
        if use_s2:
            future_names[pool.submit(_pick(semantic_scholar, mode), query, max_per_source, year_from)] = "Semantic Scholar"
        if use_arxiv:
            future_names[pool.submit(_pick(arxiv, mode), query, max_per_source, year_from)] = "arXiv"

        pending = set(future_names)
        deadline = time.monotonic() + 90
        while pending:
            if should_cancel and should_cancel():
                break
            if time.monotonic() > deadline:
                for fut in pending:
                    errors[future_names[fut]] = "timed out"
                break
            done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
            for fut in done:
                name = future_names[fut]
                try:
                    all_results.extend(fut.result())
                except Exception as exc:
                    errors[name] = str(exc) or "Search failed"
    finally:
        # Don't block on slow/cancelled sources; abandon any still running.
        pool.shutdown(wait=False, cancel_futures=True)

    return deduplicate(all_results), errors
