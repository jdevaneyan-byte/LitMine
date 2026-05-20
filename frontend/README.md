# LitMine frontend (Next.js)

Enterprise-style React UI for LitMine. Talks to the FastAPI backend
(`../backend`) over JSON. Reading/review and the citation network map are
built on top of the same local database the Streamlit app uses.

Stack: Next.js 16 (App Router) · React 19 · TypeScript · Tailwind v4.

## Run (needs the backend running too)

```bash
# 1. Backend (from the project root, venv active)
uvicorn backend.main:app --port 8000

# 2. Frontend (this folder)
npm install
npm run dev
```

Open <http://localhost:3000>.

The API base URL defaults to `http://localhost:8000` and can be overridden
in `.env.local`:

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

## Status

- ✅ Phase 2 — project list + Library table (filter, paginate)
- ⬜ Phase 3 — reading / review 2-pane with manual edit + audit
- ⬜ Phase 4 — network map (citation / author / journal)
