from __future__ import annotations

import csv
import io
import re


def parse_reference_upload(filename: str, raw: bytes) -> list[dict]:
    name = filename.lower()
    text = raw.decode("utf-8-sig", errors="replace")
    if name.endswith(".csv"):
        return parse_csv(text)
    if name.endswith(".bib"):
        return parse_bibtex(text)
    if name.endswith(".ris"):
        return parse_ris(text)
    return parse_doi_list(text)


def parse_csv(text: str) -> list[dict]:
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        lowered = {str(k).strip().lower(): (v or "").strip() for k, v in row.items()}
        title = _pick(lowered, "title", "article title", "name")
        if not title:
            continue
        rows.append(
            _article(
                title=title,
                authors=_pick(lowered, "authors", "author"),
                year=_parse_year(_pick(lowered, "year", "publication year")),
                doi=_clean_doi(_pick(lowered, "doi")),
                url=_pick(lowered, "url", "link"),
                abstract=_pick(lowered, "abstract"),
                source="Import",
            )
        )
    return rows


def parse_bibtex(text: str) -> list[dict]:
    rows = []
    for entry in re.split(r"\n\s*@", text):
        entry = entry if entry.startswith("@") else "@" + entry
        if "{" not in entry:
            continue
        fields = {
            key.lower(): _strip_braces(value)
            for key, value in re.findall(r"([A-Za-z]+)\s*=\s*[{'\"](.+?)[}'\"]\s*,?", entry, re.S)
        }
        title = fields.get("title", "").strip()
        if not title:
            continue
        rows.append(
            _article(
                title=title,
                authors=fields.get("author", "").replace(" and ", ", "),
                year=_parse_year(fields.get("year", "")),
                doi=_clean_doi(fields.get("doi", "")),
                url=fields.get("url", ""),
                abstract=fields.get("abstract", ""),
                source="BibTeX import",
            )
        )
    return rows


def parse_ris(text: str) -> list[dict]:
    rows = []
    current: dict[str, list[str]] = {}
    for line in text.splitlines():
        if len(line) < 6 or line[2:6] != "  - ":
            continue
        tag = line[:2]
        value = line[6:].strip()
        if tag == "TY":
            current = {}
        elif tag == "ER":
            title = _first(current, "TI", "T1")
            if title:
                rows.append(
                    _article(
                        title=title,
                        authors=", ".join(current.get("AU", [])),
                        year=_parse_year(_first(current, "PY", "Y1")),
                        doi=_clean_doi(_first(current, "DO")),
                        url=_first(current, "UR"),
                        abstract=_first(current, "AB", "N2"),
                        source="RIS import",
                    )
                )
            current = {}
        else:
            current.setdefault(tag, []).append(value)
    return rows


def parse_doi_list(text: str) -> list[dict]:
    rows = []
    seen = set()
    for match in re.finditer(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, flags=re.I):
        doi = _clean_doi(match.group(1))
        if doi in seen:
            continue
        seen.add(doi)
        rows.append(_article(title=f"DOI {doi}", doi=doi, url=f"https://doi.org/{doi}", source="DOI import"))
    return rows


def _article(
    title: str,
    authors: str = "",
    year: int | None = None,
    doi: str = "",
    url: str = "",
    abstract: str = "",
    source: str = "Import",
) -> dict:
    return {
        "title": title.strip(),
        "authors": authors.strip(),
        "year": year,
        "doi": doi.strip(),
        "url": url.strip(),
        "abstract": abstract.strip(),
        "source": source,
    }


def _pick(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        if row.get(key):
            return row[key]
    return ""


def _first(row: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = row.get(key)
        if values:
            return values[0]
    return ""


def _parse_year(value: str) -> int | None:
    match = re.search(r"(19|20)\d{2}", value or "")
    return int(match.group(0)) if match else None


def _clean_doi(value: str) -> str:
    doi = (value or "").strip().lower()
    doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    return doi.strip().rstrip(".")


def _strip_braces(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("{", "").replace("}", "")).strip()
