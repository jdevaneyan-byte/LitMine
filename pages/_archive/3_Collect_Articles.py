from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import func

from database import CollectedArticle, Project, init_db, new_session
from utils.export import articles_to_json
from utils.import_refs import parse_reference_upload
from utils.queue_store import load_queues, save_ca_queue
from utils.search_job import clear_job, find_active_job, get_status, start_job
from utils.search_query import build_query
from utils.search_runner import run_article_search_with_status

st.set_page_config(page_title="Collect Articles", page_icon="CA", layout="wide")
init_db()

PAGE_SIZE = 50
STATUSES = ["identified", "screened", "eligible", "included", "excluded"]
PDF_DIR = Path("uploaded_pdfs")
PDF_DIR.mkdir(exist_ok=True)


def load_project_selector() -> int:
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

    selected_id = st.sidebar.selectbox(
        "Active Project",
        options=list(project_map.keys()),
        format_func=lambda x: project_map[x],
        index=list(project_map.keys()).index(active_id),
    )
    st.session_state.active_project_id = selected_id
    return selected_id


def parse_keywords(raw: str) -> list[str]:
    return [p.strip().lower() for p in raw.replace("\n", ",").split(",") if p.strip()]


def title_matches(title: str, keywords: list[str], mode: str) -> bool:
    if not keywords:
        return True
    title_l = title.lower()
    if mode == "all":
        return all(keyword in title_l for keyword in keywords)
    return any(keyword in title_l for keyword in keywords)


def save_to_collection(
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
            title = art.get("title", "").strip()
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
                    screening_status="identified",
                    imported_from=imported_from,
                )
            )
            added += 1
            existing_titles.add(title_l)
            if doi_l:
                existing_dois.add(doi_l)

        p = session.get(Project, project_id)
        if p and p.stage < 4:
            p.stage = 4
        session.commit()
        return added, skipped_kw
    finally:
        session.close()


def save_pdf(project_id: int, article_id: int, uploaded) -> str:
    suffix = Path(uploaded.name).suffix or ".pdf"
    path = PDF_DIR / f"project_{project_id}_article_{article_id}{suffix}"
    path.write_bytes(uploaded.getvalue())
    return str(path)


selected_id = load_project_selector()

session = new_session()
try:
    project = session.get(Project, selected_id)
    project_name = project.name
    project_topic = project.topic
    chosen_title = project.chosen_title or ""
    collected_count = session.query(CollectedArticle).filter_by(project_id=selected_id).count()
finally:
    session.close()

st.title("Collect Articles")
st.markdown(f"**Project:** {project_name}")
if chosen_title:
    st.info(f"Review title: {chosen_title}")
else:
    st.warning("No review title set. You can collect articles now, but title selection is recommended first.")

st.markdown("---")

tab_search, tab_collection = st.tabs(["1. Search and Add", f"2. My Collection ({collected_count})"])

with tab_search:
    search_mode = st.radio("Search Mode", ["Single Search", "Search Queue"], horizontal=True)

    with st.expander("Advanced query builder", expanded=False):
        base_query = st.text_input("Base topic", value=chosen_title or project_topic, key="ca_base_query")
        required = st.text_input("Required terms", placeholder="comma-separated", key="ca_required_terms")
        optional = st.text_input("Optional terms", placeholder="comma-separated OR terms", key="ca_optional_terms")
        excluded = st.text_input("Excluded terms", placeholder="comma-separated NOT terms", key="ca_excluded_terms")
        built_query = build_query(base_query, required, optional, excluded)
        st.code(built_query or chosen_title or project_topic, language="text")

    col1, col2, col3 = st.columns(3)
    with col1:
        year_from = st.number_input("Published From", min_value=1900, max_value=2030, value=2000, step=1, key="ca_year")
    with col2:
        max_per_source = st.select_slider("Max per source", options=[10, 20, 30, 50, 100, 150, 200], value=50, key="ca_max")
    with col3:
        st.markdown("**Sources**")
        use_openalex = st.checkbox("OpenAlex", value=True, key="ca_oa")
        use_pubmed = st.checkbox("PubMed", value=True, key="ca_pm")
        use_s2 = st.checkbox("Semantic Scholar", value=True, key="ca_s2")

    st.markdown("**Title keyword filter**")
    kw_col1, kw_col2 = st.columns([3, 1])
    with kw_col1:
        title_keyword = st.text_input("Keywords, comma-separated. Leave blank to save all.", value="", key="ca_title_kw")
    with kw_col2:
        title_match_mode_label = st.radio("Match", ["Any", "All"], horizontal=True, key="ca_title_kw_mode")
        title_match_mode = "all" if title_match_mode_label == "All" else "any"

    search_settings = dict(
        max_per_source=max_per_source,
        year_from=int(year_from),
        use_openalex=use_openalex,
        use_pubmed=use_pubmed,
        use_s2=use_s2,
    )

    if search_mode == "Single Search":
        with st.form("ca_single"):
            query = st.text_input("Search Query", value=built_query or chosen_title or project_topic)
            go = st.form_submit_button("Search", type="primary")
        if go and query.strip():
            with st.spinner("Searching sources..."):
                unique, errors = run_article_search_with_status(query, **search_settings)
            added, skipped = save_to_collection(unique, selected_id, title_keyword, title_match_mode)
            st.success(f"{len(unique)} found; {added} new saved; {skipped} skipped by title filter.")
            if errors:
                for source, message in errors.items():
                    st.warning(f"{source}: {message}")
            st.rerun()
    else:
        active_job = st.session_state.get("ca_job_id")
        # If session_state was wiped (e.g. browser refresh), try to re-attach
        # to any background job still running for this project.
        if not active_job:
            recovered = find_active_job(selected_id, "articles")
            if recovered:
                st.session_state.ca_job_id = recovered
                active_job = recovered
        if active_job:
            @st.fragment(run_every=2)
            def _ca_progress():
                status = get_status(active_job)
                if status is None:
                    st.session_state.pop("ca_job_id", None)
                    st.rerun()
                    return
                pct = status["completed"] / status["total"] if status["total"] else 0
                st.progress(pct, text=f"{status['completed']}/{status['total']} searches completed")
                if status.get("current_query") and not status["done"]:
                    st.caption(f"Searching: `{status['current_query']}`")
                for line in status["log"]:
                    st.markdown(line)
                if status["done"]:
                    if status.get("error"):
                        st.error(f"Error: {status['error']}")
                    else:
                        st.success(f"Done. {status['total_added']} new articles saved.")
                    clear_job(active_job)
                    st.session_state.pop("ca_job_id", None)
                    st.rerun()
            _ca_progress()
            if st.button("Cancel", type="secondary"):
                clear_job(active_job)
                st.session_state.pop("ca_job_id", None)
                st.rerun()
        else:
            saved_q = load_queues(selected_id)
            topic = chosen_title or project_topic or "your topic"
            fallback = "\n".join([topic, f"{topic} mechanism", f"{topic} applications", f"{topic} methods"])
            current_text = saved_q["ca"] or fallback
            queue_text = st.text_area("Search queries, one per line", value=current_text, height=250)
            if queue_text != current_text:
                save_ca_queue(selected_id, queue_text)
            queries = [q.strip() for q in queue_text.splitlines() if q.strip()]
            st.caption(f"{len(queries)} queries. Auto-saved.")
            if st.button("Run All Searches", type="primary", disabled=not queries):
                job_id = start_job(
                    queries=queries,
                    settings=search_settings,
                    mode="articles",
                    project_id=selected_id,
                    title_keyword=title_keyword,
                    title_match_mode=title_match_mode,
                )
                st.session_state.ca_job_id = job_id
                st.rerun()

    st.markdown("---")
    uploaded = st.file_uploader("Import references into collection", type=["csv", "bib", "ris", "txt"])
    if uploaded and st.button("Import Uploaded References"):
        refs = parse_reference_upload(uploaded.name, uploaded.getvalue())
        added, skipped = save_to_collection(refs, selected_id, imported_from="Import")
        st.success(f"Imported {len(refs)} records; {added} new saved; {skipped} skipped.")
        st.rerun()

with tab_collection:
    if collected_count == 0:
        st.info("No articles collected yet. Use search or import references.")
    else:
        session = new_session()
        try:
            source_counts = (
                session.query(CollectedArticle.source, func.count(CollectedArticle.id))
                .filter_by(project_id=selected_id)
                .group_by(CollectedArticle.source)
                .all()
            )
            status_counts = (
                session.query(CollectedArticle.screening_status, func.count(CollectedArticle.id))
                .filter_by(project_id=selected_id)
                .group_by(CollectedArticle.screening_status)
                .all()
            )
        finally:
            session.close()

        st.subheader("PRISMA-style Counts")
        count_cols = st.columns(max(1, len(status_counts)))
        for i, (status, count) in enumerate(status_counts):
            count_cols[i].metric(status or "identified", count)

        st.subheader("Source Breakdown")
        source_cols = st.columns(len(source_counts) + 1)
        source_cols[0].metric("Total", collected_count)
        for i, (src, cnt) in enumerate(source_counts, 1):
            source_cols[i].metric(src, cnt)

        st.markdown("---")
        filter_kw = st.text_input("Filter by keyword in title", key="ca_filter")
        status_filter = st.selectbox("Screening status", ["all"] + STATUSES)
        tag_filter = st.text_input("Filter by tag", key="ca_tag_filter")
        page = st.session_state.get("ca_page", 0)

        session = new_session()
        try:
            q = session.query(CollectedArticle).filter_by(project_id=selected_id)
            if filter_kw:
                q = q.filter(CollectedArticle.title.ilike(f"%{filter_kw}%"))
            if status_filter != "all":
                q = q.filter(CollectedArticle.screening_status == status_filter)
            if tag_filter:
                q = q.filter(CollectedArticle.tags.ilike(f"%{tag_filter}%"))
            total_filtered = q.count()
            # All filtered articles (for download).
            all_articles = q.order_by(CollectedArticle.year.desc()).all()
            articles = all_articles[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
            rows = [
                {
                    "ID": a.id,
                    "Title": a.title,
                    "Year": a.year or "",
                    "Authors": (a.authors or "")[:80],
                    "Source": a.source,
                    "Status": a.screening_status or "identified",
                    "Tags": a.tags or "",
                    "PDF": "yes" if a.pdf_path else "",
                }
                for a in articles
            ]
            json_bytes = articles_to_json(all_articles).encode("utf-8")
        finally:
            session.close()

        st.download_button(
            f"Download all matching as JSON ({total_filtered})",
            data=json_bytes,
            file_name=f"{project_name.replace(' ', '_')}_collection.json",
            mime="application/json",
        )

        total_pages = max(1, (total_filtered + PAGE_SIZE - 1) // PAGE_SIZE)
        st.caption(f"Showing page {page + 1} of {total_pages}. Select a row to edit it.")
        event = st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )

        selected_rows = event.selection.rows if event and event.selection else []
        if selected_rows:
            selected = rows[selected_rows[0]]
            session = new_session()
            try:
                art = session.get(CollectedArticle, selected["ID"])
                with st.form(f"edit_article_{art.id}"):
                    st.markdown(f"#### {art.title}")
                    st.caption(f"{art.authors or ''} | {art.year or ''} | {art.source or ''}")
                    st.markdown(art.abstract or "*No abstract available.*")
                    status = st.selectbox("Screening Status", STATUSES, index=STATUSES.index(art.screening_status or "identified"))
                    tags = st.text_input("Tags", value=art.tags or "", placeholder="methods, clinical, key paper")
                    reason = st.text_area("Decision Reason", value=art.decision_reason or "", height=80)
                    notes = st.text_area("Notes", value=art.notes or "", height=100)
                    pdf = st.file_uploader("Attach PDF", type=["pdf"], key=f"pdf_{art.id}")
                    c1, c2 = st.columns(2)
                    with c1:
                        save = st.form_submit_button("Save Article", type="primary")
                    with c2:
                        delete = st.form_submit_button("Remove from Collection")
                    if save:
                        art.screening_status = status
                        art.tags = tags.strip()
                        art.decision_reason = reason.strip()
                        art.notes = notes.strip()
                        if pdf:
                            art.pdf_path = save_pdf(selected_id, art.id, pdf)
                        session.commit()
                        st.success("Article saved.")
                        st.rerun()
                    if delete:
                        session.delete(art)
                        session.commit()
                        st.success("Article removed.")
                        st.rerun()
                if art.pdf_path:
                    st.caption(f"PDF attached: {art.pdf_path}")
            finally:
                session.close()

        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            if st.button("Prev", disabled=page == 0, key="ca_prev"):
                st.session_state.ca_page = page - 1
                st.rerun()
        with c3:
            if st.button("Next", disabled=page >= total_pages - 1, key="ca_next"):
                st.session_state.ca_page = page + 1
                st.rerun()
