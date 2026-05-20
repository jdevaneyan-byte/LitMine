"""Normalize the many per-source publication-type strings into one small,
user-facing taxonomy. Sources disagree (OpenAlex `article`, Semantic Scholar
`JournalArticle`, PubMed `Journal Article`, arXiv preprints, etc.) and often
omit the type entirely — those land in "Unclassified".
"""

from __future__ import annotations

CATEGORIES = [
    "Review",
    "Research article",
    "Conference",
    "Book/Chapter",
    "Preprint",
    "Editorial/Note",
    "Dataset",
    "Unclassified",
]


def categorize(pub_type: str | None, source: str | None = "", title: str | None = "") -> str:
    src = (source or "").strip().lower()
    t = (pub_type or "").strip().lower()

    # arXiv (and other preprint servers) are preprints regardless of label.
    if src == "arxiv":
        return "Preprint"

    if not t:
        return "Unclassified"

    # Order matters: check the more specific buckets first.
    if "review" in t or "meta-analysis" in t or "metaanalysis" in t:
        return "Review"
    if any(k in t for k in ("preprint", "posted-content", "posted content")):
        return "Preprint"
    if any(k in t for k in ("book", "monograph", "chapter")):
        return "Book/Chapter"
    if any(k in t for k in ("conference", "proceedings")):
        return "Conference"
    if any(k in t for k in ("editorial", "letter", "comment", "news", "note", "erratum", "correction")):
        return "Editorial/Note"
    if "dataset" in t:
        return "Dataset"
    if any(k in t for k in ("journalarticle", "journal article", "article", "study", "clinicaltrial",
                            "clinical trial", "casereport", "case report", "research")):
        return "Research article"
    return "Unclassified"
