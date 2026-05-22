# Field-of-Study Engine — Design

**Date:** 2026-05-22
**Status:** Draft for review

## Goal

Let users see and filter collected papers by **academic field** (discipline), so a
keyword search like "serendipity" that pulls in chemistry/physics papers can be narrowed
to the user's actual topic. The classification must be **free, offline, and require no API
key or per-call cost for any user** — it works identically in the public/trial version with
zero setup.

## Why this approach

Collection is keyword-driven and not topic-aware, so off-topic papers are unavoidable. The
sources expose discipline metadata unevenly (OpenAlex: full; Semantic Scholar: its own
taxonomy; arXiv: coarse; PubMed: none), and any *live* per-article lookup would require an
API key we cannot provide to public/trial users. Therefore the engine is a **precomputed,
shipped journal→field lookup table**, matched per paper by **ISSN**. This is a mature,
standardised idea (Scopus ASJC / Scimago / Web of Science journal classification); we reuse
the OpenAlex field taxonomy (26 fields, CC0 public-domain data) rather than invent one.

**Trade-off accepted:** journal-level classification is less precise than content-level for
multidisciplinary megajournals. We handle that explicitly with a **"Multidisciplinary"**
bucket and never emit a confidently-wrong label. Unmatched papers get **"Unknown field"**.

## The 26 fields

OpenAlex's canonical field list (aligned with Scopus ASJC), e.g. Social Sciences, Arts and
Humanities, Computer Science, Chemistry, Physics and Astronomy, Materials Science, Medicine,
… (full list of 26 baked in as a constant for the "all fields" picker section).

## Components

### 1. Build script (developer-run, one-time) — `scripts/build_journal_fields.py`
- Pages the OpenAlex `sources` API (or a CC0 snapshot) using a **developer** key.
- For each source (journal) with an ISSN: aggregate its `topics` to a **dominant field**
  and a **concentration ratio** (top field's share of works).
- Emit one record per journal:
  `{ issn_l, issns: [...], names: [normalized display_name + alternate_titles + abbreviated_title], field, multidisciplinary }`
  where `multidisciplinary = concentration < 0.5` (threshold documented, tunable).
- Write a shipped artifact: `data/journal_fields.json.gz` (committed to the repo). Two
  in-memory indexes are built from it at load: **by ISSN** and **by normalized name**.
- This script is **not** run by end users; it produces the artifact we ship. Refresh
  ~annually.

### 2. Runtime classifier — `utils/field_classifier.py`
- Loads the shipped table once (lazy, cached) into `{issn -> entry}` and `{name -> entry}`.
- `classify(issn: str | None, venue: str | None) -> tuple[str, str]` returns
  `(field_label, field_source)`:
  - ISSN hit → `(entry.field or "Multidisciplinary", "issn")`
  - else normalized-venue-name hit → `(…, "name")`
  - else → `("Unknown", "none")`
  - megajournal (`multidisciplinary` true) → field_label `"Multidisciplinary"`.
- Pure, deterministic, no network. Never raises (bad input → `("Unknown", "none")`).

### 3. ISSN capture in source parsers
- `api/openalex.py`: parse `primary_location.source.issn_l` (already fetched via
  `primary_location`; no FIELDS change). Return `issn`.
- `api/semantic_scholar.py`: add `publicationVenue` to `FIELDS`; parse
  `publicationVenue.issn`. Return `issn`.
- `api/pubmed.py`: parse `.//Journal/ISSN` from the article XML. Return `issn`.
- `api/arxiv.py`: no ISSN (preprints) → `issn = ""`.

### 4. Persistence + classification at collection
- `database.py`: add columns via the existing migration list:
  - `collected_articles.issn VARCHAR(20) DEFAULT ''`
  - `collected_articles.field VARCHAR(60) DEFAULT ''`
  - `collected_articles.field_source VARCHAR(10) DEFAULT ''`
- `utils/search_job.py`: when saving each `CollectedArticle`, call
  `classify(art.get("issn"), art.get("venue"))` and store `field` + `field_source` + `issn`.

### 5. Backfill for existing papers — `POST /api/projects/{id}/backfill-fields`
- Existing rows have no `issn` captured historically, so backfill matches by **normalized
  venue name** against the table's name index. Pure local pass over the project's rows —
  **instant, no API, no rate limit**. Sets `field`/`field_source`; unmatched → "Unknown".
- (New collections are classified inline, so backfill is only for pre-existing libraries.)

### 6. Filtering API
- `GET /api/projects/{id}/articles`: add a `field` query param (exact match against the
  stored `field`, mirroring the existing `category` filter).
- Field facet counts: add a `by_field` tally (label → count) to the screening-stats or
  insights response, so the picker shows "Social Sciences (120), Chemistry (8)".

### 7. Frontend (Library tab)
- A **Field** filter next to Type/Decision: **hybrid** picker — fields present in the
  collection with counts (checkable) + a collapsible "All 26 fields" section (hardcoded
  constant) for fields not yet collected. "Multidisciplinary" and "Unknown" appear as their
  own buckets.
- Field shown on the paper modal with provenance, e.g. "Field: Chemistry (matched by
  journal ISSN)" — explainability builds trust.
- **Disposition:** the field is a *filter/label only*. To act, the user selects rows and
  uses the **existing bulk Exclude / Delete** actions. Nothing is auto-excluded or deleted.

## Data flow

Collection: source parser (issn, venue) → `classify()` → store field on `CollectedArticle`.
Filter: Library Field picker → `GET …/articles?field=…` → table → existing bulk actions.
Backfill: button → local name-match pass → fields updated.

## Error handling

- Classifier never raises; missing/garbled input → "Unknown".
- Missing shipped artifact → classifier returns "Unknown" for everything (logged once);
  app still works.
- Migration add-column is idempotent (try/except per the existing pattern).
- Backfill endpoint: 404 on missing project; per-row failures skipped, not fatal.

## Testing

- **Classifier:** ISSN hit, name-fallback hit, megajournal→"Multidisciplinary",
  no-match→"Unknown", empty/None input.
- **Parsers:** OpenAlex/S2/PubMed extract `issn`; arXiv returns "".
- **Build script:** a sample OpenAlex `sources` payload → correct table entry incl.
  dominant-field + multidisciplinary flag.
- **Migration:** columns added idempotently on an existing DB.
- **API:** `field` filter narrows results; `by_field` facet counts correct; backfill sets
  fields by name match and reports a count.

## Out of scope (future)

- **BYO-key content-aware classification** (the optional layer): when a user supplies their
  own OpenAlex/Claude key post-trial, classify per-article from title/abstract for higher
  accuracy. Designed later; the `field_source` column already anticipates it.
- Lexical/keyword tie-break to split megajournal papers into a real field (no API) — a
  possible later refinement; for now megajournals are labelled "Multidisciplinary".
- Scimago/Scopus crosswalk as an alternate dataset source.
