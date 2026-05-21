# LitMine — Roadmap & Publication Plan

*One page. The whole picture, so it isn't carried in your head.*

---

## 1. Where we are (DONE — built & tested)

- Multi-source collection (OpenAlex, Semantic Scholar, PubMed, Crossref, arXiv) + deduplication
- Durable background jobs (survive refresh, manual cancel, atomic writes)
- Screening workflow, trash/restore, full metadata exports (Excel/CSV/JSON)
- React + FastAPI frontend over the same local SQLite as the Streamlit app
- 3D citation/author/journal network maps
- **Type-aware completeness audit** (chapters/corrections/editorials don't require an abstract)
- **Gap-fill resolver**: Crossref → OpenAlex → Semantic Scholar → Europe PMC (by DOI),
  **+ a strict title-search fallback** for journal/type
- **Safety gate**: near-exact title (≥0.95) + year ±1 + author-surname overlap; venue sanity
  check; never overwrites a record's own DOI  *(verified: rejects the wrong-paper fills a
  naive approach makes)*
- **Provenance + honest flagging**: `abstract_unavailable` = "no open abstract" instead of guessing
- Bring-your-own-key config (each provider optional, graceful degradation)

## 2. What's left (FINITE — known how)

- [ ] Migrate to the OpenAlex API key (required since Feb 2026) — small
- [ ] Per-provider rate limiting + **batch lookups** (S2 `/paper/batch`, OpenAlex filters) + caching
      — fixes large-project speed; Semantic Scholar's 1 req/sec is the only real bottleneck
- [ ] (Optional, deferred) publisher plugins (Springer/Elsevier) — institutional only
- [ ] Tests for the resolver gate + docs (README API-keys section, `.env.example`)
- [ ] Write the paper

## 3. Inherent limits we DOCUMENT (not bugs)

- Elsevier/Springer abstracts are **paywalled** — no free tool can fetch them. We state this
  plainly and flag those papers. ~92% of the residual gap is just these two publishers.
- Open-source abstract recovery ceiling ≈ **28–50%** of genuine gaps. The rest is paywalled.

## 4. The paper

**Venue:** SoftwareX (no repo-age gate; ~3-week review) first choice; JOSS later if desired.

**Title (working):** *LitMine: a local-first literature workspace with provenance-tracked,
safety-gated metadata completion from open sources.*

**Narrative:** A trustworthy literature corpus needs complete metadata, but open sources are
fragmented and inconsistent. LitMine collects across sources and completes gaps with a
resolver that (a) fills only empty fields, (b) trusts a match only when title+year+author agree,
and (c) honestly flags what open sources cannot provide.

**Sections:** Summary · Statement of need · Design (collection, dedup, resolver cascade,
safety gate, provenance) · Empirical evaluation · Limitations · Availability.

**Figures/tables (straight from our experiments — already have the data):**
1. Completeness before/after the resolver (Amide: 3,253 → 3,593 complete)
2. Abstract recovery by source (Europe PMC + S2 carry it; Crossref/OpenAlex ≈ 0 for gaps)
3. Residual gap by publisher (Elsevier 63% / Springer 29%) — the paywall boundary
4. Safe vs naive matching: wrong-paper fills caught by the gate (id 3186/3558/1627)

**Limitations section = our strength:** the 28% open ceiling, the paywall concentration, and
the wrong-match danger with our mitigation. This is rigor, and reviewers reward it.

## 5. Order of operations

1. Finish §2 engineering (OpenAlex key → throttle/batch/cache → tests/docs)
2. Freeze scope: open-sources-only; publisher plugins documented as optional/institutional
3. Generate the 4 figures from the data we already collected
4. Draft → submit to SoftwareX
