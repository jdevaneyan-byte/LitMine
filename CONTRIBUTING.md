# Contributing to Literature Collector

Thanks for your interest! Bug reports, feature ideas and pull requests are
all welcome.

## Reporting bugs

Open a GitHub issue with:

- What you tried (commands, screenshots if relevant)
- What you expected
- What happened instead
- Your Python version, OS, and (if relevant) which database the issue
  involves

## Suggesting features

Open an issue first to discuss the idea before sending a PR — this avoids
duplicate work and lets maintainers help shape scope. We try to keep the
core small and local-first; features that require new heavyweight
dependencies need a strong case.

## Development setup

```bash
git clone https://github.com/FILL_IN_USERNAME/literature-collector.git
cd literature-collector
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
pip install -r requirements-dev.txt

streamlit run app.py
```

## Running tests

```bash
pytest -q
```

PRs must keep the existing tests green. New features should add tests.

## Code style

- Python 3.9+ compatible. Use `from __future__ import annotations` when you
  need PEP 604 union syntax (e.g. `dict | None`) in module-level
  annotations.
- Standard library + `pandas`, `requests`, `sqlalchemy`, `streamlit`,
  `openpyxl` are first-class. Adding a new top-level dependency needs a
  comment in the PR explaining why.
- Keep `utils/` modules small and independently testable. Streamlit-only
  helpers go in `pages/` or `utils/keybinds.py` (which is the only
  Streamlit-coupled `utils/` module).
- Comment the *why*, not the *what*. Skip docstrings unless the function
  is part of a public surface; named functions and types should be enough
  for most cases.

## Database changes

The SQLite schema lives in `database.py`. If you add or rename a column:

1. Edit the SQLAlchemy model.
2. Add a row to the `migrations` list in `init_db()` so existing
   user databases pick up the new column on next launch.
3. If a migration cannot be expressed as a simple `ALTER TABLE`, write a
   small helper that runs on startup and is idempotent.

## API clients

`api/openalex.py`, `api/pubmed.py`, `api/semantic_scholar.py`,
`api/arxiv.py` and `api/references.py` all share the same response shape
(see `_parse_*` helpers). New sources should produce the same dict keys so
the dedup and storage layers work without changes:

```
{"title", "doi", "abstract", "authors", "year", "source", "url"}
```

## Pull request checklist

- [ ] `pytest -q` passes
- [ ] No new dependencies (or justified in the PR description)
- [ ] New behaviour has a test
- [ ] User-facing copy is plain English; jargon has a tooltip
- [ ] No emojis in code or comments unless they're already in the file

## Code of conduct

Be kind. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
