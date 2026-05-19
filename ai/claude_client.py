import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "2500"))


def get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set. Add it to your .env file.")
    return anthropic.Anthropic(api_key=api_key)


def stream_landscape_analysis(articles: list[dict]):
    """Yield text chunks for the landscape analysis. Use with st.write_stream."""
    if not articles:
        yield "No articles to analyze."
        return

    entries = []
    for i, art in enumerate(articles[:60], 1):
        entry = f"{i}. {art['title']} ({art.get('year', 'N/A')})"
        if art.get("abstract"):
            entry += f"\n   {art['abstract'][:250]}..."
        entries.append(entry)

    articles_block = "\n\n".join(entries)

    prompt = f"""You are a research literature analyst helping a researcher plan a new review article.

Below are {len(articles)} existing review articles on the topic. Analyze them and provide a structured report.

---
## 1. Overview
Summarize what these reviews collectively cover - the scope, main subjects, and general state of the literature.

## 2. Main Themes Covered
List the key themes, subtopics, and methodological approaches already well-covered by existing reviews.

## 3. Gaps in the Literature
What important aspects, populations, methodologies, time periods, or perspectives are missing or underrepresented in existing reviews?

## 4. Opportunities for a New Review
Suggest 3-5 specific, actionable angles for a new review article that would make a genuine contribution. Be concrete - not just "more research needed" but specific proposed titles or angles.
---

EXISTING REVIEW ARTICLES:
{articles_block}"""

    client = get_client()
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def suggest_search_strategy(topic: str, title: str = "", review_type: str = ""):
    prompt = f"""You are helping design a literature search strategy.

Topic: {topic}
Working title: {title or "Not selected"}
Review type: {review_type or "Not specified"}

Return:
1. 8-12 practical search queries, one per line
2. Recommended inclusion criteria
3. Recommended exclusion criteria
4. Notes for adapting the query to PubMed, OpenAlex, and Semantic Scholar

Keep it concrete and avoid invented citations."""

    client = get_client()
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def classify_articles_relevance(articles: list[dict], topic: str) -> dict[int, bool]:
    """
    Classify each article as relevant (True) or not (False) to the given topic.
    Returns a dict mapping article id -> bool.
    Sends articles in batches of 80 to stay within token limits.
    """
    if not articles:
        return {}

    client = get_client()
    results: dict[int, bool] = {}

    batch_size = 80
    for batch_start in range(0, len(articles), batch_size):
        batch = articles[batch_start : batch_start + batch_size]

        lines = []
        for art in batch:
            abstract_snippet = ""
            if art.get("abstract"):
                abstract_snippet = " | " + art["abstract"][:150]
            lines.append(f"ID:{art['id']} | {art['title']} ({art.get('year', '')}){abstract_snippet}")

        prompt = f"""You are helping filter a literature database for a research review on:
"{topic}"

For each article below, decide if it is DIRECTLY relevant to that topic (True) or not relevant (False).
Only mark True if the article is clearly about the core chemistry/science of the topic.
Respond with ONLY lines in this exact format - one per article, nothing else:
ID:<number>:<True/False>

ARTICLES:
{chr(10).join(lines)}"""

        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("ID:"):
                continue
            parts = line[3:].split(":")
            if len(parts) == 2:
                try:
                    art_id = int(parts[0])
                    relevant = parts[1].strip().lower() == "true"
                    results[art_id] = relevant
                except ValueError:
                    pass

    return results


def stream_relevance_filter(articles: list[dict], topic: str):
    """
    Stream progress updates while classifying articles.
    Yields markdown strings for the UI. Final yield is a JSON summary line.
    """
    import json

    if not articles:
        yield "No articles to filter."
        return

    client = get_client()
    all_results: dict[int, bool] = {}
    batch_size = 80
    total_batches = (len(articles) + batch_size - 1) // batch_size

    yield f"Classifying **{len(articles)} articles** in {total_batches} batch(es)...\n\n"

    for batch_num, batch_start in enumerate(range(0, len(articles), batch_size), 1):
        batch = articles[batch_start : batch_start + batch_size]

        lines = []
        for art in batch:
            abstract_snippet = ""
            if art.get("abstract"):
                abstract_snippet = " | " + art["abstract"][:150]
            lines.append(f"ID:{art['id']} | {art['title']} ({art.get('year', '')}){abstract_snippet}")

        prompt = f"""You are helping filter a literature database for a research review on:
"{topic}"

For each article below, decide if it is DIRECTLY relevant to that topic (True) or not relevant (False).
Only mark True if the article is clearly about the core chemistry/science of the topic.
Respond with ONLY lines in this exact format - one per article, nothing else:
ID:<number>:<True/False>

ARTICLES:
{chr(10).join(lines)}"""

        yield f"**Batch {batch_num}/{total_batches}** ({len(batch)} articles)...\n"

        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        batch_keep = 0
        batch_remove = 0
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("ID:"):
                continue
            parts = line[3:].split(":")
            if len(parts) == 2:
                try:
                    art_id = int(parts[0])
                    relevant = parts[1].strip().lower() == "true"
                    all_results[art_id] = relevant
                    if relevant:
                        batch_keep += 1
                    else:
                        batch_remove += 1
                except ValueError:
                    pass

        yield f"  -> Keep: **{batch_keep}** | Remove: **{batch_remove}**\n\n"

    kept = sum(1 for v in all_results.values() if v)
    removed = sum(1 for v in all_results.values() if not v)
    yield f"\n---\n**Filter complete** - {kept} relevant / {removed} not relevant out of {len(articles)} total.\n"
    yield f"\n```json\n{json.dumps(all_results)}\n```\n"
