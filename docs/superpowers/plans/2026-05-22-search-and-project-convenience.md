# Search & Project Convenience — Batch 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the search keyword-parsing / cancel friction and add convenience features — live chip preview, project delete, inline rename + duplicate, and AI keyword expansion — to the LitMine literature workspace.

**Architecture:** A Next.js (App Router) frontend in `frontend/` talks to a FastAPI backend in `backend/main.py` backed by SQLAlchemy models in `database.py`. Search runs as a background thread job (`utils/search_job.py`) whose progress the UI polls. This plan adds a pure frontend parsing helper (unit-tested with Vitest), new FastAPI endpoints (unit-tested with `unittest` + `TestClient`), and UI affordances on the project cards and search panel.

**Tech Stack:** FastAPI, SQLAlchemy, pytest/unittest (backend); Next.js 16, React 19, TypeScript, Tailwind v4, lucide-react, Vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-05-22-search-and-project-convenience-design.md`

---

## File Structure

**Frontend**
- Create `frontend/src/lib/parseTerms.ts` — pure term-parsing helper (one responsibility).
- Create `frontend/src/lib/parseTerms.test.ts` — Vitest unit tests.
- Create `frontend/vitest.config.ts` — test runner config.
- Modify `frontend/package.json` — add Vitest devDeps + `test` script.
- Modify `frontend/src/components/SearchPanel.tsx` — use `parseTerms`, chip preview, cancel state, suggest button.
- Modify `frontend/src/lib/api.ts` — `deleteProject`, `renameProject`, `duplicateProject`, `suggestKeywords`.
- Modify `frontend/src/app/page.tsx` — card delete modal, inline rename, duplicate.

**Backend**
- Modify `backend/main.py` — comma-split in `start_search`; `DELETE`/`PATCH`/`duplicate` project endpoints; `keyword-suggest` endpoint; Pydantic schemas.
- Modify `ai/claude_client.py` — `suggest_keywords()`.
- Modify `tests/test_backend.py` — new API tests.

---

## Task 1: Frontend test setup + `parseTerms`

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/lib/parseTerms.ts`
- Test: `frontend/src/lib/parseTerms.test.ts`

- [ ] **Step 1: Add Vitest to package.json**

Add to `devDependencies`: `"vitest": "^3.2.4"`. Add to `scripts`: `"test": "vitest run"`.

- [ ] **Step 2: Install**

Run: `cd frontend && npm install`
Expected: installs vitest, exit 0.

- [ ] **Step 3: Create `frontend/vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
```

- [ ] **Step 4: Write the failing test** — `frontend/src/lib/parseTerms.test.ts`

```ts
import { describe, expect, it } from "vitest";
import { parseTerms } from "./parseTerms";

describe("parseTerms", () => {
  it("splits on newlines", () => {
    expect(parseTerms("a\nb\nc")).toEqual(["a", "b", "c"]);
  });
  it("splits on commas", () => {
    expect(parseTerms("a, b, c")).toEqual(["a", "b", "c"]);
  });
  it("splits on mixed commas and newlines", () => {
    expect(parseTerms("a, b\nc,d")).toEqual(["a", "b", "c", "d"]);
  });
  it("preserves multi-word phrases", () => {
    expect(parseTerms("liposomal drug delivery, nanoparticle")).toEqual([
      "liposomal drug delivery",
      "nanoparticle",
    ]);
  });
  it("strips numbered list markers", () => {
    expect(parseTerms("1. alpha, 2) beta\n3. gamma")).toEqual(["alpha", "beta", "gamma"]);
  });
  it("strips bullet markers", () => {
    expect(parseTerms("- alpha\n• beta\n* gamma")).toEqual(["alpha", "beta", "gamma"]);
  });
  it("trims whitespace and drops empties", () => {
    expect(parseTerms("  a  ,, \n , b ")).toEqual(["a", "b"]);
  });
  it("de-duplicates case-insensitively, keeping first casing", () => {
    expect(parseTerms("Alpha, alpha, ALPHA, beta")).toEqual(["Alpha", "beta"]);
  });
  it("returns [] for empty input", () => {
    expect(parseTerms("   ")).toEqual([]);
  });
});
```

- [ ] **Step 5: Run test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — cannot resolve `./parseTerms` / `parseTerms is not a function`.

- [ ] **Step 6: Implement `frontend/src/lib/parseTerms.ts`**

```ts
// Splits a free-text search box into clean, de-duplicated search terms.
// Splits on newlines AND commas (never spaces, so multi-word phrases survive),
// and strips leading list markers like "1.", "2)", "-", "•", "*".
const LIST_MARKER = /^\s*(\d+[.)]|[-*•])\s+/;

export function parseTerms(raw: string): string[] {
  if (!raw) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const piece of raw.split(/[\n,]/)) {
    const term = piece.replace(LIST_MARKER, "").trim();
    if (!term) continue;
    const key = term.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(term);
  }
  return out;
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS — 9 tests.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/lib/parseTerms.ts frontend/src/lib/parseTerms.test.ts
git commit -m "Add parseTerms helper + Vitest setup"
```

---

## Task 2: SearchPanel uses parseTerms + live chip preview

**Files:**
- Modify: `frontend/src/components/SearchPanel.tsx`

- [ ] **Step 1: Import parseTerms and derive parsed terms**

At the top of `SearchPanel.tsx`, add to imports:

```ts
import { parseTerms } from "@/lib/parseTerms";
import { X } from "lucide-react";
```

Inside the component, after the `queries` state is declared (around line 35), add:

```ts
const terms = parseTerms(queries);
const removeTerm = (idx: number) =>
  setQueries(terms.filter((_, i) => i !== idx).join("\n"));
```

- [ ] **Step 2: Use parseTerms in `run()`**

Replace the `qs` construction in `run()` (currently `queries.split("\n").map(...).filter(Boolean)` at lines 87-90) with:

```ts
const qs = parseTerms(queries);
```

- [ ] **Step 3: Update the helper text**

Change the label hint (line 125) from `(one per line — each runs across all sources)` to:

```tsx
(one per line or comma-separated — each runs across all sources)
```

- [ ] **Step 4: Render the chip preview**

Immediately after the `</textarea>` (line 133), insert:

```tsx
{terms.length > 0 && (
  <div className="mt-2 flex flex-wrap items-center gap-1.5">
    <span className="text-xs text-[var(--muted)]">
      {terms.length} term{terms.length === 1 ? "" : "s"}:
    </span>
    {terms.map((t, i) => (
      <span
        key={`${t}-${i}`}
        className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-2 py-0.5 text-xs"
      >
        {t}
        {!running && (
          <button
            type="button"
            onClick={() => removeTerm(i)}
            className="text-[var(--muted)] hover:text-[var(--danger)]"
            aria-label={`Remove ${t}`}
          >
            <X size={11} />
          </button>
        )}
      </span>
    ))}
  </div>
)}
```

- [ ] **Step 5: Verify build + lint**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/SearchPanel.tsx
git commit -m "SearchPanel: parse commas/lists + live chip preview"
```

---

## Task 3: Backend defense — comma-split in start_search

**Files:**
- Modify: `backend/main.py:747`
- Test: `tests/test_backend.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_backend.py` inside `ApiShapeTests`

```python
    def test_search_splits_comma_queries(self):
        from utils import search_query  # noqa: F401  (ensures package import path)
        # The endpoint splits a comma-joined query into multiple queries before
        # starting the job. We verify the splitting helper the endpoint uses.
        from backend.main import _split_queries
        self.assertEqual(_split_queries(["a, b", "c"]), ["a", "b", "c"])
        self.assertEqual(_split_queries(["  ", "x ,, y"]), ["x", "y"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backend.py -k test_search_splits_comma_queries -v`
Expected: FAIL — `cannot import name '_split_queries'`.

- [ ] **Step 3: Add `_split_queries` and use it in `start_search`**

In `backend/main.py`, add near the other module helpers (above `start_search`):

```python
def _split_queries(queries: list[str]) -> list[str]:
    """Expand comma-joined queries and drop blanks, so any API client gets the
    same per-term search behavior the UI provides."""
    out = []
    for q in queries:
        for part in q.split(","):
            part = part.strip()
            if part:
                out.append(part)
    return out
```

Replace the `queries = [q.strip() for q in req.queries if q.strip()]` line (around 747) with:

```python
    queries = _split_queries(req.queries)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backend.py -k test_search_splits_comma_queries -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_backend.py
git commit -m "Backend: split comma-joined search queries"
```

---

## Task 4: Cancel UI feedback

**Files:**
- Modify: `frontend/src/components/SearchPanel.tsx`

- [ ] **Step 1: Add cancelling state**

After the `status` state (around line 46) add:

```ts
const [cancelling, setCancelling] = useState(false);
```

- [ ] **Step 2: Reset cancelling when the job finishes**

In the polling `tick` callback, inside the `if (s.done)` block (around line 69), add `setCancelling(false);` alongside the existing `setJobId(null);`.

- [ ] **Step 3: Replace the Cancel button**

Replace the running-state button (lines 254-258) with:

```tsx
<button
  className="btn"
  disabled={cancelling}
  onClick={() => {
    if (!jobId) return;
    setCancelling(true);
    cancelSearch(jobId);
  }}
>
  {cancelling ? "Cancelling…" : "Cancel"}
</button>
```

- [ ] **Step 4: Verify build + lint**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SearchPanel.tsx
git commit -m "SearchPanel: show Cancelling… state on cancel"
```

---

## Task 5: Backend — delete project endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_backend.py`

- [ ] **Step 1: Write the failing test** — append to `ApiShapeTests`

```python
    def test_delete_project_removes_it(self):
        created = self.client.post(
            "/api/projects",
            json={"name": "Temp Del", "topic": "t", "type": "both"},
        ).json()
        pid = created["id"]
        r = self.client.delete(f"/api/projects/{pid}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("deleted", body)
        self.assertIn("collected_articles", body["deleted"])
        # It is gone now.
        self.assertEqual(self.client.get(f"/api/projects/{pid}").status_code, 404)

    def test_delete_missing_project_404(self):
        self.assertEqual(self.client.delete("/api/projects/99999999").status_code, 404)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backend.py -k delete_project -v`
Expected: FAIL — DELETE returns 405 (method not allowed).

- [ ] **Step 3: Implement the endpoint**

In `backend/main.py`, add (place it after `get_project`, near line 180). Import the models at the top of the function to match the file's local-import style:

```python
@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int):
    from database import (
        CitationLink,
        CitedArticle,
        CollectedArticle,
        CuratedReview,
        LandscapeAnalysis,
        LandscapeArticle,
    )

    session = new_session()
    try:
        proj = session.get(Project, project_id)
        if not proj:
            raise HTTPException(404, "project not found")
        deleted = {}
        for model in (
            CollectedArticle,
            CuratedReview,
            CitedArticle,
            CitationLink,
            LandscapeArticle,
            LandscapeAnalysis,
        ):
            q = session.query(model).filter_by(project_id=project_id)
            deleted[model.__tablename__] = q.count()
            q.delete(synchronize_session=False)
        session.delete(proj)
        session.commit()
    finally:
        session.close()

    # Best-effort cleanup of background job files for this project.
    try:
        from pathlib import Path

        from utils.job_io import read_json

        for d in ("search_jobs", "ref_jobs", "enrich_jobs", "capture_jobs"):
            p = Path(d)
            if not p.exists():
                continue
            for f in p.glob("*.json"):
                data = read_json(f)
                if data and data.get("project_id") == project_id:
                    f.unlink(missing_ok=True)
    except Exception:
        pass

    return {"ok": True, "deleted": deleted}
```

> Note: confirm the job-dir names against the codebase (`search_jobs` is created in `utils/search_job.py`). Only the dirs that exist are touched; non-existent dirs are skipped, so an extra name in the list is harmless.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backend.py -k delete_project -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_backend.py
git commit -m "Backend: DELETE project cascades to child tables"
```

---

## Task 6: Frontend — delete project from card

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Add `deleteProject` to api.ts**

After `createProject` (line 46) add:

```ts
export async function deleteProject(id: number): Promise<{ ok: boolean; deleted: Record<string, number> }> {
  const res = await fetch(`${BASE}/api/projects/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
```

- [ ] **Step 2: Wire delete state into HomePage**

In `frontend/src/app/page.tsx`, update the import (line 6) to include `deleteProject`:

```ts
import { createProject, deleteProject, listProjects } from "@/lib/api";
```

Add `Trash2` to the lucide import (line 8):

```ts
import { Plus, ArrowRight, FolderOpen, Trash2 } from "lucide-react";
```

In `HomePage`, after `const [creating, setCreating] = useState(false);` add:

```ts
const [deleting, setDeleting] = useState<ProjectSummary | null>(null);
const removeProject = (id: number) =>
  setProjects((cur) => (cur ? cur.filter((p) => p.id !== id) : cur));
```

- [ ] **Step 3: Add the trash icon to each card**

Inside the `<Link>` card (after the gradient `<span>` at line 83), add:

```tsx
<button
  type="button"
  onClick={(e) => {
    e.preventDefault();
    e.stopPropagation();
    setDeleting(p);
  }}
  className="absolute right-2 top-2 z-10 rounded-md p-1.5 text-[var(--faint)] opacity-0 transition hover:bg-[var(--danger)]/10 hover:text-[var(--danger)] group-hover:opacity-100"
  aria-label={`Delete ${p.name}`}
>
  <Trash2 size={15} />
</button>
```

- [ ] **Step 4: Render the confirmation modal**

Before the closing `</div>` that wraps the page, next to `{creating && ...}` (line 104), add:

```tsx
{deleting && (
  <DeleteProjectModal
    project={deleting}
    onClose={() => setDeleting(null)}
    onDeleted={() => {
      removeProject(deleting.id);
      setDeleting(null);
    }}
  />
)}
```

- [ ] **Step 5: Implement DeleteProjectModal**

Add this component at the bottom of the file (after `SkeletonGrid`):

```tsx
function DeleteProjectModal({
  project,
  onClose,
  onDeleted,
}: {
  project: ProjectSummary;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const armed = confirm.trim().toLowerCase() === "delete";

  const run = async () => {
    if (!armed) return;
    setBusy(true);
    setErr(null);
    try {
      await deleteProject(project.id);
      onDeleted();
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div className="card card-elevated w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h2 className="font-display text-lg font-semibold text-[var(--danger)]">Delete project</h2>
        <p className="mt-2 text-sm text-[var(--text)]">
          This permanently deletes <b>{project.name}</b>, including{" "}
          <b>{project.library.toLocaleString()}</b> library papers,{" "}
          <b>{project.curated_reviews.toLocaleString()}</b> reviews, and{" "}
          <b>{project.cited.toLocaleString()}</b> cited records. This cannot be undone.
        </p>
        <label className="mt-4 block text-xs font-medium text-[var(--muted)]">
          Type <code className="font-mono text-[var(--text)]">delete</code> to confirm
        </label>
        <input
          className="input mt-1 w-full"
          value={confirm}
          autoFocus
          onChange={(e) => setConfirm(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
        />
        {err && <div className="mt-2 text-xs text-[var(--danger)]">{err}</div>}
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className="btn"
            style={{ background: "var(--danger)", color: "white", opacity: armed && !busy ? 1 : 0.5 }}
            disabled={!armed || busy}
            onClick={run}
          >
            {busy ? "Deleting…" : "Delete this project"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Verify build + lint**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/app/page.tsx
git commit -m "Frontend: delete project from card with typed confirmation"
```

---

## Task 7: Backend — rename + duplicate project

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_backend.py`

- [ ] **Step 1: Write the failing tests** — append to `ApiShapeTests`

```python
    def test_rename_project(self):
        pid = self.client.post(
            "/api/projects", json={"name": "Before", "topic": "t", "type": "both"}
        ).json()["id"]
        try:
            r = self.client.patch(f"/api/projects/{pid}", json={"name": "After"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(self.client.get(f"/api/projects/{pid}").json()["name"], "After")
        finally:
            self.client.delete(f"/api/projects/{pid}")

    def test_duplicate_project_shell_only(self):
        pid = self.client.post(
            "/api/projects", json={"name": "Orig", "topic": "top", "type": "review"}
        ).json()["id"]
        dup_id = None
        try:
            r = self.client.post(f"/api/projects/{pid}/duplicate")
            self.assertEqual(r.status_code, 200)
            dup_id = r.json()["id"]
            dup = self.client.get(f"/api/projects/{dup_id}").json()
            self.assertTrue(dup["name"].startswith("Copy of"))
        finally:
            self.client.delete(f"/api/projects/{pid}")
            if dup_id:
                self.client.delete(f"/api/projects/{dup_id}")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_backend.py -k "rename_project or duplicate_project" -v`
Expected: FAIL — 405 method not allowed.

- [ ] **Step 3: Add the Pydantic schema**

In `backend/main.py`, near `ProjectCreate` (line 63) add:

```python
class ProjectPatch(BaseModel):
    name: Optional[str] = None
    topic: Optional[str] = None
    description: Optional[str] = None
```

- [ ] **Step 4: Implement PATCH and duplicate endpoints**

Add after `get_project`:

```python
@app.patch("/api/projects/{project_id}")
def update_project(project_id: int, patch: ProjectPatch):
    session = new_session()
    try:
        proj = session.get(Project, project_id)
        if not proj:
            raise HTTPException(404, "project not found")
        if patch.name is not None:
            if not patch.name.strip():
                raise HTTPException(400, "name cannot be empty")
            proj.name = patch.name.strip()
        if patch.topic is not None:
            proj.topic = patch.topic.strip()
        if patch.description is not None:
            proj.description = patch.description
        session.commit()
        return {"id": proj.id, "name": proj.name, "topic": proj.topic}
    finally:
        session.close()


@app.post("/api/projects/{project_id}/duplicate")
def duplicate_project(project_id: int):
    session = new_session()
    try:
        src = session.get(Project, project_id)
        if not src:
            raise HTTPException(404, "project not found")
        clone = Project(
            name=f"Copy of {src.name}",
            topic=src.topic,
            literature_type=src.literature_type,
            description=src.description,
            stage=3,  # ready to collect, matching create_project
        )
        session.add(clone)
        session.commit()
        return {"id": clone.id, "name": clone.name}
    finally:
        session.close()
```

> Fields confirmed against `database.py:Project` and `create_project` (`backend/main.py:151`): `name`, `topic`, `literature_type`, `description`, `stage` all exist.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_backend.py -k "rename_project or duplicate_project" -v`
Expected: PASS (both).

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_backend.py
git commit -m "Backend: PATCH rename + duplicate (shell only) project"
```

---

## Task 8: Frontend — inline rename + duplicate on card

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Add api.ts functions**

After `deleteProject` add:

```ts
export async function renameProject(id: number, patch: { name?: string; topic?: string; description?: string }) {
  const res = await fetch(`${BASE}/api/projects/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<{ id: number; name: string; topic: string }>;
}

export async function duplicateProject(id: number) {
  const res = await fetch(`${BASE}/api/projects/${id}/duplicate`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<{ id: number; name: string }>;
}
```

- [ ] **Step 2: Import them + icons in page.tsx**

Update imports:

```ts
import { createProject, deleteProject, duplicateProject, listProjects, renameProject } from "@/lib/api";
import { Plus, ArrowRight, FolderOpen, Trash2, Pencil, Copy } from "lucide-react";
```

- [ ] **Step 3: Add rename + reload helpers in HomePage**

After `removeProject` add:

```ts
const [renamingId, setRenamingId] = useState<number | null>(null);
const reload = () => listProjects().then(setProjects).catch((e) => setError(String(e)));
```

- [ ] **Step 4: Add edit/duplicate buttons next to the trash button**

In the card action cluster (alongside the Trash2 button from Task 6), add two more buttons. Wrap all three in a container `<div className="absolute right-2 top-2 z-10 flex gap-0.5 opacity-0 transition group-hover:opacity-100">` and move the existing trash button inside it (drop the individual `opacity-0 group-hover:opacity-100` from the trash button since the wrapper handles it):

```tsx
<button
  type="button"
  onClick={(e) => { e.preventDefault(); e.stopPropagation(); setRenamingId(p.id); }}
  className="rounded-md p-1.5 text-[var(--faint)] transition hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
  aria-label={`Rename ${p.name}`}
>
  <Pencil size={15} />
</button>
<button
  type="button"
  onClick={async (e) => {
    e.preventDefault();
    e.stopPropagation();
    await duplicateProject(p.id);
    reload();
  }}
  className="rounded-md p-1.5 text-[var(--faint)] transition hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
  aria-label={`Duplicate ${p.name}`}
>
  <Copy size={15} />
</button>
```

- [ ] **Step 5: Inline-edit the name when renaming**

Replace the card title `<h2>` (line 85) with a conditional: when `renamingId === p.id`, render an input; otherwise the heading.

```tsx
{renamingId === p.id ? (
  <input
    className="input w-full text-base font-semibold"
    defaultValue={p.name}
    autoFocus
    onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
    onKeyDown={(e) => {
      e.stopPropagation();
      if (e.key === "Escape") setRenamingId(null);
    }}
    onBlur={async (e) => {
      const name = e.target.value.trim();
      setRenamingId(null);
      if (name && name !== p.name) {
        await renameProject(p.id, { name });
        reload();
      }
    }}
  />
) : (
  <h2 className="font-display text-base font-semibold leading-snug">{p.name}</h2>
)}
```

- [ ] **Step 6: Verify build + lint**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/app/page.tsx
git commit -m "Frontend: inline rename + duplicate project on card"
```

---

## Task 9: Backend — AI keyword expansion

**Files:**
- Modify: `ai/claude_client.py`
- Modify: `backend/main.py`
- Test: `tests/test_backend.py`

- [ ] **Step 1: Write the failing test** — append to `ApiShapeTests`

```python
    def test_keyword_suggest_shape(self):
        r = self.client.post("/api/keyword-suggest", json={"topic": "drug delivery", "seeds": []})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("terms", body)
        self.assertIsInstance(body["terms"], list)
        # Without an API key configured the endpoint degrades gracefully.
        if not body["terms"]:
            self.assertTrue(body.get("unavailable"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backend.py -k keyword_suggest -v`
Expected: FAIL — 404 not found.

- [ ] **Step 3: Add `suggest_keywords` to ai/claude_client.py**

Append:

```python
def suggest_keywords(topic: str, seeds: list[str] | None = None) -> list[str]:
    """Return related search keywords for a topic. Returns [] if no API key is
    configured or the call fails — callers degrade gracefully."""
    seeds = seeds or []
    try:
        client = get_client()
    except Exception:
        return []
    seed_line = f" Existing terms: {', '.join(seeds)}." if seeds else ""
    prompt = (
        f"Suggest 12 concise literature-search keywords or short phrases for the "
        f"research topic: \"{topic}\".{seed_line} "
        f"Return ONLY a comma-separated list, no numbering, no commentary."
    )
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    except Exception:
        return []
    out, seen = [], set()
    for part in text.replace("\n", ",").split(","):
        term = part.strip().lstrip("-•*0123456789. )").strip()
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            out.append(term)
    return out[:12]
```

> Note: confirm `get_client` and `MODEL` exist in `ai/claude_client.py` (they do, per the spec). Match the existing message-parsing idiom used by `classify_articles_relevance`.

- [ ] **Step 4: Add the endpoint + schema in backend/main.py**

Near the schemas add:

```python
class KeywordSuggest(BaseModel):
    topic: str = ""
    seeds: list[str] = []
```

Add the endpoint (near the other project-level routes):

```python
@app.post("/api/keyword-suggest")
def keyword_suggest(body: KeywordSuggest):
    from ai.claude_client import suggest_keywords

    terms = suggest_keywords(body.topic, body.seeds)
    return {"terms": terms, "unavailable": len(terms) == 0}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_backend.py -k keyword_suggest -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/claude_client.py backend/main.py tests/test_backend.py
git commit -m "Backend: AI keyword-suggest endpoint with graceful degradation"
```

---

## Task 10: Frontend — Suggest terms button

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/SearchPanel.tsx`
- Modify: `frontend/src/app/projects/[id]/page.tsx`

- [ ] **Step 1: Add api.ts function**

After `duplicateProject` add:

```ts
export async function suggestKeywords(topic: string, seeds: string[]): Promise<{ terms: string[]; unavailable: boolean }> {
  return postJson(`/api/keyword-suggest`, { topic, seeds });
}
```

- [ ] **Step 2: Pass topic into SearchPanel**

In `frontend/src/app/projects/[id]/page.tsx`, where `<SearchPanel ... />` is rendered (line 253), add `topic={project?.topic ?? ""}`.

- [ ] **Step 3: Accept the prop in SearchPanel**

In `SearchPanel`'s props type (line 26-33) add `topic?: string;` and destructure `topic = ""`.

- [ ] **Step 4: Add suggestion state + handler**

Add imports: `import { suggestKeywords } from "@/lib/api";` and `import { Sparkles } from "lucide-react";` (merge into existing import lines).

Add state near the others:

```ts
const [suggestions, setSuggestions] = useState<string[]>([]);
const [suggesting, setSuggesting] = useState(false);
const [aiUnavailable, setAiUnavailable] = useState(false);

const fetchSuggestions = async () => {
  setSuggesting(true);
  try {
    const r = await suggestKeywords(topic, terms);
    setSuggestions(r.terms.filter((t) => !terms.some((x) => x.toLowerCase() === t.toLowerCase())));
    setAiUnavailable(r.unavailable);
  } finally {
    setSuggesting(false);
  }
};

const addSuggestion = (t: string) => {
  setQueries((q) => (q.trim() ? `${q}\n${t}` : t));
  setSuggestions((s) => s.filter((x) => x !== t));
};
```

- [ ] **Step 5: Render the button + suggestion chips**

Directly below the chip preview block (from Task 2), add:

```tsx
{!aiUnavailable && (
  <div className="mt-2">
    <button
      type="button"
      className="flex items-center gap-1 text-xs font-medium text-[var(--primary)] hover:underline disabled:opacity-50"
      onClick={fetchSuggestions}
      disabled={suggesting || running}
    >
      <Sparkles size={12} /> {suggesting ? "Thinking…" : "Suggest terms"}
    </button>
    {suggestions.length > 0 && (
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {suggestions.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => addSuggestion(t)}
            className="rounded-full border border-dashed border-[var(--primary)] px-2 py-0.5 text-xs text-[var(--primary)] hover:bg-[var(--primary-weak)]"
          >
            + {t}
          </button>
        ))}
      </div>
    )}
  </div>
)}
```

- [ ] **Step 6: Verify build + lint**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/components/SearchPanel.tsx "frontend/src/app/projects/[id]/page.tsx"
git commit -m "Frontend: AI Suggest terms button + add-able chips"
```

---

## Task 11: Verify + document keyboard screening

**Files:**
- Modify: `frontend/src/components/Shortcuts.tsx` (only if entries are missing)

- [ ] **Step 1: Read the HelpOverlay**

Read `frontend/src/components/Shortcuts.tsx` and list which keys it documents.

- [ ] **Step 2: Compare against the implemented keys**

The Library keys implemented in `frontend/src/app/projects/[id]/page.tsx:519-564` are:
`j`/`k`/↑/↓ navigate, `o`/Enter open, `i`/`m`/`e`/`u` decisions, `x`/Space select, `a` select all, `Delete`/`Backspace` trash, `[`/`]` page, `/` focus filter, `1`–`5` decision filter.

- [ ] **Step 3: Add any missing entries**

For each implemented key not present in the HelpOverlay, add a documentation row following the file's existing row format (match the surrounding JSX exactly). If all keys are already documented, make no change and note it.

- [ ] **Step 4: Verify build + lint**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit (only if changed)**

```bash
git add frontend/src/components/Shortcuts.tsx
git commit -m "Docs: complete keyboard-screening shortcuts in help overlay"
```

---

## Final verification

- [ ] **Backend tests**

Run: `python -m pytest tests/test_backend.py -v`
Expected: all PASS.

- [ ] **Frontend unit tests**

Run: `cd frontend && npm test`
Expected: all PASS.

- [ ] **Frontend typecheck + lint**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: no errors.

- [ ] **Manual smoke (with backend + frontend running):**
  - Paste `1. alpha, 2. beta, gamma` into Search → chip preview shows 3 terms.
  - Start a multi-term search, click Cancel → button shows "Cancelling…" and the run stops.
  - On the home page, hover a project card → rename inline, duplicate (creates "Copy of …"), and delete (requires typing `delete`).
  - Click "Suggest terms" → either chips appear or the button is hidden when AI is unavailable.
```
