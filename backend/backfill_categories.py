"""Backfill the normalized `category` for existing library rows from their
already-stored raw `pub_type` + source. Pure local computation — no network.

Run from the project root:
    python -m backend.backfill_categories
"""

from __future__ import annotations

from database import CollectedArticle, init_db, new_session
from utils.pub_category import categorize


def backfill() -> None:
    init_db()
    session = new_session()
    try:
        rows = (
            session.query(CollectedArticle)
            .filter((CollectedArticle.category == "") | (CollectedArticle.category == None))  # noqa: E711
            .all()
        )
        n = 0
        for a in rows:
            a.category = categorize(a.pub_type, a.source, a.title)
            n += 1
        session.commit()
        print(f"Categorized {n} rows.")
    finally:
        session.close()


if __name__ == "__main__":
    backfill()
