import pandas as pd
import streamlit as st

from database import Project, init_db, new_session
from utils.export import articles_to_bibtex, articles_to_csv, articles_to_json, articles_to_ris, project_report

st.set_page_config(page_title="Export", page_icon="EX", layout="wide")
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
    articles = list(project.collected_articles)
    landscape_articles = list(project.landscape_articles)
finally:
    session.close()

st.title("Export")
st.markdown(f"**Project:** {project.name}")
if project.chosen_title:
    st.markdown(f"**Review Title:** {project.chosen_title}")
st.markdown("---")

if not articles:
    st.info("No articles in your collection yet. Go to Collect Articles to add some.")
    st.stop()

safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in project.name).strip() or "review"

scope = st.radio("Export Scope", ["All collected", "Included only", "Eligible or included"], horizontal=True)
if scope == "Included only":
    export_articles = [a for a in articles if a.screening_status == "included"]
elif scope == "Eligible or included":
    export_articles = [a for a in articles if a.screening_status in {"eligible", "included"}]
else:
    export_articles = articles

st.markdown(f"**{len(export_articles)} articles** ready to export from **{len(articles)} collected**.")

status_counts = pd.Series([a.screening_status or "identified" for a in articles]).value_counts().reset_index()
status_counts.columns = ["Status", "Count"]

source_counts = pd.Series([a.source or "Unknown" for a in articles]).value_counts().reset_index()
source_counts.columns = ["Source", "Count"]

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("PRISMA-style Status")
    st.bar_chart(status_counts.set_index("Status"))
with col_b:
    st.subheader("Source Breakdown")
    st.bar_chart(source_counts.set_index("Source"))

st.markdown("---")
st.subheader("Download Files")

csv_data = articles_to_csv(export_articles)
bib_data = articles_to_bibtex(export_articles)
ris_data = articles_to_ris(export_articles)
json_data = articles_to_json(export_articles)
report_data = project_report(project, landscape_articles, export_articles)

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.download_button("CSV", data=csv_data, file_name=f"{safe_name}_articles.csv", mime="text/csv", type="primary")
with col2:
    st.download_button("BibTeX", data=bib_data, file_name=f"{safe_name}_articles.bib", mime="text/plain", type="primary")
with col3:
    st.download_button("RIS", data=ris_data, file_name=f"{safe_name}_articles.ris", mime="text/plain", type="primary")
with col4:
    st.download_button("JSON", data=json_data, file_name=f"{safe_name}_articles.json", mime="application/json", type="primary")
with col5:
    st.download_button("Report", data=report_data, file_name=f"{safe_name}_report.md", mime="text/markdown", type="primary")

st.markdown("---")
st.subheader("Article Preview")

rows = [
    {
        "Title": art.title,
        "Authors": art.authors,
        "Year": art.year or "",
        "Source": art.source,
        "DOI": art.doi or "",
        "Status": art.screening_status or "identified",
        "Tags": art.tags or "",
        "Notes": art.notes or "",
        "PDF": art.pdf_path or "",
    }
    for art in export_articles
]

st.dataframe(
    pd.DataFrame(rows),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Title": st.column_config.TextColumn("Title", width="large"),
        "Authors": st.column_config.TextColumn("Authors", width="medium"),
        "Year": st.column_config.NumberColumn("Year", format="%d"),
        "DOI": st.column_config.LinkColumn("DOI", display_text=r"https://doi\.org/(.+)"),
    },
)

with st.expander("Project Report Preview"):
    st.markdown(report_data)

