# LitMine backend (FastAPI)

JSON API over the same local SQLite database the Streamlit app uses. Powers
the React frontend (`frontend/`). Reuses `database.py`, `api/`, and `utils/`.

## Run

From the project root (so imports resolve), with the project venv active:

```bash
pip install -r requirements.txt          # root deps (sqlalchemy, requests, ...)
pip install -r backend/requirements.txt  # fastapi + uvicorn
uvicorn backend.main:app --reload --port 8000
```

API root: <http://localhost:8000/api/health>
Interactive docs: <http://localhost:8000/docs>

The database location follows the `LITMINE_DB` env var (default `litmine.db`),
so the backend and the Streamlit app share one database by default.

## Endpoints (Phase 1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/projects` | list projects with counts |
| GET | `/api/projects/{id}` | project detail |
| GET | `/api/projects/{id}/articles` | paginated library (filters: q, decision, year_min, pub_type) |
| GET | `/api/articles/{id}?with_references=true` | full article; optional on-demand reference list |
| PATCH | `/api/articles/{id}` | manual edit (marks row as user-edited / audited) |
| GET | `/api/projects/{id}/network?mode=citation\|author\|journal` | graph nodes + edges for Cytoscape |
| GET | `/api/health` | health check |
