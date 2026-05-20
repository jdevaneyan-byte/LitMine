"""Home page — project list + create a new project.

Simplified for first-time users: just a name, a type (Review articles /
Research articles / both), and an optional description. Everything else is
configured inside the project workspace.
"""

from datetime import datetime, timezone

import streamlit as st

from database import (
    CitedArticle,
    CollectedArticle,
    CuratedReview,
    LandscapeArticle,
    Project,
    init_db,
    new_session,
)

st.set_page_config(
    page_title="LitMine",
    page_icon="LM",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

LITERATURE_TYPES = ["Review + research articles", "Review articles", "Research articles"]
LITERATURE_TYPE_HELP = (
    "What kind of literature you mainly want to find.\n\n"
    "• **Review articles** — review / overview articles\n"
    "• **Research articles** — primary research articles\n"
    "• **Review + research articles** — search for both"
)


# Sidebar

st.sidebar.title("LitMine")
st.sidebar.caption("Find, organise and download academic literature for your research group.")
st.sidebar.markdown("---")
st.sidebar.markdown(
    "**How it works**\n\n"
    "1. Create a project below\n"
    "2. Open the project's **Workspace** to search, import, screen, and download"
)


# Main

st.title("LitMine")
st.markdown(
    "A simple workspace for academic literature: search the web databases "
    "(OpenAlex, PubMed, Semantic Scholar), import your existing reference lists, "
    "extract citations from review papers, screen results, and download to Excel."
)
st.markdown("---")


# Create new project

st.subheader("Create a new project")
with st.form("new_project_form", clear_on_submit=True):
    cols = st.columns([2, 1])
    with cols[0]:
        project_name = st.text_input(
            "Project name",
            placeholder="e.g. CO2 reduction catalysts",
            help="A short, memorable name. You can rename later.",
        )
    with cols[1]:
        literature_type = st.selectbox(
            "Looking for",
            LITERATURE_TYPES,
            index=0,
            help=LITERATURE_TYPE_HELP,
        )

    topic = st.text_input(
        "Topic / main keyword",
        placeholder="e.g. electrochemical CO2 reduction copper catalysts",
        help="Used as the default seed for searches. You can change it any time inside the project.",
    )
    description = st.text_area(
        "Description (optional)",
        placeholder="Brief context for yourself or collaborators.",
        height=70,
        help="Optional. Notes about the goal of this project.",
    )

    submitted = st.form_submit_button("Create project", type="primary")
    if submitted:
        if not project_name.strip():
            st.error("Project name is required.")
        else:
            session = new_session()
            try:
                project = Project(
                    name=project_name.strip(),
                    topic=(topic.strip() or project_name.strip()),
                    description=description.strip(),
                    literature_type=literature_type,
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(project)
                session.commit()
                st.session_state.active_project_id = project.id
                st.success(f"Project '{project_name}' created. Open the **Workspace** in the sidebar.")
                st.rerun()
            finally:
                session.close()


# Existing projects

st.markdown("---")
st.subheader("Your projects")

session = new_session()
try:
    projects = session.query(Project).order_by(Project.created_at.desc()).all()
    project_summaries = []
    for p in projects:
        project_summaries.append(
            {
                "id": p.id,
                "name": p.name,
                "topic": p.topic,
                "literature_type": p.literature_type or "Review + research articles",
                "description": p.description or "",
                "collected": session.query(CollectedArticle).filter_by(project_id=p.id).count(),
                "landscape": session.query(LandscapeArticle).filter_by(project_id=p.id).count(),
                "curated_reviews": session.query(CuratedReview).filter_by(project_id=p.id).count(),
                "cited": session.query(CitedArticle).filter_by(project_id=p.id).count(),
            }
        )
finally:
    session.close()

if not project_summaries:
    st.info("No projects yet. Create one above to get started.")
else:
    for s in project_summaries:
        is_active = st.session_state.get("active_project_id") == s["id"]
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 3, 2, 1])
            with c1:
                st.markdown(f"### {s['name']}")
                st.caption(f"Looking for: **{s['literature_type']}**")
                if s["description"]:
                    st.caption(s["description"])
            with c2:
                st.caption(f"Topic: `{s['topic']}`")
                total_library = s["collected"] + s["landscape"]
                bits = [f"📚 Library: **{total_library}**"]
                if s["curated_reviews"]:
                    bits.append(f"📑 Curated reviews: **{s['curated_reviews']}**")
                if s["cited"]:
                    bits.append(f"🔗 Cited refs: **{s['cited']}**")
                st.markdown(" · ".join(bits))
            with c3:
                if is_active:
                    st.success("Active project")
                else:
                    st.caption("Click *Open* to make this the active project.")
            with c4:
                if st.button(
                    "Active" if is_active else "Open",
                    key=f"open_{s['id']}",
                    type="secondary" if is_active else "primary",
                    use_container_width=True,
                ):
                    st.session_state.active_project_id = s["id"]
                    st.rerun()
                if st.button(
                    "Delete",
                    key=f"del_{s['id']}",
                    help="Permanently delete this project and all its data.",
                    use_container_width=True,
                ):
                    st.session_state[f"confirm_delete_{s['id']}"] = True

                if st.session_state.get(f"confirm_delete_{s['id']}"):
                    st.warning("Confirm delete?")
                    if st.button("Yes, delete", key=f"confirm_{s['id']}", use_container_width=True):
                        session = new_session()
                        try:
                            p = session.get(Project, s["id"])
                            if p:
                                session.delete(p)
                                session.commit()
                            if st.session_state.get("active_project_id") == s["id"]:
                                st.session_state.active_project_id = None
                            st.session_state.pop(f"confirm_delete_{s['id']}", None)
                            st.rerun()
                        finally:
                            session.close()
