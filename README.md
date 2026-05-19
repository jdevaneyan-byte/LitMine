# Literature Collector

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)

**A local, open-source workspace for academic literature.** Search OpenAlex,
PubMed, Semantic Scholar and arXiv from one screen; import your existing
reference lists from Excel / CSV / BibTeX / RIS; bulk-extract every citation
from a curated set of review papers; screen with keyboard shortcuts and
PRISMA metrics; download formatted Excel.

Built for small research groups that want a reproducible literature workflow
without cloud lock-in. All data lives in a local SQLite file.

> Status: research software, actively developed. Pre-release; expect rough
> edges.

---

## Why Literature Collector

| Existing tool | What it does well | Gap Literature Collector fills |
|---|---|---|
| [ASReview](https://github.com/asreview/asreview) | AI-assisted screening of imported references | No search, no citation extraction from reviews |
| [Rayyan](https://www.rayyan.ai/) | Polished screening UI, multi-rater | Cloud-only; no API search; no citation mining |
| [Local Citation Network](https://localcitationnetwork.github.io/) | Visualises citation neighbourhoods | No batch screening, no Excel export, no local DB |
| [paper-search-mcp](https://github.com/openags/paper-search-mcp) | Multi-source paper search via CLI | No UI, no screening, no project model |
| [openalexR](https://github.com/ropensci/openalexR) | Powerful OpenAlex queries from R | Single source, R only |

**Literature Collector's hook**: a one-stop **search → import → extract
citations from reviews → screen → export** pipeline that runs on a laptop,
written in Python/Streamlit so it's instantly self-hostable.

---

## Features

- **Multi-database search.** OpenAlex, PubMed (NCBI E-utilities), Semantic
  Scholar, arXiv. Single-topic or batch-queue modes. Results deduplicated
  across sources by DOI, external IDs and fuzzy title match.
- **Curated seed-paper citation extraction.** Upload an Excel of DOIs
  for a mix of review and key primary papers; the tool fetches each
  seed's reference list (Semantic Scholar with Crossref fallback) and
  applies a year + publication-type filter. Cited papers whose
  metadata flags them as reviews are tagged so you can decide whether
  to recurse on them.
- **PRISMA-style screening.** Per-paper decisions (include / maybe /
  exclude / unscreened) with preset exclusion reasons and one-key shortcuts
  (`I` / `M` / `E` / `N`).
- **Duplicate detection and merge.** Scans the library for same-DOI,
  same-normalised-title, and fuzzy-title-within-same-year matches; merges
  metadata into the highest-information row.
- **Formatted Excel export.** Frozen header, auto-filter, wrapped long
  fields, sensible column widths, hyperlinked DOIs.
- **Local-first.** SQLite database; no cloud account, no telemetry beyond
  Streamlit's default usage statistics (which can be disabled).
- **Background jobs.** Long-running searches and extractions run in daemon
  threads; the UI re-attaches to in-flight jobs after a browser refresh.

---

## Installation

Python **3.9 or newer**. Tested on Windows 11 and macOS.

```bash
git clone https://github.com/FILL_IN_USERNAME/literature-collector.git
cd literature-collector
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Optional API keys (free, recommended)

Some databases throttle anonymous traffic. Setting these environment
variables removes the bottleneck:

```bash
# Higher PubMed limits (3 → 10 req/sec)
NCBI_API_KEY=...
# Higher Semantic Scholar limits (~1 → ~100 req/sec)
SEMANTIC_SCHOLAR_API_KEY=...
# Polite-pool identification for OpenAlex and Crossref
CROSSREF_MAILTO=you@example.org
```

Optional Claude API key for the built-in AI analysis features:

```bash
ANTHROPIC_API_KEY=...
```

Copy `.env.example` to `.env` and fill in any keys you have.

### Run

```bash
streamlit run app.py
```

Open <http://localhost:8501>.

---

## Screenshots

> The following screenshots show the main workflows. To regenerate them
> after a UI change, see `docs/screenshots/README.md`.

| | |
|---|---|
| **Home — project list and creator** | ![Home page](docs/screenshots/01_home.png) |
| **Workspace — Search the web** (multi-database, batch queue) | ![Search section](docs/screenshots/02_search.png) |
| **Workspace — Library** (PRISMA strip, screening shortcuts, abstract panel) | ![Library section](docs/screenshots/03_library.png) |
| **Workspace — Extract citations from reviews** (live progress) | ![Extraction section](docs/screenshots/04_extract.png) |
| **Workspace — Possible duplicates** (merge UI) | ![Duplicates panel](docs/screenshots/05_duplicates.png) |

---

## Quick walkthrough

1. **Create a project** on the Home page — name, type (Review / Research /
   Both), optional topic and description.
2. **Open the Workspace.** Pick one of five sections from the top selector:
   - **🔍 Search the web** — type one topic or a list of topics; choose
     databases and year cutoff; results land in the library.
   - **📥 Import my list** — upload Excel (with Title and DOI columns) to
     curated reviews, or CSV / BibTeX / RIS / DOI text to the library.
   - **🔗 Extract citations from reviews** — for each curated review, fetch
     its reference list, filter by year, flag review-type citations.
   - **📚 Library** — browse, filter, screen with keyboard shortcuts,
     download as Excel / CSV / JSON.
   - **⚙ Project settings** — rename / change type / delete.
3. **Screen rapidly.** In the Library, click any row to expand the abstract
   panel; press `I` (include), `M` (maybe), `E` (exclude) or `N` (next).
4. **Resolve duplicates** at the bottom of the Library: **Scan for
   duplicates** then **Merge all** with a confirmation.
5. **Export.** Every download button shows the exact row count and ships
   formatted Excel by default.

---

## Project layout

```
literature-collector/
├── app.py                       # Home: project list and creator
├── pages/
│   ├── 1_Workspace.py           # All in-project actions
│   └── _archive/                # Earlier multi-page UI, kept for reference
├── api/
│   ├── openalex.py
│   ├── pubmed.py
│   ├── semantic_scholar.py
│   ├── arxiv.py
│   └── references.py            # Citation list via S2 + Crossref fallback
├── utils/
│   ├── search_runner.py         # Parallel search across enabled sources
│   ├── search_job.py            # Background-thread job manager
│   ├── extract_job.py           # Bulk citation-extraction job manager
│   ├── dedup.py                 # At-insert deduplication
│   ├── find_duplicates.py       # Post-hoc duplicate scan + merge
│   ├── excel_export.py          # Formatted xlsx output
│   ├── excel_import.py          # Curated-review Excel parser
│   ├── import_refs.py           # CSV / BibTeX / RIS / DOI list parser
│   ├── search_query.py          # Boolean query builder
│   ├── queue_store.py           # Persisted topic queues per project
│   └── keybinds.py              # Keyboard-shortcut helper
├── ai/
│   └── claude_client.py         # Optional Claude AI analysis
├── database.py                  # SQLAlchemy schema (SQLite)
├── tests/
│   └── test_core.py
└── paper/
    ├── paper.md                 # JOSS paper
    └── paper.bib
```

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

---

## For reviewers and first-time users

A small demo dataset and a 7-step smoke-test walkthrough are in
[`examples/`](examples/README.md). No API keys are required to evaluate
any of the review-critical functionality — every database integration
works on the public polite-pool rate limits out of the box.

The optional `ANTHROPIC_API_KEY` only enables the in-app AI analysis
feature (landscape summary, relevance suggestion). All search, import,
extraction, deduplication, screening, and export functionality is
independent of it.

---

## How to cite

If you use Literature Collector in published work, please cite the JOSS
paper (forthcoming) or the repository via the `CITATION.cff` file.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and pull requests are
welcome.

---

## License

[MIT](LICENSE).

---

## Acknowledgments

This tool depends on free public APIs from [OpenAlex](https://openalex.org/),
[NCBI PubMed](https://pubmed.ncbi.nlm.nih.gov/), [Semantic
Scholar](https://www.semanticscholar.org/), [arXiv](https://arxiv.org/) and
[Crossref](https://www.crossref.org/). Please respect their rate limits and
terms of service.

The authors designed, implemented, tested and validated Literature
Collector. AI coding tools were used during implementation for
boilerplate and routine refactoring under the authors' direction.