# Examples

Small files included to make a fresh install testable without hunting for
your own seed data. Used by reviewers and first-time users.

## `demo_seed_papers.csv`

Five real DOIs (amide-chemistry reviews and methodology papers) you can
import into the Workspace → **📥 Import my list** → *Curated reviews*
section to try the citation-extraction pipeline end-to-end. The full
extraction over these five DOIs hits Semantic Scholar and Crossref, fits
within the anonymous-pool rate limits, and finishes in under a minute.

**To use:**

1. Convert the CSV to Excel (Streamlit's importer expects `.xlsx`):
   - Open `examples/demo_seed_papers.csv` in Excel / LibreOffice / Numbers
   - Save As → `demo_seed_papers.xlsx`
2. In the app: **Workspace → 📥 Import my list → Curated reviews →
   upload**. Save. Then **🔗 Extract citations from reviews → Start
   extraction**.
3. You should see ~150–400 cited references collected within a minute,
   filtered to ~30–80 kept (year ≥ 2019) and a handful flagged as reviews.

## Suggested smoke-test for reviewers

```bash
pytest -q                          # should report 29 passed
streamlit run app.py               # then open http://localhost:8501
```

Inside the app:

1. **Home** → create a project named "Demo", topic *amide bond formation*,
   leave description empty.
2. **Workspace → 📥 Import my list → Curated reviews** → upload the
   demo Excel from this folder.
3. **🔗 Extract citations from reviews → Start extraction** → wait ~1 min.
4. **📚 Library** is empty; switch to the **Cited articles** view at the
   bottom of the Extract section to see the fetched references.
5. **🔍 Search the web** → "Multiple topics", paste two short queries on
   separate lines, Run all searches.
6. **📚 Library** → press `I` / `M` / `E` on a few rows to verify
   screening.
7. **⬇ Excel** download button → confirm the xlsx opens with frozen
   header, auto-filter, and full abstracts.

No API keys are required for any step.
