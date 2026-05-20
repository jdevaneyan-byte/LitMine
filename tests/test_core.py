"""Core unit tests. Run with: pytest -q"""

import io
import unittest
import xml.etree.ElementTree as ET

import pandas as pd

from utils.dedup import deduplicate, normalize_doi, normalize_title
from utils.import_refs import parse_bibtex, parse_csv, parse_doi_list, parse_ris
from utils.search_query import build_query


class NormalizationTests(unittest.TestCase):
    def test_normalize_doi_strips_https(self):
        self.assertEqual(normalize_doi("https://doi.org/10.1000/ABC"), "10.1000/abc")

    def test_normalize_doi_handles_empty(self):
        self.assertEqual(normalize_doi(None), "")
        self.assertEqual(normalize_doi(""), "")

    def test_normalize_title_removes_punct(self):
        self.assertEqual(normalize_title("A Study: of  Things!"), "a study of things")

    def test_normalize_title_handles_none(self):
        self.assertEqual(normalize_title(None), "")


class DeduplicationTests(unittest.TestCase):
    def test_fuzzy_title_dedup(self):
        rows = [
            {"title": "Deep learning for clinical diagnosis", "doi": ""},
            {"title": "Deep Learning for Clinical Diagnosis.", "doi": ""},
            {"title": "Different article entirely about cats", "doi": ""},
        ]
        out = deduplicate(rows)
        self.assertEqual(len(out), 2)

    def test_doi_dedup_overrides_title_difference(self):
        rows = [
            {"title": "First wording", "doi": "10.1/abc"},
            {"title": "Completely different wording but same DOI", "doi": "10.1/abc"},
        ]
        out = deduplicate(rows)
        self.assertEqual(len(out), 1)

    def test_short_titles_not_fuzzy_matched(self):
        # Titles below 35 chars should not collapse on fuzzy alone.
        rows = [
            {"title": "Short A", "doi": ""},
            {"title": "Short B", "doi": ""},
        ]
        out = deduplicate(rows)
        self.assertEqual(len(out), 2)


class ImportRefsTests(unittest.TestCase):
    def test_parse_doi_list_dedupes(self):
        rows = parse_doi_list("See 10.1000/test and https://doi.org/10.1000/test")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doi"], "10.1000/test")

    def test_parse_csv_minimal(self):
        text = "title,authors,year,doi\nPaper One,Doe,2024,10.1/x\nPaper Two,Roe,2023,\n"
        rows = parse_csv(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["title"], "Paper One")
        self.assertEqual(rows[0]["doi"], "10.1/x")
        self.assertEqual(rows[1]["year"], 2023)

    def test_parse_bibtex_minimal(self):
        bib = "@article{abc, title={Some Paper}, author={Doe, J. and Roe, R.}, year={2024}, doi={10.1/xyz}}"
        rows = parse_bibtex(bib)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Some Paper")
        self.assertEqual(rows[0]["year"], 2024)
        self.assertEqual(rows[0]["doi"], "10.1/xyz")

    def test_parse_ris_minimal(self):
        # RIS format requires the "TAG  - VALUE" pattern; ER line still needs
        # the trailing space so it matches the line[2:6] == "  - " check.
        ris = (
            "TY  - JOUR\n"
            "TI  - A RIS Paper\n"
            "AU  - Doe, J.\n"
            "AU  - Roe, R.\n"
            "PY  - 2022\n"
            "DO  - 10.1/ris\n"
            "ER  - \n"
        )
        rows = parse_ris(ris)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "A RIS Paper")
        self.assertEqual(rows[0]["year"], 2022)


class SearchQueryTests(unittest.TestCase):
    def test_build_query_basic(self):
        q = build_query("machine learning", "diagnosis", "clinical, imaging", "animal")
        self.assertEqual(q, '"machine learning" diagnosis (clinical OR imaging) NOT animal')


class ExcelExportTests(unittest.TestCase):
    def test_rows_to_excel_returns_xlsx_bytes(self):
        from utils.excel_export import rows_to_excel

        rows = [
            {"#": 1, "Title": "Paper A", "Year": 2024, "DOI": "10.1/a"},
            {"#": 2, "Title": "Paper B", "Year": 2023, "DOI": "10.1/b"},
        ]
        data = rows_to_excel(rows)
        self.assertIsInstance(data, (bytes, bytearray))
        # xlsx files are zip archives that start with PK.
        self.assertTrue(data[:2] == b"PK")
        # Round-trip read with pandas to confirm contents.
        df = pd.read_excel(io.BytesIO(data))
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]["Title"], "Paper A")

    def test_filename_for_sanitizes(self):
        from utils.excel_export import filename_for

        name = filename_for("My / Bad: Name", "library", "xlsx")
        self.assertTrue(name.endswith(".xlsx"))
        self.assertNotIn("/", name)
        self.assertNotIn(":", name)


class ExcelImportTests(unittest.TestCase):
    def test_parse_curated_excel_finds_header_row(self):
        from utils.excel_import import parse_curated_excel

        # Build an Excel that mimics the user's master sheet shape:
        # a banner row, then a header row containing Title and DOI.
        df = pd.DataFrame(
            [
                ["My banner", None, None, None, None],
                ["Year", "Title", "DOI", "Journal", "Theme"],
                [2024, "Paper A", "10.1/a", "JCS", "amides"],
                [2023, "Paper B", "10.1/b", "JOC", "esters"],
            ]
        )
        buf = io.BytesIO()
        df.to_excel(buf, index=False, header=False, engine="openpyxl")
        rows = parse_curated_excel("master.xlsx", buf.getvalue())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["title"], "Paper A")
        self.assertEqual(rows[0]["doi"], "10.1/a")
        self.assertEqual(rows[0]["year"], 2024)


class FindDuplicatesTests(unittest.TestCase):
    def test_normalize_title_for_clusters(self):
        from utils.find_duplicates import normalize_title as norm

        self.assertEqual(norm("Hello, World!"), "hello world")
        self.assertEqual(norm(None), "")

    def test_pick_keeper_prefers_doi_and_longer_abstract(self):
        from utils.find_duplicates import pick_keeper

        class Fake:
            def __init__(self, id_, doi="", abstract="", authors="", title=""):
                self.id = id_
                self.doi = doi
                self.abstract = abstract
                self.authors = authors
                self.title = title

        members = [
            Fake(1, doi="", abstract="short"),
            Fake(2, doi="10.1/x", abstract="a longer abstract here"),
            Fake(3, doi="10.1/x", abstract=""),
        ]
        keeper = pick_keeper(members)
        self.assertEqual(keeper.id, 2)


class ArxivParserTests(unittest.TestCase):
    SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <published>2024-01-15T10:00:00Z</published>
    <title>A Review of Recent Advances in Amide Chemistry</title>
    <summary>An overview of amide bond formation and cleavage.</summary>
    <author><name>Jane Doe</name></author>
    <author><name>John Roe</name></author>
    <arxiv:doi>10.1/sample</arxiv:doi>
  </entry>
</feed>
"""

    def test_parse_entry_yields_expected_fields(self):
        from api.arxiv import _parse_entry

        root = ET.fromstring(self.SAMPLE)
        entry = root.find("{http://www.w3.org/2005/Atom}entry")
        parsed = _parse_entry(entry)
        self.assertEqual(parsed["year"], 2024)
        self.assertEqual(parsed["doi"], "10.1/sample")
        self.assertEqual(parsed["source"], "arXiv")
        self.assertIn("Jane Doe", parsed["authors"])
        self.assertEqual(parsed["title"].split()[0], "A")

    def test_looks_like_review_title(self):
        from api.arxiv import _looks_like_review

        self.assertTrue(_looks_like_review("Recent Advances in X"))
        self.assertTrue(_looks_like_review("A review of Y"))
        self.assertFalse(_looks_like_review("Synthesis of compound Z"))


class ReferencesParserTests(unittest.TestCase):
    def test_parse_s2_paper(self):
        from api.references import _parse_s2_paper

        raw = {
            "title": "Sample Cited Work",
            "year": 2020,
            "authors": [{"name": "A. Author"}, {"name": "B. Author"}],
            "externalIds": {"DOI": "10.1/cite"},
            "publicationTypes": ["Review"],
            "venue": "Some Journal",
            "abstract": "abstract text",
            "url": "https://semanticscholar.org/paper/abc",
        }
        out = _parse_s2_paper(raw)
        self.assertEqual(out["doi"], "10.1/cite")
        self.assertEqual(out["year"], 2020)
        self.assertTrue(out["is_review"])
        self.assertEqual(out["source"], "Semantic Scholar")

    def test_looks_like_review(self):
        from api.references import _looks_like_review

        self.assertTrue(_looks_like_review("Recent advances in X", []))
        self.assertTrue(_looks_like_review("X", ["Review"]))
        self.assertFalse(_looks_like_review("Synthesis of X", []))

    def test_looks_like_book(self):
        from api.references import _looks_like_book

        self.assertTrue(_looks_like_book(["Book"]))
        self.assertTrue(_looks_like_book(["BookSection"]))
        self.assertFalse(_looks_like_book(["JournalArticle"]))
        self.assertFalse(_looks_like_book([]))

    def test_parse_s2_paper_flags_book(self):
        from api.references import _parse_s2_paper

        out = _parse_s2_paper({
            "title": "Some Book",
            "year": 2010,
            "externalIds": {"DOI": "10.1/book"},
            "publicationTypes": ["Book"],
        })
        self.assertTrue(out["is_book"])
        self.assertFalse(out["is_review"])


class KeybindsImportSmoke(unittest.TestCase):
    def test_module_imports(self):
        # keybinds.py is pure JS injection; only smoke-test that it imports.
        from utils import keybinds

        self.assertTrue(hasattr(keybinds, "bind_keys"))


if __name__ == "__main__":
    unittest.main()
