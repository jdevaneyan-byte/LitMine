from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import func

from ai.claude_client import get_client, stream_landscape_analysis, stream_relevance_filter, suggest_search_strategy
from database import LandscapeAnalysis, LandscapeArticle, Project, init_db, new_session
from utils.export import articles_to_json
from utils.import_refs import parse_reference_upload
from utils.queue_store import load_queues, save_ls_queue
from utils.search_job import clear_job, find_active_job, get_status, start_job
from utils.search_query import build_query
from utils.search_runner import run_review_search_with_status

st.set_page_config(page_title="Landscape Scan", page_icon="LS", layout="wide")
init_db()

PAGE_SIZE = 50
DECISIONS = ["unscreened", "include", "maybe", "exclude"]


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


def save_articles_to_landscape(
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
            for a in session.query(LandscapeArticle).filter_by(project_id=project_id).all()
            if a.doi
        }
        existing_titles = {
            (a.title or "").strip().lower()
            for a in session.query(LandscapeArticle).filter_by(project_id=project_id).all()
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
                LandscapeArticle(
                    project_id=project_id,
                    title=title,
                    doi=art.get("doi", ""),
                    abstract=art.get("abstract", ""),
                    authors=art.get("authors", ""),
                    year=art.get("year"),
                    source=imported_from or art.get("source", "Import"),
                    url=art.get("url", ""),
                    decision="unscreened",
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


selected_id = load_project_selector()

session = new_session()
try:
    project = session.get(Project, selected_id)
    project_name = project.name
    project_topic = project.topic
    project_review_type = project.review_type or "Narrative review"
    saved_analysis = project.analysis.full_text if project.analysis else ""
    landscape_count = session.query(LandscapeArticle).filter_by(project_id=selected_id).count()
    relevant_count = session.query(LandscapeArticle).filter_by(project_id=selected_id, is_relevant=True).count()
    filtered_ever = session.query(LandscapeArticle).filter(
        LandscapeArticle.project_id == selected_id,
        LandscapeArticle.is_relevant != None,
    ).count()
finally:
    session.close()

st.title("Landscape Scan")
st.markdown(f"**Project:** {project_name} | **Topic:** `{project_topic}`")
st.markdown("---")

with st.expander("Project settings and criteria"):
    session = new_session()
    try:
        p = session.get(Project, selected_id)
        with st.form("project_settings"):
            review_type = st.selectbox(
                "Review Type",
                ["Narrative review", "Scoping review", "Systematic review", "Meta-analysis", "Rapid review"],
                index=max(0, ["Narrative review", "Scoping review", "Systematic review", "Meta-analysis", "Rapid review"].index(p.review_type or "Narrative review"))
                if (p.review_type or "Narrative review") in ["Narrative review", "Scoping review", "Systematic review", "Meta-analysis", "Rapid review"]
                else 0,
            )
            inclusion = st.text_area("Inclusion Criteria", value=p.inclusion_criteria or "", height=80)
            exclusion = st.text_area("Exclusion Criteria", value=p.exclusion_criteria or "", height=80)
            strategy = st.text_area("Search Strategy Notes", value=p.search_strategy or "", height=100)
            if st.form_submit_button("Save Settings", type="primary"):
                p.review_type = review_type
                p.inclusion_criteria = inclusion.strip()
                p.exclusion_criteria = exclusion.strip()
                p.search_strategy = strategy.strip()
                p.updated_at = datetime.now(timezone.utc)
                session.commit()
                st.success("Project settings saved.")
                st.rerun()
    finally:
        session.close()

relevant_label = f" | {relevant_count} relevant" if filtered_ever else ""
tab_search, tab_saved, tab_analysis = st.tabs(
    ["1. Search", f"2. Saved Reviews ({landscape_count}{relevant_label})", "3. AI Analysis"]
)

with tab_search:
    search_mode = st.radio("Search Mode", ["Single Search", "Search Queue"], horizontal=True)

    with st.expander("Advanced query builder", expanded=False):
        base_query = st.text_input("Base topic", value=project_topic, key="ls_base_query")
        required = st.text_input("Required terms", placeholder="comma-separated", key="ls_required_terms")
        optional = st.text_input("Optional terms", placeholder="comma-separated OR terms", key="ls_optional_terms")
        excluded = st.text_input("Excluded terms", placeholder="comma-separated NOT terms", key="ls_excluded_terms")
        built_query = build_query(base_query, required, optional, excluded, search_reviews=True)
        st.code(built_query or project_topic, language="text")

    col1, col2, col3 = st.columns(3)
    with col1:
        year_from = st.number_input("Published From", min_value=1900, max_value=2030, value=2019, step=1)
    with col2:
        max_per_source = st.select_slider("Max per source", options=[10, 20, 30, 50, 100], value=30)
    with col3:
        st.markdown("**Sources**")
        use_openalex = st.checkbox("OpenAlex", value=True, key="ls_oa")
        use_pubmed = st.checkbox("PubMed", value=True, key="ls_pm")
        use_s2 = st.checkbox("Semantic Scholar", value=True, key="ls_s2")

    st.markdown("**Title keyword filter**")
    kw_col1, kw_col2 = st.columns([3, 1])
    with kw_col1:
        title_keyword = st.text_input(
            "Keywords, comma-separated. Leave blank to save all.",
            value=project_topic.split()[0] if project_topic else "",
            key="ls_title_kw",
        )
    with kw_col2:
        title_match_mode_label = st.radio("Match", ["Any", "All"], horizontal=True, key="ls_title_kw_mode")
        title_match_mode = "all" if title_match_mode_label == "All" else "any"

    search_settings = dict(
        max_per_source=max_per_source,
        year_from=int(year_from),
        use_openalex=use_openalex,
        use_pubmed=use_pubmed,
        use_s2=use_s2,
    )

    if search_mode == "Single Search":
        with st.form("ls_single"):
            query = st.text_input("Search Query", value=built_query or project_topic)
            go = st.form_submit_button("Search", type="primary")
        if go and query.strip():
            with st.spinner("Searching sources..."):
                unique, errors = run_review_search_with_status(query, **search_settings)
            added, skipped = save_articles_to_landscape(unique, selected_id, title_keyword, title_match_mode)
            st.success(f"{len(unique)} found; {added} new saved; {skipped} skipped by title filter.")
            if errors:
                for source, message in errors.items():
                    st.warning(f"{source}: {message}")
            st.rerun()
    else:
        active_job = st.session_state.get("ls_job_id")
        # Recover from session_state loss (e.g. browser refresh) by scanning
        # the on-disk job dir for any background job still running.
        if not active_job:
            recovered = find_active_job(selected_id, "reviews")
            if recovered:
                st.session_state.ls_job_id = recovered
                active_job = recovered
        if active_job:
            @st.fragment(run_every=2)
            def _ls_progress():
                status = get_status(active_job)
                if status is None:
                    st.session_state.pop("ls_job_id", None)
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
                    st.session_state.pop("ls_job_id", None)
                    st.rerun()
            _ls_progress()
            if st.button("Cancel", type="secondary"):
                clear_job(active_job)
                st.session_state.pop("ls_job_id", None)
                st.rerun()
        else:
            saved_q = load_queues(selected_id)
            topic = project_topic or "your topic"
            fallback = "\n".join([topic, f"{topic} review", f"{topic} synthesis", f"{topic} recent advances"])
            current_text = saved_q["ls"] or fallback
            queue_text = st.text_area("Search queries, one per line", value=current_text, height=220)
            if queue_text != current_text:
                save_ls_queue(selected_id, queue_text)
            queries = [q.strip() for q in queue_text.splitlines() if q.strip()]
            st.caption(f"{len(queries)} queries. Auto-saved.")
            if st.button("Run All Searches", type="primary", disabled=not queries):
                job_id = start_job(
                    queries=queries,
                    settings=search_settings,
                    mode="reviews",
                    project_id=selected_id,
                    title_keyword=title_keyword,
                    title_match_mode=title_match_mode,
                )
                st.session_state.ls_job_id = job_id
                st.rerun()

    st.markdown("---")
    uploaded = st.file_uploader("Import review references for the landscape set", type=["csv", "bib", "ris", "txt"])
    if uploaded and st.button("Import Uploaded References"):
        refs = parse_reference_upload(uploaded.name, uploaded.getvalue())
        added, skipped = save_articles_to_landscape(refs, selected_id, imported_from="Import")
        st.success(f"Imported {len(refs)} records; {added} new saved; {skipped} skipped.")
        st.rerun()

with tab_saved:
    if landscape_count == 0:
        st.info("No reviews saved yet. Run a search or import references.")
    else:
        session = new_session()
        try:
            source_counts = (
                session.query(LandscapeArticle.source, func.count(LandscapeArticle.id))
                .filter_by(project_id=selected_id)
                .group_by(LandscapeArticle.source)
                .all()
            )
        finally:
            session.close()

        metric_cols = st.columns(len(source_counts) + 1 + (1 if filtered_ever else 0))
        metric_cols[0].metric("Total", landscape_count)
        for i, (src, cnt) in enumerate(source_counts, 1):
            metric_cols[i].metric(src, cnt)
        if filtered_ever:
            metric_cols[-1].metric("Relevant (AI)", relevant_count)

        filter_kw = st.text_input("Filter by keyword in title", key="ls_filter")
        decision_filter = st.selectbox("Decision filter", ["all"] + DECISIONS)
        show_relevant_only = st.checkbox("Relevant AI only", value=False, disabled=not bool(filtered_ever))
        page = st.session_state.get("ls_page", 0)

        session = new_session()
        try:
            q = session.query(LandscapeArticle).filter_by(project_id=selected_id)
            if show_relevant_only:
                q = q.filter(LandscapeArticle.is_relevant == True)
            if decision_filter != "all":
                q = q.filter(LandscapeArticle.decision == decision_filter)
            if filter_kw:
                q = q.filter(LandscapeArticle.title.ilike(f"%{filter_kw}%"))
            total_filtered = q.count()
            # All filtered articles (for download). Same query, no pagination.
            all_articles = q.order_by(LandscapeArticle.year.desc()).all()
            # Current page slice (for the table only).
            articles = all_articles[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
            rows = [
                {
                    "ID": a.id,
                    "Title": a.title,
                    "Year": a.year or "",
                    "Authors": (a.authors or "")[:80],
                    "Source": a.source,
                    "Decision": a.decision or "unscreened",
                    "AI Relevant": "yes" if a.is_relevant else ("no" if a.is_relevant is False else ""),
                    "Tags": a.tags or "",
                }
                for a in articles
            ]
            download_payload = articles_to_json(all_articles, include_relevance=True).encode("utf-8")
        finally:
            session.close()

        st.download_button(
            f"Download Landscape JSON (all {total_filtered} matching)",
            data=download_payload,
            file_name=f"{project_name.replace(' ', '_')}_landscape.json",
            mime="application/json",
        )

        total_pages = max(1, (total_filtered + PAGE_SIZE - 1) // PAGE_SIZE)
        st.caption(f"Showing page {page + 1} of {total_pages}. Select a row to screen it.")
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
                art = session.get(LandscapeArticle, selected["ID"])
                with st.form(f"screen_landscape_{art.id}"):
                    st.markdown(f"#### {art.title}")
                    st.caption(f"{art.authors or ''} | {art.year or ''} | {art.source or ''}")
                    st.markdown(art.abstract or "*No abstract available.*")
                    decision = st.selectbox("Manual Decision", DECISIONS, index=DECISIONS.index(art.decision or "unscreened"))
                    tags = st.text_input("Tags", value=art.tags or "", placeholder="methods, background, gap")
                    reason = st.text_area("Decision Reason", value=art.decision_reason or "", height=80)
                    notes = st.text_area("Notes", value=art.notes or "", height=100)
                    c1, c2 = st.columns(2)
                    with c1:
                        save = st.form_submit_button("Save Screening", type="primary")
                    with c2:
                        delete = st.form_submit_button("Remove from Landscape")
                    if save:
                        art.decision = decision
                        art.tags = tags.strip()
                        art.decision_reason = reason.strip()
                        art.notes = notes.strip()
                        session.commit()
                        st.success("Screening saved.")
                        st.rerun()
                    if delete:
                        session.delete(art)
                        session.commit()
                        st.success("Article removed.")
                        st.rerun()
            finally:
                session.close()

        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            if st.button("Prev", disabled=page == 0, key="ls_prev"):
                st.session_state.ls_page = page - 1
                st.rerun()
        with c3:
            if st.button("Next", disabled=page >= total_pages - 1, key="ls_next"):
                st.session_state.ls_page = page + 1
                st.rerun()

with tab_analysis:
    if landscape_count == 0:
        st.warning("Save some review articles first.")
    else:
        try:
            get_client()
            api_ok = True
        except ValueError:
            api_ok = False

        if not api_ok:
            st.error("ANTHROPIC_API_KEY not found. Add it to your .env file and restart.")
        else:
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if st.button("Analyze Landscape", type="primary", use_container_width=True):
                    session = new_session()
                    try:
                        arts = session.query(LandscapeArticle).filter_by(project_id=selected_id).all()
                        art_dicts = [{"title": a.title, "abstract": a.abstract, "year": a.year} for a in arts]
                    finally:
                        session.close()
                    box = st.empty()
                    full_text = ""
                    with st.spinner("Analyzing..."):
                        for chunk in stream_landscape_analysis(art_dicts):
                            full_text += chunk
                            box.markdown(full_text)
                    session = new_session()
                    try:
                        ana = session.query(LandscapeAnalysis).filter_by(project_id=selected_id).first()
                        if ana:
                            ana.full_text = full_text
                            ana.updated_at = datetime.now(timezone.utc)
                        else:
                            session.add(LandscapeAnalysis(project_id=selected_id, full_text=full_text))
                        p = session.get(Project, selected_id)
                        if p and p.stage < 2:
                            p.stage = 2
                        session.commit()
                        st.success("Analysis saved.")
                    finally:
                        session.close()
            with col_b:
                if st.button("Filter by Relevance", use_container_width=True):
                    session = new_session()
                    try:
                        arts = session.query(LandscapeArticle).filter_by(project_id=selected_id).all()
                        art_dicts = [{"id": a.id, "title": a.title, "abstract": a.abstract, "year": a.year} for a in arts]
                    finally:
                        session.close()
                    import json as _json

                    progress_box = st.empty()
                    full_log = ""
                    relevance_map: dict[int, bool] = {}
                    with st.spinner("Filtering..."):
                        for chunk in stream_relevance_filter(art_dicts, project_topic):
                            full_log += chunk
                            if "```json" in full_log:
                                try:
                                    json_part = full_log.split("```json")[1].split("```")[0].strip()
                                    relevance_map = {int(k): v for k, v in _json.loads(json_part).items()}
                                except Exception:
                                    pass
                            progress_box.markdown(full_log.split("```json")[0])
                    if relevance_map:
                        session = new_session()
                        try:
                            for art_id, is_rel in relevance_map.items():
                                a = session.get(LandscapeArticle, art_id)
                                if a:
                                    a.is_relevant = is_rel
                            session.commit()
                            st.success(f"Filter saved. {sum(1 for v in relevance_map.values() if v)} relevant.")
                            st.rerun()
                        finally:
                            session.close()
                    else:
                        st.warning("No classification results received.")
            with col_c:
                if st.button("Suggest Search Strategy", use_container_width=True):
                    box = st.empty()
                    full_text = ""
                    with st.spinner("Generating strategy..."):
                        for chunk in suggest_search_strategy(project_topic, "", project_review_type):
                            full_text += chunk
                            box.markdown(full_text)
                    session = new_session()
                    try:
                        p = session.get(Project, selected_id)
                        p.ai_search_strategy = full_text
                        p.search_strategy = full_text
                        p.updated_at = datetime.now(timezone.utc)
                        session.commit()
                        st.success("AI search strategy saved to project settings.")
                    finally:
                        session.close()

        if saved_analysis:
            st.markdown("#### Previously Saved Analysis")
            st.markdown(saved_analysis)
