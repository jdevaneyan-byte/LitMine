"""Phase: Extract References from curated review papers.

Workflow:
1. Upload an Excel master list of curated review papers (one row per review,
   must include a Title and DOI column). Each review gets a stable ID.
2. Click "Extract References" — the app fetches each review's reference list
   from Semantic Scholar (with Crossref fallback) in a background thread.
3. References are filtered: research papers older than the year floor are
   rejected. Reviews are flagged so the user can decide whether to chase them.
4. Browse / filter / download the kept (and rejected) references.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import func

from database import CitedArticle, CuratedReview, Project, init_db, new_session
from utils.excel_import import parse_curated_excel
from utils.extract_job import clear_job, find_active_job, get_status, start_extract_job

st.set_page_config(page_title="Extract References", page_icon="ER", layout="wide")
init_db()


# Helpers (defined first so the page body can call them)

def _save_curated(project_id: int, rows: list[dict], replace: bool) -> tuple[int, int]:
    session = new_session()
    try:
        replaced = 0
        if replace:
            replaced = (
                session.query(CuratedReview).filter_by(project_id=project_id).count()
            )
            (
                session.query(CitedArticle).filter_by(project_id=project_id).delete(synchronize_session=False)
            )
            (
                session.query(CuratedReview).filter_by(project_id=project_id).delete(synchronize_session=False)
            )
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


def _clear_curated(project_id: int):
    session = new_session()
    try:
        session.query(CitedArticle).filter_by(project_id=project_id).delete(synchronize_session=False)
        session.query(CuratedReview).filter_by(project_id=project_id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


# Sidebar - active project

def select_project() -> int:
    st.sidebar.title("Literature Collector")
    st.sidebar.markdown("---")
    session = new_session()
    try:
        projects = session.query(Project).order_by(Project.created_at.desc()).all()
        project_map = {p.id: p.name for p in projects}
    finally:
        session.close()
    if not project_map:
        st.warning("No projects found. Create one on the Home page.")
        st.stop()
    active_id = st.session_state.get("active_project_id")
    if active_id not in project_map:
        active_id = list(project_map.keys())[0]
        st.session_state.active_project_id = active_id
    selected = st.sidebar.selectbox(
        "Active Project",
        options=list(project_map.keys()),
        format_func=lambda x: project_map[x],
        index=list(project_map.keys()).index(active_id),
    )
    st.session_state.active_project_id = selected
    return selected


selected_id = select_project()

# Project + counts
session = new_session()
try:
    project = session.get(Project, selected_id)
    project_name = project.name
    project_topic = project.topic
    review_count = session.query(CuratedReview).filter_by(project_id=selected_id).count()
    cited_total = session.query(CitedArticle).filter_by(project_id=selected_id).count()
    cited_kept = session.query(CitedArticle).filter_by(project_id=selected_id, status="kept").count()
    cited_rejected = session.query(CitedArticle).filter_by(project_id=selected_id, status="rejected").count()
    cited_review_flagged = session.query(CitedArticle).filter_by(
        project_id=selected_id, is_review=True
    ).count()
finally:
    session.close()

st.title("Extract References")
st.markdown(f"**Project:** {project_name} | **Topic:** `{project_topic}`")
st.markdown("---")

tab_import, tab_extract, tab_browse = st.tabs(
    [
        f"1. Curated Reviews ({review_count})",
        "2. Extract",
        f"3. Cited Articles ({cited_kept} kept / {cited_rejected} rejected)",
    ]
)


# Tab 1 - import the curated review master Excel

with tab_import:
    st.markdown("### Upload curated review master list")
    st.caption(
        "Upload an Excel (.xlsx / .xls) or CSV. The header row must include "
        "**Title** and **DOI** columns. Optional: Year, Journal, Theme, "
        "Core/Extended, Why included, DOI URL."
    )

    uploaded = st.file_uploader(
        "Master list",
        type=["xlsx", "xls"],
        key="curated_upload",
    )
    replace_existing = st.checkbox(
        "Replace existing curated reviews for this project (also deletes their cited articles)",
        value=False,
        key="curated_replace",
    )

    if uploaded is not None:
        try:
            rows = parse_curated_excel(uploaded.name, uploaded.getvalue())
        except Exception as exc:
            st.error(f"Could not parse file: {exc}")
            rows = []

        if rows:
            st.success(f"Parsed **{len(rows)}** rows from `{uploaded.name}`.")
            preview_df = pd.DataFrame(rows[:10])
            st.dataframe(preview_df, use_container_width=True, hide_index=True)
            if st.button("Save to project", type="primary", key="save_curated"):
                added, replaced = _save_curated(selected_id, rows, replace_existing)
                if replace_existing:
                    st.success(f"Replaced. {added} curated reviews now in project (cleared {replaced}).")
                else:
                    st.success(f"Added {added} new curated reviews (skipped {len(rows) - added} duplicates).")
                st.rerun()

    st.markdown("---")
    st.markdown("### Curated reviews in project")
    if review_count == 0:
        st.info("No curated reviews yet. Upload a master list above.")
    else:
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
                    "ID": r.id,
                    "Year": r.year or "",
                    "Title": r.title,
                    "DOI": r.doi or "",
                    "Journal": r.journal or "",
                    "Theme": r.theme or "",
                    "Importance": r.importance or "",
                    "Status": r.extraction_status,
                    "Refs (kept/total)": f"{r.references_kept}/{r.references_total}"
                    if r.references_total
                    else "",
                    "Last run": r.last_extracted_at.strftime("%Y-%m-%d %H:%M")
                    if r.last_extracted_at
                    else "",
                }
                for r in reviews
            ]
        finally:
            session.close()

        st.dataframe(
            pd.DataFrame(data),
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn("ID", width="small"),
                "Title": st.column_config.TextColumn("Title", width="large"),
                "DOI": st.column_config.LinkColumn("DOI", display_text=r".+", width="medium"),
            },
        )

        if st.button("Clear all curated reviews + their cited articles", type="secondary"):
            _clear_curated(selected_id)
            st.success("Cleared.")
            st.rerun()


# Tab 2 - run the extraction

with tab_extract:
    if review_count == 0:
        st.info("Import a master list in tab 1 first.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            year_floor = st.number_input(
                "Year floor for research articles",
                min_value=1900,
                max_value=2100,
                value=2019,
                step=1,
                help="Research papers published before this year are rejected. "
                "Reviews are flagged regardless of year (toggle below to also filter them).",
            )
        with col2:
            keep_reviews_regardless = st.checkbox(
                "Keep reviews regardless of year",
                value=True,
                help="If on, review references are kept even if older than the year floor.",
            )
        with col3:
            scope = st.radio(
                "Run on",
                ["Pending only", "All reviews", "Failed only"],
                horizontal=False,
                key="extract_scope",
            )

        # Pick review IDs based on scope.
        session = new_session()
        try:
            q = session.query(CuratedReview).filter_by(project_id=selected_id)
            if scope == "Pending only":
                q = q.filter(CuratedReview.extraction_status.in_(["pending", "failed"]))
            elif scope == "Failed only":
                q = q.filter(CuratedReview.extraction_status == "failed")
            target_ids = [r.id for r in q.order_by(CuratedReview.id).all()]
        finally:
            session.close()

        st.caption(f"Will process **{len(target_ids)}** review(s).")

        active_job = st.session_state.get("extract_job_id")
        # Recover from session_state loss (refresh) by scanning the job dir.
        if not active_job:
            recovered = find_active_job(selected_id)
            if recovered:
                st.session_state.extract_job_id = recovered
                active_job = recovered
        if active_job:

            @st.fragment(run_every=2)
            def _progress():
                status = get_status(active_job)
                if status is None:
                    st.session_state.pop("extract_job_id", None)
                    st.rerun()
                    return
                pct = status["completed"] / status["total"] if status["total"] else 0
                st.progress(pct, text=f"{status['completed']}/{status['total']} reviews processed")
                if status.get("current_review") and not status["done"]:
                    st.caption(f"Working on: {status['current_review']}")
                totals = status.get("totals", {})
                tcols = st.columns(4)
                tcols[0].metric("Kept", totals.get("kept", 0))
                tcols[1].metric("Rejected", totals.get("rejected", 0))
                tcols[2].metric("Reviews flagged", totals.get("reviews_flagged", 0))
                tcols[3].metric("No refs", totals.get("no_refs", 0))
                with st.expander("Log", expanded=True):
                    for line in status.get("log", []):
                        st.markdown(line)
                if status["done"]:
                    if status.get("error"):
                        st.error(f"Job error: {status['error']}")
                    else:
                        st.success("Extraction complete.")
                    clear_job(active_job)
                    st.session_state.pop("extract_job_id", None)
                    st.rerun()

            _progress()
            if st.button("Cancel", type="secondary"):
                clear_job(active_job)
                st.session_state.pop("extract_job_id", None)
                st.rerun()
        else:
            disabled = len(target_ids) == 0
            if st.button("Extract References", type="primary", disabled=disabled):
                job_id = start_extract_job(
                    project_id=selected_id,
                    review_ids=target_ids,
                    year_floor=int(year_floor),
                    keep_reviews_regardless_of_year=keep_reviews_regardless,
                )
                st.session_state.extract_job_id = job_id
                st.rerun()


# Tab 3 - browse cited articles

with tab_browse:
    if cited_total == 0:
        st.info("No cited articles yet. Run extraction in tab 2.")
    else:
        # Filters
        f1, f2, f3, f4 = st.columns([1, 1, 1, 2])
        with f1:
            view = st.radio("Show", ["Kept", "Rejected", "All"], key="browse_view", horizontal=False)
        with f2:
            review_filter_value = st.checkbox("Review only", value=False, key="browse_review_only")
        with f3:
            year_min = st.number_input(
                "Year >= (0 = no filter)", min_value=0, max_value=2100, value=0, step=1
            )
        with f4:
            kw = st.text_input("Title contains", placeholder="e.g. amide, cleavage")

        # Build review options
        session = new_session()
        try:
            reviews = (
                session.query(CuratedReview).filter_by(project_id=selected_id)
                .order_by(CuratedReview.id).all()
            )
            review_options = {0: "All reviews"} | {
                r.id: f"#{r.id} - {r.title[:80]}" for r in reviews
            }
        finally:
            session.close()
        parent_pick = st.selectbox(
            "Parent review",
            options=list(review_options.keys()),
            format_func=lambda x: review_options[x],
            key="browse_parent",
        )

        session = new_session()
        try:
            q = session.query(CitedArticle).filter_by(project_id=selected_id)
            if view == "Kept":
                q = q.filter(CitedArticle.status == "kept")
            elif view == "Rejected":
                q = q.filter(CitedArticle.status == "rejected")
            if review_filter_value:
                q = q.filter(CitedArticle.is_review == True)  # noqa: E712
            if year_min:
                q = q.filter(CitedArticle.year != None).filter(CitedArticle.year >= int(year_min))  # noqa: E711
            if kw.strip():
                q = q.filter(CitedArticle.title.ilike(f"%{kw.strip()}%"))
            if parent_pick:
                q = q.filter(CitedArticle.curated_review_id == parent_pick)

            total_filtered = q.count()
            ordered = q.order_by(CitedArticle.year.desc().nullslast(), CitedArticle.id.desc())
            # Table preview is capped to keep the page snappy.
            preview = ordered.limit(2000).all()
            # Full filtered set (for downloads). Loaded lazily only when needed.
            all_filtered = ordered.all()

            rows = [
                {
                    "Review ID": a.curated_review_id,
                    "Year": a.year or "",
                    "Title": a.title,
                    "Authors": a.authors,
                    "Venue": a.venue,
                    "DOI": (f"https://doi.org/{a.doi}" if a.doi else ""),
                    "Is Review": "Yes" if a.is_review else "",
                    "Status": a.status,
                    "Reason": a.rejected_reason,
                    "Source": a.source,
                }
                for a in preview
            ]

            full_rows = [
                {
                    "Review ID": a.curated_review_id,
                    "Year": a.year or "",
                    "Title": a.title,
                    "Authors": a.authors,
                    "Venue": a.venue,
                    "DOI": a.doi or "",
                    "DOI URL": f"https://doi.org/{a.doi}" if a.doi else "",
                    "URL": a.url or "",
                    "Abstract": a.abstract or "",
                    "Is Review": "Yes" if a.is_review else "",
                    "Publication Types": a.publication_types or "",
                    "Status": a.status,
                    "Rejected Reason": a.rejected_reason,
                    "Source": a.source,
                }
                for a in all_filtered
            ]
        finally:
            session.close()

        truncated = " (showing first 2000; download has all)" if total_filtered > 2000 else ""
        st.caption(
            f"Showing **{len(rows)}** of {total_filtered} matching cited articles{truncated}. "
            f"Project totals: {cited_kept} kept, {cited_rejected} rejected, {cited_review_flagged} flagged-as-review"
        )

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Title": st.column_config.TextColumn("Title", width="large"),
                "DOI": st.column_config.LinkColumn("DOI", display_text=r".+", width="medium"),
                "Authors": st.column_config.TextColumn("Authors", width="medium"),
            },
        )

        # Downloads (full filtered set, not the table preview).
        df_full = pd.DataFrame(full_rows)
        csv_bytes = df_full.to_csv(index=False).encode("utf-8")
        json_bytes = df_full.to_json(orient="records", indent=2, force_ascii=False).encode("utf-8")

        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                f"Download all matching as CSV ({total_filtered})",
                data=csv_bytes,
                file_name=f"{project_name}_cited_articles.csv",
                mime="text/csv",
            )
        with dl2:
            st.download_button(
                f"Download all matching as JSON ({total_filtered})",
                data=json_bytes,
                file_name=f"{project_name}_cited_articles.json",
                mime="application/json",
            )


