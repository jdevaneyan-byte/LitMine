"""Parse the curated review master Excel into CuratedReview rows.

The Excel produced by the user contains a banner row, then columns:
    Year, Title, Journal, Theme, DOI, DOI URL, Core/Extended, Why included

We auto-detect the header row by scanning the first 10 rows for a row that
contains both 'title' and 'doi' (case-insensitive)."""

from __future__ import annotations

import io
import re
from typing import IO

import pandas as pd


CURATED_FIELDS = {"title", "doi"}


def parse_curated_excel(filename: str, raw: bytes | IO[bytes]) -> list[dict]:
    """Read the file bytes and return a list of curated-review dicts."""

    if isinstance(raw, bytes):
        buf: IO[bytes] = io.BytesIO(raw)
    else:
        buf = raw

    name = (filename or "").lower()
    if name.endswith(".xls"):
        engine = "xlrd"
    else:
        engine = "openpyxl"

    raw_df = pd.read_excel(buf, header=None, engine=engine)
    header_row = _find_header_row(raw_df)
    if header_row is None:
        raise ValueError("Could not find a header row containing 'Title' and 'DOI'.")

    # Re-read with the discovered header.
    if isinstance(raw, bytes):
        buf = io.BytesIO(raw)
    df = pd.read_excel(buf, header=header_row, engine=engine)
    df.columns = [_norm_col(c) for c in df.columns]

    rows: list[dict] = []
    for _, row in df.iterrows():
        title = _str(row.get("title"))
        doi = _clean_doi(_str(row.get("doi")))
        if not title and not doi:
            continue
        rows.append(
            {
                "title": title or f"DOI {doi}",
                "doi": doi,
                "year": _safe_int(row.get("year")),
                "journal": _str(row.get("journal")),
                "theme": _str(row.get("theme")),
                "importance": _str(row.get("core/extended") or row.get("importance")),
                "notes": _str(row.get("why included") or row.get("notes")),
                "url": _str(row.get("doi url") or row.get("url")) or (f"https://doi.org/{doi}" if doi else ""),
            }
        )
    return rows


def _find_header_row(df: pd.DataFrame, scan_rows: int = 10) -> int | None:
    for i in range(min(scan_rows, len(df))):
        cells = {str(v).strip().lower() for v in df.iloc[i].tolist() if pd.notna(v)}
        if CURATED_FIELDS.issubset(cells):
            return i
    return None


def _norm_col(value) -> str:
    return str(value or "").strip().lower()


def _str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _safe_int(value) -> int | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _clean_doi(value: str) -> str:
    s = (value or "").strip()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s, flags=re.I)
    return s.lower().rstrip(".")
