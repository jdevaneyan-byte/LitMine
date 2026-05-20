"""Excel (xlsx) export with proper formatting.

Each row is one article (or cited reference). Columns are tuned for readability:
- Bold header with light-grey fill
- Frozen first row + auto-filter (so columns sort/filter in Excel)
- Sensible column widths
- Long fields (Title, Authors, Abstract) wrap inside the cell
- Hyperlinked DOI column
"""

from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# Per-column display widths (in Excel character units).
COLUMN_WIDTHS = {
    "#": 6,
    "ID": 6,
    "Year": 8,
    "Source": 16,
    "Status": 14,
    "Is Review": 10,
    "Decision": 14,
    "Tags": 18,
    "Venue": 26,
    "Authors": 36,
    "DOI": 30,
    "URL": 30,
    "Title": 60,
    "Abstract": 80,
    "Notes": 30,
    "Rejected Reason": 24,
    "Publication Types": 18,
    "Review ID": 8,
}
DEFAULT_WIDTH = 20
WRAP_COLUMNS = {"Title", "Authors", "Abstract", "Notes", "Rejected Reason"}


def rows_to_excel(rows: list[dict], sheet_name: str = "Articles") -> bytes:
    """Convert a list of dict rows to a formatted xlsx (returned as bytes)."""

    if not rows:
        rows = [{"(empty)": ""}]

    df = pd.DataFrame(rows)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name[:31] or "Sheet1", index=False)
        ws = writer.sheets[sheet_name[:31] or "Sheet1"]

        header_fill = PatternFill("solid", fgColor="EEEEEE")
        header_font = Font(bold=True)
        center = Alignment(vertical="center", wrap_text=False)
        wrap = Alignment(vertical="top", wrap_text=True)

        # Style header row.
        for col_idx, col_name in enumerate(df.columns, start=1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
            letter = get_column_letter(col_idx)
            ws.column_dimensions[letter].width = COLUMN_WIDTHS.get(str(col_name), DEFAULT_WIDTH)

        # Wrap long text columns + a sensible row height that doesn't expand to 200pt.
        for col_idx, col_name in enumerate(df.columns, start=1):
            if str(col_name) in WRAP_COLUMNS:
                for row_idx in range(2, len(df) + 2):
                    ws.cell(row=row_idx, column=col_idx).alignment = wrap

        # Freeze header + add auto-filter so user can sort/filter inside Excel.
        ws.freeze_panes = "A2"
        last_col = get_column_letter(len(df.columns))
        ws.auto_filter.ref = f"A1:{last_col}{len(df) + 1}"

        # Cap row height so cells stay manageable; user can expand any row by clicking.
        ws.sheet_format.defaultRowHeight = 18

    return buf.getvalue()


def articles_to_excel(articles: list, include_serial: bool = True) -> bytes:
    """Format CollectedArticle / LandscapeArticle rows for Excel download."""

    rows = []
    for idx, a in enumerate(articles, start=1):
        row = {}
        if include_serial:
            row["#"] = idx
        row.update(
            {
                "Title": _str(a.title),
                "Authors": _str(a.authors),
                "Year": a.year or "",
                "Source": _str(a.source),
                "DOI": _str(a.doi),
                "DOI URL": f"https://doi.org/{a.doi}" if a.doi else "",
                "URL": _str(a.url),
                "Abstract": _str(a.abstract),
                "Tags": _str(getattr(a, "tags", "")),
                "Notes": _str(getattr(a, "notes", "")),
                "Decision": _str(getattr(a, "decision", "")) or _str(getattr(a, "screening_status", "")),
                "Decision Reason": _str(getattr(a, "decision_reason", "")),
                "PDF Path": _str(getattr(a, "pdf_path", "")),
                "ID": a.id,
            }
        )
        rows.append(row)
    return rows_to_excel(rows, sheet_name="Articles")


def cited_articles_to_excel(cited: list, include_serial: bool = True) -> bytes:
    """Format CitedArticle rows for Excel download."""

    rows = []
    for idx, a in enumerate(cited, start=1):
        row = {}
        if include_serial:
            row["#"] = idx
        row.update(
            {
                "Title": _str(a.title),
                "Authors": _str(a.authors),
                "Year": a.year or "",
                "Venue": _str(a.venue),
                "DOI": _str(a.doi),
                "DOI URL": f"https://doi.org/{a.doi}" if a.doi else "",
                "URL": _str(a.url),
                "Abstract": _str(a.abstract),
                "Is Review": "Yes" if a.is_review else "",
                "Is Book": "Yes" if getattr(a, "is_book", False) else "",
                "Publication Types": _str(a.publication_types),
                "Status": _str(a.status),
                "Rejected Reason": _str(a.rejected_reason),
                "Source": _str(a.source),
                "Review ID": a.curated_review_id,
                "ID": a.id,
            }
        )
        rows.append(row)
    return rows_to_excel(rows, sheet_name="Cited Articles")


def filename_for(project_name: str, suffix: str, ext: str = "xlsx") -> str:
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in (project_name or "project")).strip() or "project"
    stamp = datetime.now().strftime("%Y%m%d")
    return f"{safe}_{suffix}_{stamp}.{ext}"


def _str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()
