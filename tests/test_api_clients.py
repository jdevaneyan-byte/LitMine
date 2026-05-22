"""Mocked-HTTP tests for the data-source API clients.

These don't hit the network. They verify that each client correctly parses
representative response shapes and produces the unified record dict the
rest of the app depends on:

    {"title", "doi", "abstract", "authors", "year", "source", "url"}

If an upstream API changes shape, these tests give a clear, fast signal.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import responses

from api import arxiv, openalex, pubmed, references, semantic_scholar


REQUIRED_KEYS = {"title", "doi", "abstract", "authors", "year", "source", "url"}


# OpenAlex

class OpenAlexTests(unittest.TestCase):
    @responses.activate
    def test_search_articles_parses_minimal_response(self):
        body = {
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "doi": "https://doi.org/10.1/abc",
                    "title": "Sample OpenAlex Paper",
                    "abstract_inverted_index": {"hello": [0], "world": [1]},
                    "publication_year": 2024,
                    "authorships": [
                        {"author": {"display_name": "Alice Smith"}},
                        {"author": {"display_name": "Bob Jones"}},
                    ],
                    "type": "article",
                    "primary_location": {"landing_page_url": "https://example.org/abc"},
                }
            ]
        }
        responses.add(
            responses.GET,
            "https://api.openalex.org/works",
            json=body,
            status=200,
        )
        out = openalex.search_articles("test", max_results=5, year_from=2020)
        self.assertEqual(len(out), 1)
        rec = out[0]
        self.assertTrue(REQUIRED_KEYS.issubset(rec.keys()))
        self.assertEqual(rec["source"], "OpenAlex")
        self.assertEqual(rec["year"], 2024)
        self.assertIn("Alice Smith", rec["authors"])
        self.assertEqual(rec["pub_type"], "article")
        # OpenAlex stores the abstract as an inverted index — make sure we
        # reconstructed something usable.
        self.assertIn("hello", rec["abstract"].lower())

    @responses.activate
    def test_search_both_uses_article_or_review_filter(self):
        responses.add(
            responses.GET,
            "https://api.openalex.org/works",
            json={"results": []},
            status=200,
        )
        openalex.search_both("test", max_results=5, year_from=2020)
        # The OR filter (type:article|review) must be present so reviews aren't
        # silently dropped in 'Both' mode.
        sent = responses.calls[0].request.url
        self.assertIn("type%3Aarticle%7Creview", sent)  # url-encoded "type:article|review"


# PubMed

class PubMedTests(unittest.TestCase):
    SEARCH_JSON = {"esearchresult": {"idlist": ["12345"]}}
    EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <Article>
        <ArticleTitle>Sample PubMed Paper</ArticleTitle>
        <Abstract>
          <AbstractText>An abstract about something.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author>
          <Author><LastName>Roe</LastName><ForeName>John</ForeName></Author>
        </AuthorList>
        <Journal>
          <JournalIssue>
            <PubDate><Year>2023</Year></PubDate>
          </JournalIssue>
        </Journal>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">12345</ArticleId>
        <ArticleId IdType="doi">10.1/pubmed-sample</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>"""

    @responses.activate
    def test_search_articles_parses_xml(self):
        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            json=self.SEARCH_JSON,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            body=self.EFETCH_XML,
            status=200,
            content_type="application/xml",
        )
        out = pubmed.search_articles("test", max_results=5, year_from=2020)
        self.assertEqual(len(out), 1)
        rec = out[0]
        self.assertTrue(REQUIRED_KEYS.issubset(rec.keys()))
        self.assertEqual(rec["source"], "PubMed")
        self.assertEqual(rec["year"], 2023)
        self.assertEqual(rec["doi"], "10.1/pubmed-sample")
        self.assertIn("Doe Jane", rec["authors"])

    @responses.activate
    def test_search_articles_empty_pmids(self):
        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            json={"esearchresult": {"idlist": []}},
            status=200,
        )
        out = pubmed.search_articles("nothingmatches", max_results=5)
        self.assertEqual(out, [])


# Semantic Scholar

class SemanticScholarTests(unittest.TestCase):
    @responses.activate
    def test_search_articles_parses_response(self):
        body = {
            "data": [
                {
                    "title": "Sample S2 Paper",
                    "abstract": "abstract text",
                    "year": 2022,
                    "authors": [{"name": "Carol Lee"}, {"name": "Dan Park"}],
                    "externalIds": {"DOI": "10.1/s2-sample", "PubMed": "98765"},
                    "url": "https://semanticscholar.org/paper/abc",
                    "publicationTypes": ["JournalArticle"],
                }
            ]
        }
        responses.add(
            responses.GET,
            "https://api.semanticscholar.org/graph/v1/paper/search",
            json=body,
            status=200,
        )
        out = semantic_scholar.search_articles("test", max_results=5, year_from=2020)
        self.assertEqual(len(out), 1)
        rec = out[0]
        self.assertTrue(REQUIRED_KEYS.issubset(rec.keys()))
        self.assertEqual(rec["source"], "Semantic Scholar")
        self.assertEqual(rec["year"], 2022)
        self.assertEqual(rec["doi"], "10.1/s2-sample")
        self.assertIn("Carol Lee", rec["authors"])
        self.assertEqual(rec["pub_type"], "JournalArticle")

    @responses.activate
    def test_search_articles_drops_books_and_reviews(self):
        body = {
            "data": [
                {"title": "A journal article", "year": 2022, "authors": [],
                 "externalIds": {"DOI": "10.1/a"}, "publicationTypes": ["JournalArticle"]},
                {"title": "A book", "year": 2021, "authors": [],
                 "externalIds": {"DOI": "10.1/b"}, "publicationTypes": ["Book"]},
                {"title": "A dataset", "year": 2020, "authors": [],
                 "externalIds": {"DOI": "10.1/c"}, "publicationTypes": ["Dataset"]},
                {"title": "A review", "year": 2023, "authors": [],
                 "externalIds": {"DOI": "10.1/d"}, "publicationTypes": ["Review"]},
                {"title": "Untyped paper", "year": 2022, "authors": [],
                 "externalIds": {"DOI": "10.1/e"}, "publicationTypes": []},
            ]
        }
        responses.add(
            responses.GET,
            "https://api.semanticscholar.org/graph/v1/paper/search",
            json=body,
            status=200,
        )
        out = semantic_scholar.search_articles("test", max_results=50, year_from=2000)
        titles = {r["title"] for r in out}
        # Book + Dataset dropped (junk); Review dropped (article mode); untyped kept.
        self.assertIn("A journal article", titles)
        self.assertIn("Untyped paper", titles)
        self.assertNotIn("A book", titles)
        self.assertNotIn("A dataset", titles)
        self.assertNotIn("A review", titles)

    @responses.activate
    def test_search_both_keeps_reviews_drops_books(self):
        body = {
            "data": [
                {"title": "A journal article", "year": 2022, "authors": [],
                 "externalIds": {"DOI": "10.1/a"}, "publicationTypes": ["JournalArticle"]},
                {"title": "A review", "year": 2023, "authors": [],
                 "externalIds": {"DOI": "10.1/d"}, "publicationTypes": ["Review"]},
                {"title": "A book", "year": 2021, "authors": [],
                 "externalIds": {"DOI": "10.1/b"}, "publicationTypes": ["Book"]},
            ]
        }
        responses.add(
            responses.GET,
            "https://api.semanticscholar.org/graph/v1/paper/search",
            json=body,
            status=200,
        )
        out = semantic_scholar.search_both("test", max_results=50, year_from=2000)
        titles = {r["title"] for r in out}
        self.assertIn("A journal article", titles)
        self.assertIn("A review", titles)   # both mode keeps reviews
        self.assertNotIn("A book", titles)  # junk still dropped


# arXiv

class ArxivTests(unittest.TestCase):
    SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.55555v1</id>
    <published>2024-01-15T10:00:00Z</published>
    <title>Sample arXiv Preprint About Catalysis</title>
    <summary>An overview of a catalytic process.</summary>
    <author><name>Eve Author</name></author>
    <arxiv:doi>10.1/arxiv-sample</arxiv:doi>
  </entry>
</feed>"""

    @responses.activate
    def test_search_articles_parses_atom(self):
        responses.add(
            responses.GET,
            "http://export.arxiv.org/api/query",
            body=self.SAMPLE_FEED,
            status=200,
            content_type="application/atom+xml",
        )
        # Sleep in arxiv module would slow tests down; patch it out.
        with patch("api.arxiv.time.sleep"):
            out = arxiv.search_articles("catalysis", max_results=5, year_from=2020)
        self.assertEqual(len(out), 1)
        rec = out[0]
        self.assertTrue(REQUIRED_KEYS.issubset(rec.keys()))
        self.assertEqual(rec["source"], "arXiv")
        self.assertEqual(rec["year"], 2024)
        self.assertEqual(rec["doi"], "10.1/arxiv-sample")


# References (Semantic Scholar + Crossref fallback)

class ReferencesTests(unittest.TestCase):
    @responses.activate
    def test_fetch_references_via_s2(self):
        body = {
            "data": [
                {
                    "citedPaper": {
                        "title": "Cited Work A",
                        "year": 2021,
                        "authors": [{"name": "X Y"}],
                        "externalIds": {"DOI": "10.1/cited-a"},
                        "publicationTypes": ["Review"],
                        "venue": "Venue X",
                        "abstract": "abs",
                        "url": "https://semanticscholar.org/paper/aaa",
                    }
                },
                {
                    "citedPaper": {
                        "title": "Cited Work B",
                        "year": 2018,
                        "authors": [{"name": "Z W"}],
                        "externalIds": {"DOI": "10.1/cited-b"},
                        "publicationTypes": ["JournalArticle"],
                        "venue": "Venue Y",
                        "abstract": "",
                        "url": "https://semanticscholar.org/paper/bbb",
                    }
                },
            ]
            # no "next" → paging stops after one page
        }
        responses.add(
            responses.GET,
            "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1/parent/references",
            json=body,
            status=200,
        )
        with patch("api.references.time.sleep"):
            refs = references.fetch_references("10.1/parent")
        self.assertEqual(len(refs), 2)
        # Review flagging via publicationTypes.
        self.assertTrue(refs[0]["is_review"])
        self.assertFalse(refs[1]["is_review"])
        self.assertEqual(refs[0]["source"], "Semantic Scholar")

    @responses.activate
    def test_fetch_references_falls_back_to_crossref(self):
        # S2 returns 404 → fall through to Crossref.
        responses.add(
            responses.GET,
            "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1/missing/references",
            status=404,
        )
        crossref_body = {
            "message": {
                "reference": [
                    {
                        "DOI": "10.1/cited-x",
                        "article-title": "Crossref-only Cited Title",
                        "year": "2020",
                        "journal-title": "Some Journal",
                    }
                ]
            }
        }
        responses.add(
            responses.GET,
            "https://api.crossref.org/works/10.1/missing",
            json=crossref_body,
            status=200,
        )
        # The Crossref enricher inside _enrich_crossref_refs will hit
        # /works/{doi} again per reference that has a DOI. Mock that too.
        responses.add(
            responses.GET,
            "https://api.crossref.org/works/10.1/cited-x",
            json={"message": {"title": ["Crossref-only Cited Title"]}},
            status=200,
        )
        with patch("api.references.time.sleep"):
            refs = references.fetch_references("10.1/missing")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["source"], "Crossref")
        self.assertEqual(refs[0]["doi"], "10.1/cited-x")
        self.assertEqual(refs[0]["year"], 2020)


class IssnCaptureTests(unittest.TestCase):
    def test_openalex_parse_includes_issn(self):
        from api.openalex import _parse_work
        work = {
            "title": "T", "id": "https://openalex.org/W1",
            "primary_location": {"source": {"display_name": "JACS", "issn_l": "0002-7863"}},
        }
        self.assertEqual(_parse_work(work)["issn"], "0002-7863")

    def test_s2_parse_includes_issn(self):
        from api.semantic_scholar import _parse_paper
        paper = {"title": "T", "publicationVenue": {"issn": "1234-5678"}}
        self.assertEqual(_parse_paper(paper)["issn"], "1234-5678")

    def test_arxiv_parse_has_empty_issn(self):
        import xml.etree.ElementTree as ET
        from api.arxiv import _parse_entry
        xml = ('<entry xmlns="http://www.w3.org/2005/Atom">'
               '<title>T</title><summary>s</summary>'
               '<published>2024-01-01T00:00:00Z</published>'
               '<id>http://arxiv.org/abs/2401.00001v1</id></entry>')
        entry = ET.fromstring(xml)
        self.assertEqual(_parse_entry(entry)["issn"], "")


if __name__ == "__main__":
    unittest.main()
