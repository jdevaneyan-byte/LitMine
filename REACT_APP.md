# LitMine — React app (v2, experimental)

LitMine ships **two** frontends over the same local SQLite database:

| Frontend | Stack | When to use |
|---|---|---|
| **Streamlit** (`app.py`, `pages/`) | Python | The stable, published v1 — search, import, extract, screen, export |
| **React** (`backend/` + `frontend/`) | FastAPI + Next.js | The richer v2 — reading/review workspace + interactive citation network |

Both read and write the *same* `litmine.db`, so you can use whichever you
prefer; data stays in sync.

## Running the React app

You need **two processes**: the FastAPI backend and the Next.js frontend.

### 1. Backend (FastAPI)

From the project root, with the Python venv active:

```bash
pip install -r requirements.txt
pip install -r backend/requirements.txt
uvicorn backend.main:app --port 8000
```

- API: <http://localhost:8000>
- Interactive docs: <http://localhost:8000/docs>

### 2. Frontend (Next.js)

In a second terminal:

```bash
cd frontend
npm install      # first time only
npm run dev
```

Open <http://localhost:3000>.

> Start the backend first; the frontend calls it at `http://localhost:8000`
> (override with `frontend/.env.local` → `NEXT_PUBLIC_API_BASE`).

## What the React app does

- **Project list** — every project with library / review / cited counts.
- **Library tab** — filter (title, decision) and paginate the collection.
- **Read & review tab** — two-pane reader: article list on the left; full
  metadata, abstract and on-demand reference list on the right; inline manual
  editing and one-click screening decisions. Any manual edit flags the row as
  **user-edited** (audited).
- **Network map tab** — three-pane interactive graph (Cytoscape.js) with three
  modes:
  - **Citation** — reviews → the papers they cite; node size = how many
    reviews cite it ("cited more").
  - **Authors** — co-authorship; node size = papers.
  - **Journals** — a review's journal → the venues it cites.

All network data is built from rows already in the database — no extra API
calls.

## Notes

- This is a v2 in active development; the Streamlit app remains the reference
  implementation for the paper/release.
- Node.js 18+ is required for the frontend.
- `frontend/node_modules` and `.next` are gitignored; run `npm install` after
  cloning.
