# Search & Project Convenience — Batch 1 Design

**Date:** 2026-05-22
**Status:** Approved for planning

## Goal

Remove the friction points that currently trip users up in the search/collect flow and
project management, with a "design for convenience" lens. This batch bundles three bug
fixes with three net-new convenience features.

Keyboard screening was originally scoped into this batch but **already exists** in
`LibraryTab` (`frontend/src/app/projects/[id]/page.tsx`). It is reduced to a
documentation/verification task (see §7), not a rebuild.

## Background / current behavior

- **Search input** (`frontend/src/components/SearchPanel.tsx`): the textarea is split on
  newlines only (`queries.split("\n")`). Pasting a comma-separated list on one line sends
  the whole paragraph as a single query. The backend (`backend/main.py:start_search`) only
  `.strip()`s each query — it never splits on commas, and nothing strips numbered-list
  markers like `1.`.
- **Cancel** (`utils/search_job.py`): cancellation is cooperative and only checked
  *between* queries (`_is_cancelled` at the top of the per-query loop). With a single large
  query, the worker is blocked inside the source calls and never observes the cancel flag,
  so the Cancel button appears to do nothing. The frontend button also gives no feedback.
- **Project delete**: no endpoint exists. Six tables reference `project_id`:
  `collected_articles`, `curated_reviews`, `cited_articles`, `citation_links`,
  `landscape_articles`, `landscape_analysis`.
- **Rename / duplicate**: no endpoints; projects can only be created.
- **AI**: `ai/claude_client.py` already wraps the Anthropic SDK (`get_client`, `MODEL`) and
  has `suggest_search_strategy`. No keyword-expansion entry point.

## Features

### 1. Smart keyword parsing

New module `frontend/src/lib/parseTerms.ts`:

```ts
export function parseTerms(raw: string): string[]
```

Rules, in order:
1. Split on both newlines and commas.
2. For each piece, strip a leading list marker via regex `^\s*(\d+[.)]|[-*•])\s+`.
3. Trim whitespace.
4. Drop empty pieces.
5. De-duplicate case-insensitively, preserving the first occurrence's casing.

`SearchPanel.run()` builds `queries` from `parseTerms(queries)` instead of the inline
newline split. Helper text under the label changes to
"one per line or comma-separated".

**Defense-in-depth (backend):** `start_search` in `backend/main.py` expands each incoming
query on commas as well, so any API client (not just this UI) is protected:
`queries = [t for q in req.queries for t in q.split(",")]` then strip/drop-empty.

Multi-word phrases are preserved because splitting is on commas, never spaces
(`"liposomal drug delivery, nanoparticle"` → two terms).

### 2. Live chip preview

In `SearchPanel`, below the textarea:
- Render `parseTerms(queries)` as removable chips, each with an `×`.
- Show a live count: "**N terms**".
- Removing a chip rewrites the textarea value to the remaining terms joined by `\n`.
- Chips and the remove control are disabled while a search is running.

This makes the previous "54 words → 1 term" failure visible before the user searches.

### 3. Cancel that works

- **Responsiveness:** primarily comes free from §1 — many small queries mean the existing
  between-query cancel check fires within a query or two. No change to the cancel mechanism
  itself in this batch.
- **UI feedback:** add a `cancelling` state in `SearchPanel`. On Cancel click: call
  `cancelSearch(jobId)`, set `cancelling = true`; the button label becomes "Cancelling…"
  and is disabled. Reset `cancelling` when the polled status reports `done`.
- **Out of scope (noted as a follow-up):** threading the cancel check into the per-source
  loop inside `utils/search_runner.py` so a single multi-source query can abort mid-flight.

### 4. Delete project (GitHub-style)

**Backend** — `DELETE /api/projects/{project_id}`:
- 404 if the project does not exist.
- In one transaction: count and delete rows in all six child tables
  (`collected_articles`, `curated_reviews`, `cited_articles`, `citation_links`,
  `landscape_articles`, `landscape_analysis`), then delete the `Project` row.
- Best-effort cleanup of that project's job files under `search_jobs/` (and equivalent job
  dirs) — failures here are logged, not fatal.
- Return the per-table counts deleted, so the scope of the deletion is explicit in the
  response (consistent with the "confirm scope before destructive deletes" practice).

**API client** — `deleteProject(id: number)` in `frontend/src/lib/api.ts`.

**Frontend** (`frontend/src/app/page.tsx`):
- A trash icon appears on project-card hover. Because the card is a `<Link>`, the handler
  calls `e.preventDefault()` + `e.stopPropagation()` to open the modal instead of
  navigating.
- Confirmation modal shows what will be deleted using the counts already on
  `ProjectSummary` (e.g. "**N library papers**, M reviews, K cited").
- A text input requires typing the literal word **`delete`** (case-insensitive,
  trimmed) to enable a red "Delete this project" button.
- On success, the card is removed from the list.

Rationale for typing `delete` rather than the project name: this is a local-first tool;
the typed-word confirmation is enough safety without forcing the user to copy a long name.

### 5. Inline rename + duplicate project

**Backend:**
- `PATCH /api/projects/{project_id}` — update `name`, `topic`, and/or `description`.
  Validates non-empty `name` when provided. Returns the updated project.
- `POST /api/projects/{project_id}/duplicate` — **shell only**: copies `name`
  (prefixed "Copy of "), `topic`, `literature_type`, and `description` into a new project
  with an empty library. Returns the new project's id. Does NOT copy collected articles,
  reviews, cited articles, citation links, or analyses.

**API client:** `renameProject(id, patch)` and `duplicateProject(id)`.

**Frontend** (`frontend/src/app/page.tsx`):
- A pencil icon on the card switches the name to an inline `<input>`; Enter or blur saves
  via `renameProject`, Escape cancels. The icon's handler must `preventDefault` +
  `stopPropagation` (card is a `<Link>`).
- A duplicate icon calls `duplicateProject` and inserts the new card into the list.

### 6. AI keyword expansion

**Backend:**
- New `suggest_keywords(topic: str, seeds: list[str]) -> list[str]` in
  `ai/claude_client.py`, using the existing `get_client()`/`MODEL`. Prompt: given the
  project topic and any seed terms, return a deduplicated list of related search keywords
  /synonyms suitable as search terms.
- New endpoint `POST /api/keyword-suggest` (body: `{ topic, seeds }`) returning
  `{ terms: string[] }`. If no API key is configured, return an empty list with a flag
  (e.g. `{ terms: [], unavailable: true }`) rather than 500 — graceful degradation.

**API client:** `suggestKeywords(topic, seeds)`.

**Frontend** (`SearchPanel`):
- A "✨ Suggest terms" button near the textarea (uses the project topic, passed in as a new
  prop, plus the currently-parsed terms as seeds).
- Suggested terms render as add-able chips; clicking one appends it to the textarea
  (feeding the same `parseTerms` flow). Disabled / hidden when AI is unavailable.

### 7. Keyboard screening — verify & document only

No rebuild. Confirm the existing keys in `LibraryTab` work (`i`/`m`/`e`/`u`, `j`/`k`/arrows,
`o`/Enter, `x`/space, `a`, `Delete`, `[`/`]`, `/`, `1`–`5`) and ensure the `HelpOverlay`
(`frontend/src/components/Shortcuts.tsx`) documents all of them. Add any missing entries.

## Data flow

- Search: textarea → `parseTerms` → chips + `startSearch` → background job → poll status.
- Delete/rename/duplicate: card action → API call → list state update.
- Keyword suggest: button → `suggestKeywords` → chips → textarea → `parseTerms`.

## Error handling

- `parseTerms` never throws; empty input → `[]` (existing "enter at least one term" guard
  stays).
- Delete/rename/duplicate endpoints: 404 on missing project; errors surfaced inline in the
  modal/card.
- Keyword suggest: missing API key or SDK error → `{ terms: [], unavailable: true }`, no
  crash; UI hides the feature.

## Testing

- **Unit (frontend):** `parseTerms` — newlines, commas, mixed, numbered/bulleted lists,
  dedup, whitespace, empty.
- **Unit/integration (backend):** delete removes all six child tables and the project and
  returns correct counts; rename validation; duplicate copies shell only (empty library);
  `start_search` comma-splitting; `keyword-suggest` returns `unavailable` without a key.
- **Manual:** paste a numbered comma list → correct chip count; Cancel shows "Cancelling…"
  and stops promptly; delete flow requires typing `delete`; rename/duplicate from a card;
  suggest-terms adds chips.

## Out of scope (follow-ups)

- Mid-query (per-source) cancellation in `search_runner`.
- Archive projects; full library-cloning duplicate.
- Saved searches / query templates.
