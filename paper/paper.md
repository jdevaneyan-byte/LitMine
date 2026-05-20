---
title: 'LitMine: a local-first workspace for multi-database literature search, citation extraction, and PRISMA-style screening'
tags:
  - Python
  - Streamlit
  - literature review
  - systematic review
  - bibliometrics
  - cheminformatics
  - OpenAlex
  - PubMed
  - Semantic Scholar
authors:
  - name: FILL IN AUTHOR NAME
    orcid: 0000-0000-0000-0000
    corresponding: true
    affiliation: 1
affiliations:
  - name: FILL IN AFFILIATION
    index: 1
date: 19 May 2026
bibliography: paper.bib
---

# Summary

Literature reviews are the entry point to most academic research, but the
day-to-day workflow is fragmented. Searching multiple bibliographic
databases, harmonising their metadata, identifying which papers are cited by
a curated set of review articles, and screening the resulting set to a
manageable shortlist typically requires switching between several
single-purpose tools. **LitMine** is an open-source Python
application that unifies these steps into a single local-first workspace.
It searches OpenAlex [@priem2022openalex], PubMed [@sayers2021ncbi],
Semantic Scholar [@kinney2023semanticscholar] and arXiv from one screen,
imports curated reference lists in common formats (Excel, CSV, BibTeX,
RIS), bulk-extracts cited references from a user-supplied set of seed
papers (typically a mix of review and primary articles) via Semantic
Scholar with a Crossref [@hendricks2020crossref] fallback,
detects and merges duplicates, supports PRISMA-style [@page2021prisma]
screening with keyboard shortcuts and preset exclusion reasons, and exports
formatted Excel workbooks ready for downstream analysis. All data lives in
a local SQLite database; no cloud account is required.

# Statement of need

Existing literature-management tools each solve a slice of the workflow.
Reference managers such as Zotero and EndNote excel at storing, formatting,
and citing items, but offer limited support for multi-database search or
systematic screening. ASReview [@vandeschoot2021asreview] provides
state-of-the-art active-learning screening for a previously assembled set
of records, but does not itself perform database search or bulk citation
extraction. Rayyan [@ouzzani2016rayyan] offers a polished collaborative
screening interface as a cloud service. Local Citation Network
[@hill2022localcitationnetwork] visualises the local citation
neighbourhood of a small seed set. Command-line tools such as
`paper-search-mcp` aggregate searches across many sources but lack a UI or
a project model. R packages such as `openalexR` [@aria2024openalexr]
provide deep access to a single database for users comfortable with R.

Small research groups outside computer science routinely need a single
tool that (i) searches several databases at once, (ii) imports an existing
curated set of seed papers (reviews or key primary articles) and pulls
back everything they cite, and (iii) supports a reproducible screening
pass — without forcing the data into a
cloud service that may be incompatible with institutional data policies.
LitMine addresses this gap by combining database search,
citation extraction, deduplication, screening, and structured export in
one local Python application that can be run on a laptop or shared as a
single-machine deployment in a research group.

# Features

- **Multi-database search.** Queries OpenAlex, PubMed, Semantic Scholar
  and arXiv in parallel for a single topic or a batch of topics. Results
  are deduplicated across sources by DOI, external identifier, and fuzzy
  title match (`SequenceMatcher` ratio ≥ 0.94 for titles of length
  ≥ 35 characters).
- **Curated seed-paper citation extraction.** Users supply an Excel file
  of DOIs for *seed papers* — typically a mix of review articles and key
  primary papers — and the tool fetches each seed's reference list from
  Semantic Scholar's `/paper/DOI:{doi}/references` endpoint, with a
  Crossref `/works/{doi}` fallback for records not indexed by Semantic
  Scholar. A configurable year floor and a "keep reviews regardless of
  year" toggle implement the filter logic typical of scoping reviews.
  References whose title or publication-type metadata indicates a review
  are flagged so users can decide whether to recurse on them.
- **Background-thread jobs.** Long-running searches and extractions run
  in daemon threads that write progress to a JSON file. The UI polls the
  file with `st.fragment(run_every=...)` and re-attaches to in-flight
  jobs after a browser refresh, so closing the tab does not interrupt
  work.
- **Duplicate detection and merge.** A post-hoc scanner clusters
  records by exact DOI, exact normalised title, and fuzzy title within
  the same publication year. A merge operation copies any non-empty
  fields (DOI, abstract, authors, URL) from the dropped rows into the
  keeper before deletion, so no metadata is lost.
- **PRISMA-style screening.** Per-paper decisions (include / maybe /
  exclude / unscreened) with single-key shortcuts (`I`, `M`, `E`, `N`)
  and a multi-select of preset exclusion reasons matching common PRISMA
  flow categories. A metric strip at the top of the library section
  shows running counts at each stage.
- **Formatted Excel export.** Workbooks are written via openpyxl with a
  frozen header row, auto-filter enabled, sensible per-column widths,
  text-wrap on long fields, and hyperlinked DOIs. CSV and JSON exports
  are also provided.
- **Local-first.** A single SQLite file holds all projects, articles,
  curated reviews and extracted citations. No cloud account or external
  service is required, and the database file can be moved between
  machines or shared via a network drive.

# Implementation

LitMine is implemented in Python 3.9+ using Streamlit
[@streamlit] for the web UI, SQLAlchemy for the SQLite data layer,
pandas for tabular processing, and `requests` for HTTP API access. The
codebase is organised into independent modules under `api/` (one file per
data source), `utils/` (search runner, background jobs, dedup, excel
export, duplicate scan, keybinds), and `pages/` (a single unified
workspace page plus the project list home page). Tests use the standard
library `unittest` runner with pytest discovery.

The package can be installed by cloning the repository and running
`pip install -r requirements.txt`; the only Python-side dependencies are
listed there.

# Use cases

We exercised LitMine on two ongoing chemistry literature
reviews in the authors' research group. In both projects, the curated
seed set was a mix of review articles and key primary papers (the
"references-to-mine" set), not exclusively reviews. Both runs were
performed on a laptop without paid API keys.

**Amide chemistry review.** A curated set of **51** seed-paper DOIs
(approximately 35% titled as review articles and 65% titled as primary
research papers, all deemed important enough to mine for cited
references) was supplied as an Excel sheet. The citation-extraction job
fetched **5,448** cited references in approximately 30 minutes.
Applying the default year floor of 2019 retained **1,183** candidate
research papers and flagged **182** further citations as
review-type for downstream consideration. A parallel keyword search
across OpenAlex, PubMed, Semantic Scholar and arXiv for ~250
amide-related queries returned **3,622** deduplicated papers
distributed across sources (OpenAlex: 1,698; Semantic Scholar: 1,159;
PubMed: 765). Together the two passes yielded a *de novo* candidate
set of approximately 4,800 unique papers for screening, assembled from
scratch in under one working day. Without the tool, building the same
dataset required manual reference chasing across publisher websites
and single-database searches over several days in a pilot run.

**Electrochemistry review.** A larger curated set of **279** seed-paper
DOIs (approximately 28% review-titled, 72% primary research) was
extracted in approximately three hours, yielding **34,382** cited
references. After year and publication-type filtering, **13,325**
candidate research papers were retained and **2,333** further citations
were flagged as reviews. The duplicate scanner reported no remaining
duplicates after the at-insert dedup ran, demonstrating that the
multi-stage deduplication scales without producing visible artefacts
at this size. A separate keyword sweep added a further **4,170**
deduplicated papers to the project's library.

These case studies illustrate that the tool's primary value is in
collapsing the *search → citation extraction → filter → screen*
pipeline from days to hours for projects in the 10²–10⁴ paper range
typical of a focused chemistry literature review, and that the seed
set need not be restricted to review articles — any paper with a
published reference list is a valid mining target.

# Acknowledgements

This work depends on the free public APIs of OpenAlex, NCBI PubMed,
Semantic Scholar, arXiv and Crossref. We thank the maintainers of those
services and of the open-source Python ecosystem on which Literature
Collector is built (notably Streamlit, SQLAlchemy, pandas, openpyxl,
and requests).

The authors designed, implemented, tested and validated Literature
Collector and conducted the chemistry case studies presented above. AI
coding tools were used during implementation to accelerate boilerplate
and routine refactoring under the authors' direction.
# References
