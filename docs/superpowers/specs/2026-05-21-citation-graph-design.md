# Citation graph: references, Library column, and Network map — design

*2026-05-21*

## Goal

Make a paper's references first-class and connect the corpus into a real
citation graph, using one shared data layer:

1. A **references companion panel** beside the paper modal: see what a paper
   cites and pull individual references (or all) into the Library.
2. A **Library "References" column** showing fetched/added state at a glance.
3. A **Network map** rebuilt on the live corpus (it is currently blank for
   search-based projects), rendered in legible **2D**.

## Why now

`backend/network.py` was written for the old Streamlit model (`CuratedReview`,
`CitedArticle`). Search-based projects have **zero** of those rows — everything
is in `CollectedArticle`. Verified on project 4: 16,583 collected papers, 0
curated reviews, 0 cited articles. So citation + journal modes render blank;
only author mode (which reads `CollectedArticle`) works. Meanwhile ~86% of
papers carry `referenced_ids` and ~92% carry an `openalex_id` — ideal for a real
citation graph that the builder currently ignores.

## Data layer (shared)

- **New table `CitationLink`**: `id · project_id · citing_id → cited_id ·
  created_at`, unique on `(citing_id, cited_id)`. Records *provenance*: "I
  collected B from A's reference list." Powers the Library column's added-count,
  the green state, and the "what did I add from here" list. Deterministic and
  fast (no re-matching on read).
- **Graph edges** are derived from `referenced_ids ∩ openalex_id` across the
  project's non-deleted papers — A→B when B's OpenAlex id is in A's
  `referenced_ids`. Covers the whole corpus; newly-collected references connect
  automatically because they carry their own `openalex_id`.

## 1. References companion panel

- Opens **parallel beside** the paper modal once a paper has a fetched list
  (`references_json`). Layout: paper card on the left, references panel on the
  right; stacks/toggles on narrow screens.
- Each reference row is annotated:
  - **in library** — matched to a Library row by DOI/OA id → click opens it.
  - **collectable** — has a DOI/OA id, not yet in library → **Collect** button.
  - **no-DOI** — shown, greyed, "can't collect"; never blocks the green state.
- Buttons: **Collect** (one) and **Collect all** (collectable, not-yet-added).
  Both **resolve full metadata** (OpenAlex by DOI/id → Crossref fallback) and
  add as `CollectedArticle(origin="reference")`, then create a `CitationLink`.
  If a reference already exists in the Library, **link it, don't duplicate**.
- Collect-all is a single batched call (OpenAlex 50/call); reference lists are
  ~30–50, so no background job. Per-item failures are skipped, not fatal.

## 2. Library "References" column

- `—` not fetched · plain number fetched · **green** number when every
  *collectable* reference is in the Library (`added ≥ collectable`, collectable
  > 0) · click the number → opens the paper modal with the references panel.
- List endpoint adds per-row `references_count` (fetched), `references_collectable`
  (refs with a DOI), `references_added` (grouped `CitationLink` count). Computed
  for the current page only; collectable parsed from `references_json` solely
  for rows that have references.

## 3. Network map rebuild (2D)

- Swap `react-force-graph-3d` → `react-force-graph-2d` (same family; readable).
- **Citation** — rebuilt on `CollectedArticle` + `referenced_ids`. Edge A→B when
  B.openalex_id ∈ A.referenced_ids. Node size = in-degree (papers in your set
  that cite it — the foundational metric). Cap ~800 nodes by top in-degree.
- **Author** — kept (already on `CollectedArticle`); add filters.
- **Journal** — rebuilt as venue→venue flow derived from citation edges
  (citing paper's venue → cited paper's venue), weighted. Drops the dead
  `CuratedReview` path.
- **Interactions**: click a node → open that paper in the Library; filters for
  year range, included-only, and minimum citations.

## Endpoints

- `GET  /api/articles/{id}/references` — annotated reference list.
- `POST /api/articles/{id}/references/collect` — collect one (body: identifier).
- `POST /api/articles/{id}/references/collect-all` — collect all collectable.
- `GET  /api/projects/{id}/network?mode=citation|author|journal` — rebuilt.
- `list_articles` / `_article_dict` — add the three reference counts.

## Scope guardrails (YAGNI)

- Everything stays within the project (references added with
  `origin="reference"`).
- No background job for collect-all.
- DOI-less references never block green.
- "Ghost/missing" nodes in the graph (collectable gaps shown hollow) are a
  **deferred stretch**, not part of this build.

## Testing

- `CitationLink` creation + dedup (re-collecting links, never duplicates).
- Column counts: added/collectable/green logic.
- Collect one + collect-all happy path on a known paper.
- Network builder returns non-empty citation/journal graphs for a corpus
  project; edges match `referenced_ids`.
