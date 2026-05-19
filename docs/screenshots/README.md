# Screenshots

This directory holds the screenshots embedded in the top-level [README.md](../../README.md).

## How to (re)generate them

1. Start the app: `streamlit run app.py`
2. Open <http://localhost:8501>.
3. Take **PNG** screenshots at 1280 × 800 (browser zoom 100%) of each step
   below and save them with these exact filenames so the README links
   continue to work:

| File | What to capture |
|---|---|
| `01_home.png` | The Home page: project list with at least one project, plus the "Create a new project" form |
| `02_search.png` | Workspace → 🔍 Search the web — show the "Multiple topics" mode with the queue text area populated |
| `03_library.png` | Workspace → 📚 Library — the PRISMA strip at the top + a row selected so the abstract panel and quick-decision buttons are visible |
| `04_extract.png` | Workspace → 🔗 Extract citations — mid-job, with the progress bar and the per-review log expander open |
| `05_duplicates.png` | Workspace → 📚 Library → bottom — the **🔎 Possible duplicates** expander showing a couple of duplicate group cards |

## Tips

- Pick a screen with no personally identifiable information showing.
- The Streamlit theme defaults are fine; no custom theming required.
- If your library is small, populate the screenshots from the Amide
  project; it has enough rows to make every panel non-trivial.
