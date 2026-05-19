import json
import pandas as pd


def articles_to_csv(articles: list) -> str:
    if not articles:
        return ""

    rows = [
        {
            "Title": a.title,
            "Authors": a.authors,
            "Year": a.year or "",
            "DOI": a.doi or "",
            "DOI URL": f"https://doi.org/{a.doi}" if a.doi else "",
            "URL": a.url or "",
            "Abstract": a.abstract or "",
            "Source": a.source,
            "Notes": getattr(a, "notes", "") or "",
            "Tags": getattr(a, "tags", "") or "",
            "Screening Status": getattr(a, "screening_status", "") or getattr(a, "decision", "") or "",
            "Decision Reason": getattr(a, "decision_reason", "") or "",
            "PDF Path": getattr(a, "pdf_path", "") or "",
        }
        for a in articles
    ]
    return pd.DataFrame(rows).to_csv(index=False)


def articles_to_bibtex(articles: list) -> str:
    entries = []
    for art in articles:
        first_author = (
            (art.authors or "Unknown").split(",")[0].strip().split()[-1]
        )
        year = art.year or "0000"
        title_word = (art.title or "unknown").split()[0].lower()
        key = "".join(c for c in f"{first_author}{year}{title_word}" if c.isalnum())

        lines = [f"@article{{{key},"]
        lines.append(f"  title = {{{_bib_escape(art.title)}}},")
        if art.authors:
            lines.append(f"  author = {{{_bib_escape(art.authors)}}},")
        if art.year:
            lines.append(f"  year = {{{art.year}}},")
        if art.doi:
            lines.append(f"  doi = {{{art.doi}}},")
        if art.url:
            lines.append(f"  url = {{{art.url}}},")
        if art.abstract:
            lines.append(f"  abstract = {{{_bib_escape((art.abstract or '')[:500])}}},")
        lines.append("}")
        entries.append("\n".join(lines))

    return "\n\n".join(entries)


def articles_to_ris(articles: list) -> str:
    entries = []
    for art in articles:
        lines = ["TY  - JOUR"]
        if art.title:
            lines.append(f"TI  - {art.title}")
        for author in _split_authors(art.authors or ""):
            lines.append(f"AU  - {author}")
        if art.year:
            lines.append(f"PY  - {art.year}")
        if art.doi:
            lines.append(f"DO  - {art.doi}")
        if art.url:
            lines.append(f"UR  - {art.url}")
        if art.abstract:
            lines.append(f"AB  - {art.abstract}")
        if getattr(art, "notes", ""):
            lines.append(f"N1  - {art.notes}")
        lines.append("ER  -")
        entries.append("\n".join(lines))
    return "\n\n".join(entries)


def articles_to_json(articles: list, include_relevance: bool = False) -> str:
    rows = []
    for a in articles:
        row = {
            "id": a.id,
            "title": a.title,
            "authors": a.authors or "",
            "year": a.year,
            "doi": a.doi or "",
            "url": a.url or "",
            "abstract": a.abstract or "",
            "source": a.source,
            "notes": getattr(a, "notes", "") or "",
            "tags": getattr(a, "tags", "") or "",
            "screening_status": getattr(a, "screening_status", "") or getattr(a, "decision", "") or "",
            "decision_reason": getattr(a, "decision_reason", "") or "",
            "pdf_path": getattr(a, "pdf_path", "") or "",
        }
        if include_relevance and hasattr(a, "is_relevant"):
            row["is_relevant"] = a.is_relevant
        rows.append(row)
    return json.dumps(rows, indent=2, ensure_ascii=False)


def project_report(project, landscape_articles: list, collected_articles: list) -> str:
    status_counts: dict[str, int] = {}
    for article in collected_articles:
        status = getattr(article, "screening_status", "") or "identified"
        status_counts[status] = status_counts.get(status, 0) + 1

    lines = [
        f"# {project.name}",
        "",
        f"Topic: {project.topic}",
        f"Review title: {project.chosen_title or 'Not selected'}",
        f"Review type: {getattr(project, 'review_type', '') or 'Not set'}",
        "",
        "## Criteria",
        "",
        f"Inclusion: {getattr(project, 'inclusion_criteria', '') or 'Not set'}",
        "",
        f"Exclusion: {getattr(project, 'exclusion_criteria', '') or 'Not set'}",
        "",
        "## Search Strategy",
        "",
        getattr(project, "search_strategy", "") or "No saved search strategy.",
        "",
        "## Counts",
        "",
        f"Landscape review records: {len(landscape_articles)}",
        f"Collected article records: {len(collected_articles)}",
    ]

    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")

    lines.extend(["", "## Collected Articles", ""])
    for i, art in enumerate(collected_articles, 1):
        bits = [str(art.year) if art.year else "n.d.", art.source or "unknown source"]
        if art.doi:
            bits.append(f"doi:{art.doi}")
        lines.extend([
            f"{i}. {art.title}",
            f"   {' | '.join(bits)}",
        ])
        if getattr(art, "notes", ""):
            lines.append(f"   Notes: {art.notes}")
    return "\n".join(lines)


def _bib_escape(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _split_authors(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.replace(" and ", ",").split(",") if part.strip() and part.strip() != "et al."]
