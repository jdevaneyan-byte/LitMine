"""Workspace — one page for everything you do inside a project.

Sections (chosen via the top selector):
    1. Search the web     — query OpenAlex / PubMed / Semantic Scholar
    2. Import my list     — upload an Excel / CSV / BibTeX / RIS / DOI list
    3. Extract citations  — for review papers in your library, fetch their cited refs
    4. Library            — browse, screen, decide, download
    5. Project settings   — name / type / topic / delete

Designed so a first-time visitor can read the screen top-to-bottom and know
what each control does. All non-obvious widgets have a tooltip.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import func

from database import (
    CitedArticle,
    CollectedArticle,
    CuratedReview,
    Project,
    init_db,
    new_session,
)
from utils.excel_export import (
    articles_to_excel,
    cited_articles_to_excel,
    filename_for,
    rows_to_excel,
)
from utils.excel_import import parse_curated_excel
from utils.find_duplicates import find_clusters, merge_all_clusters, merge_into, pick_keeper
from utils.extract_job import (
    clear_job as clear_extract_job,
    find_active_job as find_active_extract_job,
    get_status as get_extract_status,
    request_cancel as request_cancel_extract,
    start_extract_job,
)
from utils.import_refs import parse_reference_upload
from utils.keybinds import bind_keys
from utils.queue_store import load_queues, save_ca_queue
from utils.search_job import (
    clear_job as clear_search_job,
    find_active_job as find_active_search_job,
    get_status as get_search_status,
    request_cancel as request_cancel_search,
    start_job as start_search_job,
)

st.set_page_config(page_title="Workspace · LitMine", page_icon="LM", layout="wide")
init_db()

PAGE_SIZE = 50
DECISIONS = ["unscreened", "include", "maybe", "exclude"]
# Values that all mean "not yet screened" (historical rows used these).
UNSCREENED_VALUES = (None, "", "unscreened", "identified")


def _unscreened_clause():
    """SQLAlchemy clause matching any not-yet-screened representation."""
    return CollectedArticle.screening_status.in_([v for v in UNSCREENED_VALUES if v is not None]) | (
        CollectedArticle.screening_status == None  # noqa: E711
    )
EXCLUSION_REASONS = [
    "Off-topic",
    "Wrong study type",
    "Wrong publication type",
    "Not original research",
    "Insufficient methods",
    "Duplicate",
    "No abstract / no full text",
    "Out of date range",
    "Wrong language",
    "Other (specify below)",
]


# Sidebar — project picker

st.sidebar.title("LitMine")
st.sidebar.markdown("---")

session = new_session()
try:
    projects = session.query(Project).order_by(Project.created_at.desc()).all()
    project_map = {p.id: p.name for p in projects}
finally:
    session.close()

if not project_map:
    st.warning("No projects found. Create one on the Home page first.")
    st.stop()

active_id = st.session_state.get("active_project_id")
if active_id not in project_map:
    active_id = list(project_map.keys())[0]
    st.session_state.active_project_id = active_id

selected_id = st.sidebar.selectbox(
    "Active project",
    options=list(project_map.keys()),
    format_func=lambda x: project_map[x],
    index=list(project_map.keys()).index(active_id),
    help="Switch between your projects.",
)
st.session_state.active_project_id = selected_id


# Project header

session = new_session()
try:
    project = session.get(Project, selected_id)
    project_name = project.name
    project_topic = project.topic or ""
    project_description = project.description or ""
    literature_type = project.literature_type or "Review + research articles"
    library_count = session.query(CollectedArticle).filter_by(project_id=selected_id).count()
    curated_count = session.query(CuratedReview).filter_by(project_id=selected_id).count()
    cited_count = session.query(CitedArticle).filter_by(project_id=selected_id).count()
finally:
    session.close()

st.title(project_name)
st.caption(
    f"Looking for: **{literature_type}** &nbsp; · &nbsp; "
    f"Topic: `{project_topic}` &nbsp; · &nbsp; "
    f"📚 Library: **{library_count}** &nbsp; · &nbsp; "
    f"📑 Curated reviews: **{curated_count}** &nbsp; · &nbsp; "
    f"🔗 Cited refs: **{cited_count}**"
)
st.markdown("---")


# Section picker

SECTIONS = [
    "📚 Library",
    "🔍 Search the web",
    "📥 Import my list",
    "🔗 Extract citations from reviews",
    "⚙ Project settings",
]
section = st.radio(
    "What do you want to do?",
    SECTIONS,
    horizontal=True,
    key="ws_section",
    help=(
        "**Library** — browse, screen, and download everything you've collected.\n\n"
        "**Search the web** — query OpenAlex, PubMed and Semantic Scholar for papers.\n\n"
        "**Import my list** — upload your own Excel / CSV / BibTeX / RIS file.\n\n"
        "**Extract citations** — for review papers, fetch the references they cite.\n\n"
        "**Project settings** — rename, change type, or delete this project."
    ),
)
st.markdown("---")


# Helpers


def parse_keywords(raw: str) -> list[str]:
    return [p.strip().lower() for p in (raw or "").replace("\n", ",").split(",") if p.strip()]


def title_matches(title: str, keywords: list[str], mode: str) -> bool:
    if not keywords:
        return True
    title_l = (title or "").lower()
    if mode == "all":
        return all(k in title_l for k in keywords)
    return any(k in title_l for k in keywords)


def save_to_library(
    results: list[dict],
    project_id: int,
    title_keyword: str = "",
    title_match_mode: str = "any",
    imported_from: str = "",
) -> tuple[int, int]:
    session = new_session()
    try:
        existing_dois = {
            (a.doi or "").lower()
            for a in session.query(CollectedArticle).filter_by(project_id=project_id).all()
            if a.doi
        }
        existing_titles = {
            (a.title or "").strip().lower()
            for a in session.query(CollectedArticle).filter_by(project_id=project_id).all()
        }
        keywords = parse_keywords(title_keyword)
        added = 0
        skipped_kw = 0
        for art in results:
            title = (art.get("title") or "").strip()
            if not title:
                continue
            if not title_matches(title, keywords, title_match_mode):
                skipped_kw += 1
                continue
            doi_l = (art.get("doi") or "").lower()
            title_l = title.lower()
            if doi_l and doi_l in existing_dois:
                continue
            if title_l in existing_titles:
                continue
            session.add(
                CollectedArticle(
                    project_id=project_id,
                    title=title,
                    doi=art.get("doi", ""),
                    abstract=art.get("abstract", ""),
                    authors=art.get("authors", ""),
                    year=art.get("year"),
                    source=imported_from or art.get("source", "Import"),
                    url=art.get("url", ""),
                    pub_type=art.get("pub_type", ""),
                    venue=art.get("venue", ""),
                    citation_count=art.get("citation_count"),
                    screening_status="unscreened",
                    imported_from=imported_from,
                )
            )
            added += 1
            existing_titles.add(title_l)
            if doi_l:
                existing_dois.add(doi_l)
        session.commit()
        return added, skipped_kw
    finally:
        session.close()


def import_curated_reviews(project_id: int, rows: list[dict], replace: bool) -> tuple[int, int]:
    session = new_session()
    try:
        replaced = 0
        if replace:
            replaced = session.query(CuratedReview).filter_by(project_id=project_id).count()
            session.query(CitedArticle).filter_by(project_id=project_id).delete(synchronize_session=False)
            session.query(CuratedReview).filter_by(project_id=project_id).delete(synchronize_session=False)
            session.flush()
        existing_dois = {
            (r.doi or "").lower()
            for r in session.query(CuratedReview).filter_by(project_id=project_id).all()
            if r.doi
        }
        added = 0
        for row in rows:
            doi_l = (row.get("doi") or "").lower()
            if doi_l and doi_l in existing_dois:
                continue
            session.add(
                CuratedReview(
                    project_id=project_id,
                    title=row.get("title") or "",
                    doi=row.get("doi") or "",
                    year=row.get("year"),
                    journal=row.get("journal") or "",
                    theme=row.get("theme") or "",
                    importance=row.get("importance") or "",
                    notes=row.get("notes") or "",
                    url=row.get("url") or "",
                    imported_from="excel",
                    extraction_status="pending",
                )
            )
            if doi_l:
                existing_dois.add(doi_l)
            added += 1
        session.commit()
        return added, replaced
    finally:
        session.close()


def derive_search_mode(literature_type: str, override: str) -> str:
    """Return 'reviews', 'articles', or 'both' for the search runner."""
    if override == "Research articles":
        return "articles"
    if override == "Review articles":
        return "reviews"
    if literature_type == "Review articles":
        return "reviews"
    if literature_type == "Research articles":
        return "articles"
    return "both"  # default → research articles + reviews across all sources.


# Section 1: Library

if section == "📚 Library":
    st.markdown("### Your library")
    st.caption(
        "Everything you've collected for this project. Filter, screen, and download as Excel. "
        "Click any row in the table to see the abstract and edit screening status."
    )

    if library_count == 0:
        st.info(
            "Nothing in the library yet. Pick **🔍 Search the web** or **📥 Import my list** above to add papers."
        )
        st.stop()

    # PRISMA-style flow numbers — read counts by decision and render a
    # left-to-right strip of metrics so the screening pipeline is visible
    # at a glance.
    session = new_session()
    try:
        total_in = session.query(CollectedArticle).filter_by(project_id=selected_id).count()
        n_unscreened = (
            session.query(CollectedArticle)
            .filter_by(project_id=selected_id)
            .filter(_unscreened_clause())
            .count()
        )
        n_include = session.query(CollectedArticle).filter_by(project_id=selected_id, screening_status="include").count()
        n_maybe = session.query(CollectedArticle).filter_by(project_id=selected_id, screening_status="maybe").count()
        n_exclude = session.query(CollectedArticle).filter_by(project_id=selected_id, screening_status="exclude").count()
    finally:
        session.close()

    n_screened = total_in - n_unscreened
    pct_screened = (n_screened / total_in * 100) if total_in else 0

    st.markdown("#### Screening progress (PRISMA-style)")
    pcols = st.columns(5)
    pcols[0].metric("Identified", total_in, help="Total papers collected for this project.")
    pcols[1].metric(
        "Screened", f"{n_screened} ({pct_screened:.0f}%)",
        help="Papers with any manual decision (include / maybe / exclude).",
    )
    pcols[2].metric("Included", n_include, help="Papers you marked to include.")
    pcols[3].metric("Maybe", n_maybe, help="Papers you're undecided on.")
    pcols[4].metric("Excluded", n_exclude, help="Papers you've excluded.")
    if total_in:
        st.progress(n_screened / total_in, text=f"{n_screened} / {total_in} papers screened")
    st.markdown("---")

    # Filters
    fc1, fc2, fc3, fc4 = st.columns([2, 1, 1, 2])
    with fc1:
        filter_kw = st.text_input(
            "Filter by keyword in title",
            key="lib_filter",
            placeholder="e.g. amide",
            help="Case-insensitive substring match on the article title.",
        )
    with fc2:
        decision_filter = st.selectbox(
            "Decision",
            ["all"] + DECISIONS,
            key="lib_decision",
            help="Filter by your manual screening decision.",
        )
    with fc3:
        year_min = st.number_input(
            "Year ≥ (0 = any)",
            min_value=0,
            max_value=2100,
            value=0,
            step=1,
            help="Only show papers published in this year or later. Set to 0 to disable.",
        )
    with fc4:
        tag_filter = st.text_input(
            "Filter by tag",
            key="lib_tag",
            placeholder="e.g. methods",
            help="Case-insensitive substring match on tags you've assigned.",
        )

    # Publication-type filter — options come from what's actually present.
    session = new_session()
    try:
        present_types = sorted(
            {
                (t or "").strip()
                for (t,) in session.query(CollectedArticle.pub_type)
                .filter_by(project_id=selected_id)
                .distinct()
                if (t or "").strip()
            }
        )
    finally:
        session.close()
    type_filter = st.selectbox(
        "Publication type",
        ["all"] + present_types,
        key="lib_pubtype",
        help="Filter by the publication type recorded from the source database "
        "(e.g. article, review, preprint). 'all' includes records with no type.",
    )

    page = st.session_state.get("lib_page", 0)

    session = new_session()
    try:
        q = session.query(CollectedArticle).filter_by(project_id=selected_id)
        if filter_kw.strip():
            q = q.filter(CollectedArticle.title.ilike(f"%{filter_kw.strip()}%"))
        if decision_filter == "unscreened":
            q = q.filter(_unscreened_clause())
        elif decision_filter != "all":
            q = q.filter(CollectedArticle.screening_status == decision_filter)
        if year_min:
            q = q.filter(CollectedArticle.year != None).filter(CollectedArticle.year >= int(year_min))  # noqa: E711
        if tag_filter.strip():
            q = q.filter(CollectedArticle.tags.ilike(f"%{tag_filter.strip()}%"))
        if type_filter != "all":
            q = q.filter(CollectedArticle.pub_type == type_filter)
        ordered = q.order_by(CollectedArticle.year.desc().nullslast(), CollectedArticle.id.desc())
        total_filtered = ordered.count()
        all_filtered = ordered.all()
        page_slice = all_filtered[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

        # Per-project serial numbers across the full filtered set (so #1 is the
        # most recent / top of the list and the same paper has a stable #).
        rows = []
        for i, a in enumerate(page_slice, start=page * PAGE_SIZE + 1):
            title = a.title or ""
            authors = a.authors or ""
            rows.append(
                {
                    "#": i,
                    "Year": a.year or "",
                    "Title": title[:140] + ("…" if len(title) > 140 else ""),
                    "Authors": authors[:80] + ("…" if len(authors) > 80 else ""),
                    "Type": a.pub_type or "",
                    "Source": a.source or "",
                    "Decision": a.screening_status or "unscreened",
                    "Tags": a.tags or "",
                    "_id": a.id,
                }
            )
    finally:
        session.close()

    truncated = " (showing first 50 — use filters or pagination to find more)" if total_filtered > PAGE_SIZE else ""
    st.caption(f"**{total_filtered}** matching papers{truncated}.")

    # Downloads — Excel + CSV + JSON
    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        xlsx_bytes = articles_to_excel(all_filtered)
        st.download_button(
            f"⬇ Excel ({total_filtered})",
            data=xlsx_bytes,
            file_name=filename_for(project_name, "library", "xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Download all matching papers as a formatted Excel workbook (header row frozen, columns auto-sized, long fields wrap).",
            use_container_width=True,
        )
    with dc2:
        csv_text = pd.DataFrame(
            [
                {
                    "#": i,
                    "Title": a.title,
                    "Authors": a.authors,
                    "Year": a.year or "",
                    "DOI": a.doi or "",
                    "URL": a.url or "",
                    "Abstract": a.abstract or "",
                    "Source": a.source or "",
                    "Decision": a.screening_status or "unscreened",
                    "Tags": a.tags or "",
                    "Notes": a.notes or "",
                }
                for i, a in enumerate(all_filtered, 1)
            ]
        ).to_csv(index=False)
        st.download_button(
            f"⬇ CSV ({total_filtered})",
            data=csv_text.encode("utf-8"),
            file_name=filename_for(project_name, "library", "csv"),
            mime="text/csv",
            use_container_width=True,
        )
    with dc3:
        json_payload = pd.DataFrame(
            [
                {
                    "id": a.id,
                    "title": a.title,
                    "authors": a.authors,
                    "year": a.year,
                    "doi": a.doi,
                    "url": a.url,
                    "abstract": a.abstract,
                    "source": a.source,
                    "decision": a.screening_status,
                    "tags": a.tags,
                    "notes": a.notes,
                }
                for a in all_filtered
            ]
        ).to_json(orient="records", indent=2, force_ascii=False)
        st.download_button(
            f"⬇ JSON ({total_filtered})",
            data=json_payload.encode("utf-8"),
            file_name=filename_for(project_name, "library", "json"),
            mime="application/json",
            use_container_width=True,
        )

    st.markdown(
        "_Click any row to view the abstract and change screening status._",
        help="In the Excel download, every column is properly sized. Long fields like Title and Abstract wrap inside the cell — click a cell to read the full text in the formula bar.",
    )
    event = st.dataframe(
        pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "#": st.column_config.NumberColumn("#", help="Serial number within the current filter", width="small"),
            "Title": st.column_config.TextColumn("Title", width="large"),
            "Authors": st.column_config.TextColumn("Authors", width="medium"),
            "Year": st.column_config.NumberColumn("Year", format="%d", width="small"),
            "Type": st.column_config.TextColumn("Type", width="small", help="Publication type from the source database"),
            "Source": st.column_config.TextColumn("Source", width="small"),
            "Decision": st.column_config.TextColumn("Decision", width="small"),
            "Tags": st.column_config.TextColumn("Tags", width="small"),
        },
    )

    # Edit selected row
    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        idx = selected_rows[0]
        art_id = rows[idx]["_id"]
        session = new_session()
        try:
            art = session.get(CollectedArticle, art_id)
            with st.container(border=True):
                st.markdown(f"#### {art.title}")
                st.caption(f"{art.authors or ''} · {art.year or ''} · {art.source or ''}")
                if art.doi:
                    st.markdown(f"DOI: [`{art.doi}`](https://doi.org/{art.doi})")
                st.markdown(art.abstract or "*No abstract available.*")

                # Quick-decision buttons (outside the form so a single click
                # commits without saving the whole form). Keyboard shortcuts
                # I/M/E/N are wired up by bind_keys below.
                st.caption(
                    "**Quick decision** — click a button or press the highlighted key. "
                    "Keys only fire when you're not typing in a text field."
                )
                qb1, qb2, qb3, qb4 = st.columns(4)
                quick_action = None
                with qb1:
                    if st.button("Include [I]", key=f"qb_inc_{art.id}", type="primary", use_container_width=True):
                        quick_action = "include"
                with qb2:
                    if st.button("Maybe [M]", key=f"qb_may_{art.id}", use_container_width=True):
                        quick_action = "maybe"
                with qb3:
                    if st.button("Exclude [E]", key=f"qb_exc_{art.id}", use_container_width=True):
                        quick_action = "exclude"
                with qb4:
                    if st.button("Next unscreened [N]", key=f"qb_nxt_{art.id}", use_container_width=True):
                        quick_action = "next"

                bind_keys({
                    "i": "Include [I]",
                    "m": "Maybe [M]",
                    "e": "Exclude [E]",
                    "n": "Next unscreened [N]",
                })

                if quick_action in ("include", "maybe", "exclude"):
                    art.screening_status = quick_action
                    session.commit()
                    st.toast(f"Saved: {quick_action}", icon="✅")
                    # Auto-advance: select the next unscreened row in the current page.
                    next_idx = None
                    for j in range(idx + 1, len(rows)):
                        next_idx = j
                        break
                    st.session_state.lib_quick_next_idx = next_idx
                    st.rerun()
                elif quick_action == "next":
                    next_idx = None
                    for j in range(idx + 1, len(rows)):
                        next_idx = j
                        break
                    st.session_state.lib_quick_next_idx = next_idx
                    st.rerun()
                with st.form(f"edit_lib_{art.id}"):
                    decision = st.radio(
                        "Screening decision",
                        DECISIONS,
                        index=DECISIONS.index(art.screening_status if art.screening_status in DECISIONS else "unscreened"),
                        horizontal=True,
                        help="Your manual decision after reading the title/abstract.",
                    )

                    # Preset exclusion reasons. The stored value is the
                    # selected presets joined by ' | ', optionally followed
                    # by free-text after the last ' | '.
                    existing_reason = art.decision_reason or ""
                    prior_presets = []
                    prior_freetext = existing_reason
                    if existing_reason:
                        parts = [p.strip() for p in existing_reason.split(" | ") if p.strip()]
                        prior_presets = [p for p in parts if p in EXCLUSION_REASONS]
                        leftover = [p for p in parts if p not in EXCLUSION_REASONS]
                        prior_freetext = " | ".join(leftover)

                    reason_chips = st.multiselect(
                        "Exclusion reasons (if excluding)",
                        EXCLUSION_REASONS,
                        default=prior_presets,
                        help="Pick one or more standard reasons. Only used when decision = exclude.",
                    )
                    reason_freetext = st.text_input(
                        "Extra reason note (optional)",
                        value=prior_freetext,
                        placeholder="anything not covered above",
                    )
                    tags = st.text_input("Tags", value=art.tags or "", placeholder="methods, key paper")
                    notes = st.text_area("Notes", value=art.notes or "", height=80)
                    if st.form_submit_button("Save", type="primary"):
                        art.screening_status = decision
                        parts = list(reason_chips)
                        if reason_freetext.strip():
                            parts.append(reason_freetext.strip())
                        art.decision_reason = " | ".join(parts)
                        art.tags = tags.strip()
                        art.notes = notes.strip()
                        session.commit()
                        st.success("Saved.")
                        st.rerun()
        finally:
            session.close()

    # Pagination
    total_pages = max(1, (total_filtered + PAGE_SIZE - 1) // PAGE_SIZE)
    p1, p2, p3 = st.columns([1, 2, 1])
    with p1:
        if st.button("← Prev", disabled=page == 0, use_container_width=True):
            st.session_state.lib_page = page - 1
            st.rerun()
    with p2:
        st.caption(f"Page {page + 1} of {total_pages}")
    with p3:
        if st.button("Next →", disabled=page >= total_pages - 1, use_container_width=True):
            st.session_state.lib_page = page + 1
            st.rerun()

    # Possible duplicates panel.
    st.markdown("---")
    with st.expander("🔎 Possible duplicates", expanded=False):
        st.caption(
            "Finds groups of probable duplicate papers (same DOI, same normalized title, "
            "or fuzzy title match within the same year). Cross-source duplicates are already "
            "filtered at save time — this catches near-misses."
        )
        sc1, sc2 = st.columns([1, 3])
        with sc1:
            if st.button("🔄 Scan for duplicates", help="Re-scan the library. Takes a few seconds on big libraries."):
                st.session_state.lib_dup_clusters = find_clusters(selected_id)
                st.session_state.pop("lib_dup_confirm", None)
                st.rerun()
        with sc2:
            if "lib_dup_clusters" in st.session_state:
                resolved = st.session_state.get("lib_dup_resolved", set())
                clusters_all = st.session_state["lib_dup_clusters"]
                pending = [c for c in clusters_all if c.cluster_id not in resolved]
                st.caption(
                    f"**{len(pending)}** group(s) pending · "
                    f"**{sum(len(c.members) - 1 for c in pending)}** row(s) would be removed"
                    f"{f' · {len(resolved)} skipped' if resolved else ''}"
                )

        clusters = st.session_state.get("lib_dup_clusters")
        if clusters is None:
            st.caption("No scan yet. Click **🔄 Scan for duplicates** above.")
        elif not clusters:
            st.success("No duplicates found 🎉")
        else:
            resolved = st.session_state.setdefault("lib_dup_resolved", set())
            pending = [c for c in clusters if c.cluster_id not in resolved]

            if not pending:
                st.info("All groups resolved. Click **🔄 Scan for duplicates** to re-scan.")

            # Bulk-action bar with two-step confirmation. Auto-picks the
            # best-metadata row as keeper and deletes the rest, in one go,
            # writing to the SQLite DB immediately.
            if pending:
                bc1, bc2 = st.columns([1, 2])
                with bc1:
                    confirm = st.session_state.get("lib_dup_confirm", False)
                    if not confirm:
                        if st.button(
                            f"⚡ Merge all {len(pending)} groups",
                            type="primary",
                            help="One-click bulk merge. For each group, the row with the most metadata "
                            "(has DOI, longest abstract, most authors) is kept; the others are merged "
                            "into it and then permanently deleted from the database.",
                        ):
                            st.session_state.lib_dup_confirm = True
                            st.rerun()
                    else:
                        st.warning(
                            f"This will permanently delete **{sum(len(c.members) - 1 for c in pending)}** "
                            f"rows from the database across **{len(pending)}** groups. **This cannot be undone.**"
                        )
                        cc1, cc2 = st.columns(2)
                        with cc1:
                            if st.button("✅ Yes, merge all now", type="primary", use_container_width=True):
                                groups_merged, rows_deleted = merge_all_clusters(pending)
                                st.session_state.lib_dup_clusters = find_clusters(selected_id)
                                st.session_state.lib_dup_resolved = set()
                                st.session_state.pop("lib_dup_confirm", None)
                                st.success(
                                    f"Merged **{groups_merged}** groups · removed **{rows_deleted}** "
                                    f"duplicate rows from the database."
                                )
                                st.rerun()
                        with cc2:
                            if st.button("Cancel", use_container_width=True):
                                st.session_state.pop("lib_dup_confirm", None)
                                st.rerun()

            st.markdown("---")

            # Per-group cards — cleaner than data_editor.
            for c in pending[:20]:
                keeper = pick_keeper(c.members)
                others = [m for m in c.members if m.id != keeper.id]

                # Header row with reason for grouping.
                shared_doi = next((m.doi for m in c.members if m.doi), "")
                if all((m.doi or "").lower() == (shared_doi or "").lower() for m in c.members) and shared_doi:
                    reason = f"same DOI · `{shared_doi}`"
                else:
                    reason = "matching titles"

                with st.container(border=True):
                    hdr1, hdr2 = st.columns([4, 1])
                    with hdr1:
                        st.markdown(f"**Group of {len(c.members)}** — {reason}")
                    with hdr2:
                        if st.button("Skip", key=f"dup_skip_{c.cluster_id}", help="Hide this group without merging."):
                            resolved.add(c.cluster_id)
                            st.session_state.lib_dup_resolved = resolved
                            st.rerun()

                    # Keeper row
                    st.markdown(
                        f"✅ **KEEP** &nbsp; `#{keeper.id}` &nbsp; "
                        f"{keeper.year or '—'} · {keeper.source or '—'} · "
                        f"abstract: {len(keeper.abstract or '')} chars · "
                        f"{'DOI ✓' if keeper.doi else 'no DOI'}"
                    )
                    st.caption((keeper.title or "")[:200])

                    # Other rows (to be dropped)
                    for m in others:
                        st.markdown(
                            f"❌ drop &nbsp; `#{m.id}` &nbsp; "
                            f"{m.year or '—'} · {m.source or '—'} · "
                            f"abstract: {len(m.abstract or '')} chars · "
                            f"{'DOI ✓' if m.doi else 'no DOI'}"
                        )
                        st.caption((m.title or "")[:200])

                    # Per-group merge button + optional manual keeper override.
                    bm1, bm2, bm3 = st.columns([1, 2, 2])
                    with bm1:
                        if st.button(
                            "Merge this group",
                            key=f"dup_merge_one_{c.cluster_id}",
                            type="primary",
                            help=f"Merge {len(others)} row(s) into keeper #{keeper.id} and delete them from the DB.",
                        ):
                            n = merge_into(keeper.id, [m.id for m in others])
                            st.session_state.lib_dup_clusters = find_clusters(selected_id)
                            st.success(f"Merged {n} row(s) into #{keeper.id}.")
                            st.rerun()
                    with bm2:
                        override = st.selectbox(
                            "Use a different keeper?",
                            options=["(auto)"] + [f"#{m.id} — {m.source}" for m in c.members],
                            key=f"dup_keep_sel_{c.cluster_id}",
                            label_visibility="collapsed",
                        )
                    with bm3:
                        if override != "(auto)" and st.button(
                            f"Merge into {override}", key=f"dup_merge_alt_{c.cluster_id}"
                        ):
                            chosen_id = int(override.split(" — ")[0].lstrip("#"))
                            dropped_ids = [m.id for m in c.members if m.id != chosen_id]
                            n = merge_into(chosen_id, dropped_ids)
                            st.session_state.lib_dup_clusters = find_clusters(selected_id)
                            st.success(f"Merged {n} row(s) into #{chosen_id}.")
                            st.rerun()

            if len(pending) > 20:
                st.caption(f"_… and {len(pending) - 20} more group(s). Re-scan after merging this batch._")


# Section 2: Search the web

elif section == "🔍 Search the web":
    st.markdown("### Search OpenAlex, PubMed and Semantic Scholar")
    st.caption(
        "Type a topic (or paste a list of topics) and we'll query all enabled databases. "
        "Results land in your library."
    )

    type_override = st.radio(
        "Search for",
        ["Use project setting", "Review articles", "Research articles"],
        horizontal=True,
        help=(
            "Override the project's literature type just for this search.\n\n"
            "Review articles → filtered to review/overview articles.\n"
            "Research articles → primary research articles."
        ),
    )
    search_mode = derive_search_mode(
        literature_type=literature_type,
        override="" if type_override == "Use project setting" else type_override,
    )
    _mode_label = {
        "reviews": "review papers only",
        "articles": "research papers only (reviews and non-research items excluded)",
        "both": "research papers and reviews (non-research items like books, editorials and datasets excluded)",
    }[search_mode]
    st.caption(f"This search will fetch **{_mode_label}**.")

    one_or_many = st.radio(
        "How many topics?",
        ["One topic", "Multiple topics"],
        horizontal=True,
        help=(
            "**One topic** — type a single search string. Quick.\n\n"
            "**Multiple topics** — paste a list (one per line) and we run each as a separate search "
            "in the background. Good for big sweeps."
        ),
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        year_from = st.number_input(
            "Published from year",
            min_value=1900,
            max_value=2100,
            value=2019,
            step=1,
            help="Only fetch papers published in this year or later.",
        )
    with col2:
        max_per_source = st.select_slider(
            "Max results per source / topic",
            options=[10, 20, 30, 50, 100, 200],
            value=30,
            help="Cap per database per query. With 3 sources, 30 means up to 90 hits per topic.",
        )
    with col3:
        st.markdown("**Databases**")
        use_openalex = st.checkbox("OpenAlex", value=True, help="Open-access metadata covering most disciplines.")
        use_pubmed = st.checkbox("PubMed", value=True, help="Life sciences (NCBI/NLM).")
        use_s2 = st.checkbox("Semantic Scholar", value=True, help="AI/CS-leaning but broad coverage.")
        use_arxiv = st.checkbox(
            "arXiv",
            value=False,
            help="Preprints in physics, math, CS, quantitative biology, statistics. "
            "Adds ~3 sec per topic (polite rate limit). Often the only source with bleeding-edge work.",
        )

    with st.expander("Title keyword filter (optional)", expanded=False):
        st.caption(
            "After fetching results, keep only those whose **title** contains your keywords. "
            "Comma-separated. Leave empty to keep everything the databases return."
        )
        kw_col1, kw_col2 = st.columns([3, 1])
        with kw_col1:
            title_keyword = st.text_input(
                "Title must contain",
                key="ws_title_kw",
                placeholder="e.g. amide, CRISPR",
                label_visibility="collapsed",
                help="Comma-separated list of words. Case-insensitive substring match.",
            )
        with kw_col2:
            mode_label = st.radio(
                "Match",
                ["Any", "All"],
                horizontal=True,
                key="ws_title_kw_mode",
                help="Any = title has at least one keyword. All = title has every keyword.",
            )
            title_match_mode = "all" if mode_label == "All" else "any"

    search_settings = dict(
        max_per_source=max_per_source,
        year_from=int(year_from),
        use_openalex=use_openalex,
        use_pubmed=use_pubmed,
        use_s2=use_s2,
        use_arxiv=use_arxiv,
    )

    st.markdown("---")

    if one_or_many == "One topic":
        from utils.search_runner import (
            run_article_search_with_status,
            run_both_search_with_status,
            run_review_search_with_status,
        )

        with st.form("ws_one"):
            query = st.text_input(
                "Search topic",
                value=project_topic,
                help="A few words is best (3–8). Long sentences match nothing.",
            )
            go = st.form_submit_button("Search", type="primary")
        if go and query.strip():
            with st.spinner("Searching databases…"):
                if search_mode == "reviews":
                    results, errors = run_review_search_with_status(query, **search_settings)
                elif search_mode == "both":
                    results, errors = run_both_search_with_status(query, **search_settings)
                else:
                    results, errors = run_article_search_with_status(query, **search_settings)
            added, skipped = save_to_library(results, selected_id, title_keyword, title_match_mode)
            msg = f"Found {len(results)} unique papers · **{added} new saved**"
            if skipped:
                msg += f" · {skipped} filtered out by title keywords"
            st.success(msg)
            for src, msg in (errors or {}).items():
                st.warning(f"{src}: {msg}")
            st.rerun()
    else:
        active_job = st.session_state.get("ws_search_job_id") or find_active_search_job(
            selected_id, search_mode
        )
        if active_job:
            st.session_state.ws_search_job_id = active_job

            @st.fragment(run_every=2)
            def _ws_search_progress():
                status = get_search_status(active_job)
                if status is None:
                    st.session_state.pop("ws_search_job_id", None)
                    st.rerun()
                    return
                pct = status["completed"] / status["total"] if status["total"] else 0
                st.progress(pct, text=f"{status['completed']} / {status['total']} topics done")
                if status.get("current_query") and not status["done"]:
                    st.caption(f"Currently searching: `{status['current_query']}`")
                with st.expander("Per-topic log", expanded=True):
                    for line in status.get("log", []):
                        st.markdown(line)
                if status["done"]:
                    if status.get("error"):
                        st.error(f"Search error: {status['error']}")
                    else:
                        skip_note = f" · {status.get('total_skipped', 0)} title-filtered" if status.get("total_skipped") else ""
                        st.success(f"Done — **{status['total_added']} new papers saved**{skip_note}.")
                    clear_search_job(active_job)
                    st.session_state.pop("ws_search_job_id", None)
                    st.rerun()

            _ws_search_progress()
            if st.button("Cancel search", type="secondary"):
                # Signal the worker to stop after the current query; the
                # progress fragment clears the job once it reports done.
                request_cancel_search(active_job)
                st.toast("Cancelling after the current search…", icon="🛑")
                st.rerun()
        else:
            saved = load_queues(selected_id)
            seed = saved.get("ca") or "\n".join(
                [project_topic, f"{project_topic} review", f"{project_topic} mechanism", f"{project_topic} recent advances"]
            )
            queue_text = st.text_area(
                "Topics — one per line",
                value=seed,
                height=240,
                help="Each line becomes a separate search. Auto-saved as you type.",
            )
            if queue_text != saved.get("ca", ""):
                save_ca_queue(selected_id, queue_text)
            queries = [q.strip() for q in queue_text.splitlines() if q.strip()]
            st.caption(f"{len(queries)} topics queued.")
            if st.button("Run all searches", type="primary", disabled=not queries):
                job_id = start_search_job(
                    queries=queries,
                    settings=search_settings,
                    mode=search_mode,
                    project_id=selected_id,
                    title_keyword=title_keyword,
                    title_match_mode=title_match_mode,
                )
                st.session_state.ws_search_job_id = job_id
                st.rerun()


# Section 3: Import my list

elif section == "📥 Import my list":
    st.markdown("### Import your existing reference list")
    st.caption(
        "Have a curated list of papers already? Upload it here. "
        "Each row becomes either a library entry (research / mixed) or a curated review "
        "that you can later extract citations from."
    )

    target = st.radio(
        "Where do these go?",
        ["Library (papers to read / screen)", "Curated reviews (so I can extract their citations)"],
        help=(
            "**Library** — generic add. Treat each row as a paper in your project.\n\n"
            "**Curated reviews** — for review articles you want to mine for cited references. "
            "Pick this if you'll use **🔗 Extract citations** afterwards."
        ),
    )

    if target.startswith("Library"):
        st.caption("Accepted: CSV, BibTeX (.bib), RIS (.ris), or a plain text list of DOIs.")
        up = st.file_uploader("Reference file", type=["csv", "bib", "ris", "txt"], key="lib_upload")
        do_enrich = st.checkbox(
            "Look up missing metadata from Crossref",
            value=True,
            help="For DOI-only or sparse imports, fetch the real title, authors and "
            "year from Crossref so the records are screenable. Adds ~0.1s per record.",
        )
        if up and st.button("Import", type="primary"):
            refs = parse_reference_upload(up.name, up.getvalue())
            if do_enrich and refs:
                from utils.enrich import enrich_records

                bar = st.progress(0.0, text="Looking up metadata from Crossref…")
                enrich_records(
                    refs,
                    progress=lambda done, total: bar.progress(
                        done / total if total else 1.0, text=f"Enriched {done}/{total}"
                    ),
                )
                bar.empty()
            added, skipped = save_to_library(refs, selected_id, imported_from="Import")
            st.success(f"Parsed {len(refs)} records · **{added} new saved** · {skipped} filtered.")
            st.rerun()
    else:
        st.caption(
            "Accepted: Excel (.xlsx / .xls). The header row must include a **Title** and **DOI** column "
            "(other columns like Year, Journal, Theme, Why included are kept as metadata)."
        )
        up = st.file_uploader("Excel file", type=["xlsx", "xls"], key="cur_upload")
        replace = st.checkbox(
            "Replace existing curated reviews (and their extracted citations)",
            value=False,
            help="Clear the current curated-review list for this project first. Use this if you want a clean start.",
        )
        if up is not None:
            try:
                rows = parse_curated_excel(up.name, up.getvalue())
            except Exception as exc:
                st.error(f"Could not parse file: {exc}")
                rows = []
            if rows:
                st.success(f"Parsed **{len(rows)}** rows from `{up.name}`.")
                st.dataframe(pd.DataFrame(rows[:10]), use_container_width=True, hide_index=True)
                if st.button("Save to project", type="primary"):
                    added, replaced = import_curated_reviews(selected_id, rows, replace)
                    if replace:
                        st.success(f"Replaced. {added} curated reviews now in project (cleared {replaced}).")
                    else:
                        st.success(f"Added **{added}** new curated reviews ({len(rows) - added} duplicates skipped).")
                    st.rerun()


# Section 4: Extract citations from reviews

elif section == "🔗 Extract citations from reviews":
    st.markdown("### Extract cited references from review papers")
    st.caption(
        "For every review in your curated list, we fetch its reference list "
        "(Semantic Scholar → Crossref fallback) and apply your filter."
    )

    if curated_count == 0:
        st.info(
            "No curated reviews in this project yet. Go to **📥 Import my list** → "
            "**Curated reviews** and upload an Excel with Title + DOI columns first."
        )
        st.stop()

    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1:
        year_floor = st.number_input(
            "Year floor for research papers",
            min_value=1900,
            max_value=2100,
            value=2019,
            step=1,
            help="Research papers published before this year are rejected. Reviews are kept (see next toggle).",
        )
    with cc2:
        keep_reviews_regardless = st.checkbox(
            "Keep reviews regardless of year",
            value=True,
            help="If on, review-type citations are kept even if older than the year floor.",
        )
    with cc3:
        exclude_books = st.checkbox(
            "Exclude books / chapters",
            value=True,
            help="Reject cited references flagged as books or book chapters "
            "(detected via Semantic Scholar / Crossref type metadata).",
        )
    with cc4:
        scope = st.radio(
            "Run on",
            ["Pending or failed", "All reviews", "Failed only"],
            help="Pending or failed = everything not yet successfully extracted.",
        )

    session = new_session()
    try:
        q = session.query(CuratedReview).filter_by(project_id=selected_id)
        if scope == "Pending or failed":
            q = q.filter(CuratedReview.extraction_status.in_(["pending", "failed"]))
        elif scope == "Failed only":
            q = q.filter(CuratedReview.extraction_status == "failed")
        target_ids = [r.id for r in q.order_by(CuratedReview.id).all()]
    finally:
        session.close()

    st.caption(f"Will process **{len(target_ids)}** review(s).")

    active_job = st.session_state.get("ws_extract_job_id") or find_active_extract_job(selected_id)
    if active_job:
        st.session_state.ws_extract_job_id = active_job

        @st.fragment(run_every=2)
        def _ws_extract_progress():
            status = get_extract_status(active_job)
            if status is None:
                st.session_state.pop("ws_extract_job_id", None)
                st.rerun()
                return
            pct = status["completed"] / status["total"] if status["total"] else 0
            st.progress(pct, text=f"{status['completed']} / {status['total']} reviews done")
            if status.get("current_review") and not status["done"]:
                st.caption(f"Working on: {status['current_review']}")
            totals = status.get("totals", {})
            tcols = st.columns(5)
            tcols[0].metric("Kept", totals.get("kept", 0))
            tcols[1].metric("Rejected", totals.get("rejected", 0))
            tcols[2].metric("Reviews flagged", totals.get("reviews_flagged", 0))
            tcols[3].metric("Books rejected", totals.get("books_rejected", 0))
            tcols[4].metric("No refs", totals.get("no_refs", 0))
            with st.expander("Per-review log", expanded=True):
                for line in status.get("log", []):
                    st.markdown(line)
            if status["done"]:
                if status.get("error"):
                    st.error(f"Job error: {status['error']}")
                else:
                    st.success("Extraction complete.")
                clear_extract_job(active_job)
                st.session_state.pop("ws_extract_job_id", None)
                st.rerun()

        _ws_extract_progress()
        if st.button("Cancel extraction", type="secondary"):
            # Signal the worker to stop after the current review; the progress
            # fragment clears the job once it reports done.
            request_cancel_extract(active_job)
            st.toast("Cancelling after the current review…", icon="🛑")
            st.rerun()
    else:
        if st.button("Start extraction", type="primary", disabled=len(target_ids) == 0):
            job_id = start_extract_job(
                project_id=selected_id,
                review_ids=target_ids,
                year_floor=int(year_floor),
                keep_reviews_regardless_of_year=keep_reviews_regardless,
                exclude_books=exclude_books,
            )
            st.session_state.ws_extract_job_id = job_id
            st.rerun()

    # Browse + download cited articles
    st.markdown("---")
    st.markdown("### Cited articles collected")
    if cited_count == 0:
        st.caption("No cited articles yet. Run extraction above.")
    else:
        fc1, fc2, fc3 = st.columns([1, 1, 2])
        with fc1:
            view = st.radio("Show", ["Kept", "Rejected", "All"], key="ws_cited_view")
        with fc2:
            review_only = st.checkbox("Flagged-as-review only", value=False, key="ws_cited_review_only")
        with fc3:
            cited_kw = st.text_input(
                "Title contains",
                key="ws_cited_kw",
                placeholder="e.g. catalyst",
                help="Case-insensitive substring match.",
            )
        cited_year_min = st.number_input(
            "Year ≥ (0 = any)",
            min_value=0,
            max_value=2100,
            value=0,
            step=1,
            key="ws_cited_year",
        )

        session = new_session()
        try:
            cq = session.query(CitedArticle).filter_by(project_id=selected_id)
            if view == "Kept":
                cq = cq.filter(CitedArticle.status == "kept")
            elif view == "Rejected":
                cq = cq.filter(CitedArticle.status == "rejected")
            if review_only:
                cq = cq.filter(CitedArticle.is_review == True)  # noqa: E712
            if cited_kw.strip():
                cq = cq.filter(CitedArticle.title.ilike(f"%{cited_kw.strip()}%"))
            if cited_year_min:
                cq = cq.filter(CitedArticle.year != None).filter(CitedArticle.year >= int(cited_year_min))  # noqa: E711
            ordered = cq.order_by(CitedArticle.year.desc().nullslast(), CitedArticle.id.desc())
            cited_total_match = ordered.count()
            full_cited = ordered.all()
        finally:
            session.close()

        preview = full_cited[:500]
        st.caption(f"**{cited_total_match}** matching cited articles. (Table shows first {len(preview)}; download has all.)")

        # Downloads
        dc1, dc2 = st.columns(2)
        with dc1:
            xlsx_bytes = cited_articles_to_excel(full_cited)
            st.download_button(
                f"⬇ Excel ({cited_total_match})",
                data=xlsx_bytes,
                file_name=filename_for(project_name, "cited", "xlsx"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with dc2:
            csv_payload = pd.DataFrame(
                [
                    {
                        "#": i,
                        "Title": a.title,
                        "Authors": a.authors,
                        "Year": a.year or "",
                        "Venue": a.venue,
                        "DOI": a.doi,
                        "URL": a.url,
                        "Abstract": a.abstract,
                        "Is Review": "Yes" if a.is_review else "",
                        "Status": a.status,
                        "Rejected Reason": a.rejected_reason,
                        "Source": a.source,
                        "Review ID": a.curated_review_id,
                    }
                    for i, a in enumerate(full_cited, 1)
                ]
            ).to_csv(index=False)
            st.download_button(
                f"⬇ CSV ({cited_total_match})",
                data=csv_payload.encode("utf-8"),
                file_name=filename_for(project_name, "cited", "csv"),
                mime="text/csv",
                use_container_width=True,
            )

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "#": i,
                        "Year": a.year or "",
                        "Title": (a.title or "")[:140] + ("…" if a.title and len(a.title) > 140 else ""),
                        "Authors": (a.authors or "")[:80] + ("…" if a.authors and len(a.authors) > 80 else ""),
                        "Venue": (a.venue or "")[:40],
                        "Is Review": "Yes" if a.is_review else "",
                        "Status": a.status,
                        "Source": a.source,
                    }
                    for i, a in enumerate(preview, 1)
                ]
            ),
            use_container_width=True,
            hide_index=True,
            column_config={
                "#": st.column_config.NumberColumn("#", width="small"),
                "Title": st.column_config.TextColumn("Title", width="large"),
            },
        )

    # Curated reviews list (collapsed by default)
    with st.expander("Manage curated reviews", expanded=False):
        session = new_session()
        try:
            reviews = (
                session.query(CuratedReview)
                .filter_by(project_id=selected_id)
                .order_by(CuratedReview.year.desc().nullslast(), CuratedReview.id)
                .all()
            )
            data = [
                {
                    "#": i,
                    "Year": r.year or "",
                    "Title": (r.title or "")[:140] + ("…" if r.title and len(r.title) > 140 else ""),
                    "DOI": r.doi or "",
                    "Journal": r.journal or "",
                    "Status": r.extraction_status,
                    "Refs (kept / total)": f"{r.references_kept} / {r.references_total}" if r.references_total else "",
                }
                for i, r in enumerate(reviews, 1)
            ]
        finally:
            session.close()
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        if st.button("⚠ Clear all curated reviews and their citations"):
            session = new_session()
            try:
                session.query(CitedArticle).filter_by(project_id=selected_id).delete(synchronize_session=False)
                session.query(CuratedReview).filter_by(project_id=selected_id).delete(synchronize_session=False)
                session.commit()
                st.success("Cleared.")
                st.rerun()
            finally:
                session.close()


# Section 5: Project settings

elif section == "⚙ Project settings":
    st.markdown("### Project settings")
    st.caption("Rename, change type, or delete this project.")

    session = new_session()
    try:
        p = session.get(Project, selected_id)
        with st.form("ws_settings"):
            new_name = st.text_input("Name", value=p.name)
            _types = ["Review + research articles", "Review articles", "Research articles"]
            _current = p.literature_type if p.literature_type in _types else "Review + research articles"
            new_type = st.selectbox("Looking for", _types, index=_types.index(_current))
            new_topic = st.text_input("Topic / main keyword", value=p.topic or "")
            new_desc = st.text_area("Description", value=p.description or "", height=80)
            if st.form_submit_button("Save", type="primary"):
                p.name = new_name.strip() or p.name
                p.literature_type = new_type
                p.topic = new_topic.strip()
                p.description = new_desc.strip()
                p.updated_at = datetime.now(timezone.utc)
                session.commit()
                st.success("Saved.")
                st.rerun()
    finally:
        session.close()

    st.markdown("---")
    st.markdown("#### Danger zone")
    if st.checkbox("I want to permanently delete this project", key="ws_confirm_delete"):
        if st.button("Delete project", type="primary"):
            session = new_session()
            try:
                p = session.get(Project, selected_id)
                if p:
                    session.delete(p)
                    session.commit()
                st.session_state.active_project_id = None
                st.success("Project deleted.")
                st.rerun()
            finally:
                session.close()
