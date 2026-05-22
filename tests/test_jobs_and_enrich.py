"""Tests for job-state I/O (atomic writes + cancel tokens) and DOI enrichment."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import responses

from utils import enrich, job_io


class JobIoTests(unittest.TestCase):
    def test_write_atomic_round_trip(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "job.json"
            job_io.write_atomic(p, {"a": 1, "log": []})
            self.assertEqual(job_io.read_json(p), {"a": 1, "log": []})

    def test_patch_updates_existing(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "job.json"
            job_io.write_atomic(p, {"completed": 0})
            job_io.patch(p, completed=5)
            self.assertEqual(job_io.read_json(p)["completed"], 5)

    def test_read_json_missing_returns_none(self):
        with TemporaryDirectory() as d:
            self.assertIsNone(job_io.read_json(Path(d) / "nope.json"))

    def test_cancel_token_round_trip(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "job.json"
            job_io.write_atomic(p, {"done": False})
            self.assertFalse(job_io.is_cancelled(p))
            job_io.request_cancel(p)
            self.assertTrue(job_io.is_cancelled(p))
            # Cancelling must not clobber other fields.
            self.assertFalse(job_io.read_json(p)["done"])

    def test_append_log(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "job.json"
            job_io.write_atomic(p, {"log": ["a"]})
            job_io.append_log(p, "b")
            self.assertEqual(job_io.read_json(p)["log"], ["a", "b"])


class EnrichTests(unittest.TestCase):
    def test_needs_enrichment(self):
        self.assertTrue(enrich.needs_enrichment({"doi": "10.1/x", "title": "DOI 10.1/x"}))
        self.assertTrue(enrich.needs_enrichment({"doi": "10.1/x", "title": "Real", "year": None, "authors": ""}))
        self.assertFalse(enrich.needs_enrichment({"doi": "", "title": "DOI 10.1/x"}))
        self.assertFalse(
            enrich.needs_enrichment({"doi": "10.1/x", "title": "Real", "year": 2020, "authors": "A B"})
        )

    @responses.activate
    def test_enrich_record_fills_metadata(self):
        responses.add(
            responses.GET,
            "https://api.crossref.org/works/10.1/x",
            json={
                "message": {
                    "title": ["A Real Title"],
                    "issued": {"date-parts": [[2021, 5]]},
                    "author": [{"given": "Jane", "family": "Doe"}],
                    "type": "journal-article",
                    "abstract": "<jats:p>Hello world.</jats:p>",
                }
            },
            status=200,
        )
        rec = {"doi": "10.1/x", "title": "DOI 10.1/x", "year": None, "authors": ""}
        out = enrich.enrich_record(rec)
        self.assertEqual(out["title"], "A Real Title")
        self.assertEqual(out["year"], 2021)
        self.assertIn("Jane Doe", out["authors"])
        self.assertEqual(out["abstract"], "Hello world.")
        self.assertEqual(out["pub_type"], "journal-article")

    @responses.activate
    def test_enrich_record_no_doi_unchanged(self):
        rec = {"doi": "", "title": "DOI ???"}
        self.assertEqual(enrich.enrich_record(dict(rec)), rec)

    @responses.activate
    def test_enrich_records_counts_and_caps(self):
        responses.add(
            responses.GET,
            "https://api.crossref.org/works/10.1/a",
            json={"message": {"title": ["T A"]}},
            status=200,
        )
        recs = [
            {"doi": "10.1/a", "title": "DOI 10.1/a"},
            {"doi": "", "title": "skip me"},
        ]
        with patch("utils.enrich.time.sleep"):
            n = enrich.enrich_records(recs)
        self.assertEqual(n, 1)
        self.assertEqual(recs[0]["title"], "T A")


class SearchRunnerCancelTests(unittest.TestCase):
    def test_cancel_returns_promptly_with_slow_source(self):
        """When should_cancel becomes True, _run must abandon a slow source and
        return quickly instead of blocking up to the per-source timeout."""
        import time

        from utils import search_runner

        def slow_search(query, max_per_source, year_from):
            time.sleep(30)  # would block for a long time if awaited
            return [{"title": "should not appear", "source": "OpenAlex"}]

        with patch("utils.search_runner.openalex.search_articles", slow_search):
            start = time.monotonic()
            results, _errors = search_runner.run_article_search_with_status(
                "x", max_per_source=10, year_from=0,
                use_openalex=True, use_pubmed=False, use_s2=False, use_arxiv=False,
                should_cancel=lambda: True,
            )
            elapsed = time.monotonic() - start

        self.assertLess(elapsed, 5, "cancel did not short-circuit the slow source")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
