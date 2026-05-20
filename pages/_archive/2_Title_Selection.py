from datetime import datetime, timezone

import streamlit as st

from database import Project, init_db, new_session

st.set_page_config(page_title="Title Selection", page_icon="TS", layout="wide")
init_db()

st.sidebar.title("LitMine")
st.sidebar.markdown("---")

session = new_session()
try:
    all_projects = session.query(Project).order_by(Project.created_at.desc()).all()
    project_map = {p.id: p.name for p in all_projects}
finally:
    session.close()

if not project_map:
    st.warning("No projects found. Please create one on the Home page first.")
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

session = new_session()
try:
    project = session.get(Project, selected_id)
    current_title = project.chosen_title or ""
    saved_analysis = project.analysis.full_text if project.analysis else ""
    landscape_count = len(project.landscape_articles)
    included_count = len([a for a in project.landscape_articles if a.decision == "include" or a.is_relevant is True])
finally:
    session.close()

st.title("Title Selection")
st.markdown(f"**Project:** {project.name} | **Topic:** `{project.topic}`")
st.markdown("---")

if landscape_count == 0:
    st.warning("You have not run a landscape scan yet. A title is better after collecting existing review articles.")
elif not saved_analysis:
    st.info(f"{landscape_count} landscape records are saved. Run AI analysis in Landscape Scan for gap-based title ideas.")
else:
    with st.expander("View Landscape Analysis", expanded=not bool(current_title)):
        st.markdown(saved_analysis)

if project.ai_search_strategy:
    with st.expander("View Saved AI Search Strategy"):
        st.markdown(project.ai_search_strategy)

st.markdown("---")
st.subheader("Choose Your Review Title")

if current_title:
    st.success(f"Current title: {current_title}")

st.caption(
    f"Landscape records: {landscape_count}. Included or AI-relevant records: {included_count}. "
    "Use the rationale field to preserve why this title fits the gap."
)

with st.form("title_form"):
    new_title = st.text_input(
        "Your Review Article Title",
        value=current_title,
        placeholder="e.g. Deep Learning for Early Detection of Diabetic Retinopathy: A Systematic Review",
    )
    notes = st.text_area(
        "Title Rationale / Gap",
        value=project.description or "",
        placeholder="Why did you choose this title? What gap does it address?",
        height=120,
    )
    save_btn = st.form_submit_button("Save Title", type="primary")

    if save_btn:
        if not new_title.strip():
            st.error("Title cannot be empty.")
        else:
            session = new_session()
            try:
                proj = session.get(Project, selected_id)
                proj.chosen_title = new_title.strip()
                proj.description = notes.strip()
                proj.updated_at = datetime.now(timezone.utc)
                if proj.stage < 3:
                    proj.stage = 3
                session.commit()
                st.success("Title saved. Continue to Collect Articles.")
                st.rerun()
            finally:
                session.close()

if current_title:
    st.markdown("---")
    st.markdown("Next step: go to Collect Articles to gather and screen primary references.")

