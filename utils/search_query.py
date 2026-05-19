from __future__ import annotations


def build_query(
    base: str,
    required_terms: str = "",
    optional_terms: str = "",
    excluded_terms: str = "",
    search_reviews: bool = False,
) -> str:
    parts = []
    base = base.strip()
    if base:
        parts.append(_phrase(base))

    required = _terms(required_terms)
    if required:
        parts.extend(_phrase(term) for term in required)

    optional = _terms(optional_terms)
    if optional:
        parts.append("(" + " OR ".join(_phrase(term) for term in optional) + ")")

    excluded = _terms(excluded_terms)
    if excluded:
        parts.extend(f"NOT {_phrase(term)}" for term in excluded)

    if search_reviews:
        parts.append("review")

    return " ".join(parts).strip()


def _terms(raw: str) -> list[str]:
    return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]


def _phrase(term: str) -> str:
    term = term.strip()
    if " " in term and not (term.startswith('"') and term.endswith('"')):
        return f'"{term}"'
    return term
