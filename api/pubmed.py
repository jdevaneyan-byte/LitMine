import os
import requests
import time
import xml.etree.ElementTree as ET
from typing import Optional

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "ReviewCollector"
EMAIL = "research@review-collector.app"


def _api_key_param() -> dict:
    key = os.getenv("NCBI_API_KEY", "")
    return {"api_key": key} if key else {}


def search_reviews(
    topic: str, max_results: int = 50, year_from: Optional[int] = None
) -> list[dict]:
    query = f"({topic}) AND Review[Publication Type]"
    if year_from:
        query += f" AND {year_from}:3000[PDAT]"
    return _search(query, max_results)


def search_articles(
    topic: str, max_results: int = 100, year_from: Optional[int] = None
) -> list[dict]:
    query = topic
    if year_from:
        query += f" AND {year_from}:3000[PDAT]"
    return _search(query, max_results)


def _search(query: str, max_results: int) -> list[dict]:
    try:
        resp = requests.get(
            f"{BASE_URL}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmax": min(max_results, 200),
                "retmode": "json",
                "tool": TOOL,
                "email": EMAIL,
                **_api_key_param(),
            },
            timeout=30,
        )
        resp.raise_for_status()
        pmids = resp.json().get("esearchresult", {}).get("idlist", [])
    except Exception as exc:
        raise RuntimeError(f"PubMed search failed: {exc}") from exc

    if not pmids:
        return []

    time.sleep(0.34)

    try:
        resp = requests.get(
            f"{BASE_URL}/efetch.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml",
                "rettype": "abstract",
                "tool": TOOL,
                "email": EMAIL,
                **_api_key_param(),
            },
            timeout=60,
        )
        resp.raise_for_status()
        return _parse_xml(resp.text)
    except Exception as exc:
        raise RuntimeError(f"PubMed fetch failed: {exc}") from exc


def _parse_xml(xml_text: str) -> list[dict]:
    results = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for article_el in root.findall(".//PubmedArticle"):
        try:
            citation = article_el.find("MedlineCitation")
            if citation is None:
                continue
            art = citation.find("Article")
            if art is None:
                continue

            title_el = art.find("ArticleTitle")
            title = "".join(title_el.itertext()) if title_el is not None else ""

            abstract_parts = []
            for ab in art.findall(".//AbstractText"):
                label = ab.get("Label", "")
                text = "".join(ab.itertext())
                if text:
                    abstract_parts.append(f"{label}: {text}" if label else text)
            abstract = " ".join(abstract_parts)

            year = None
            year_el = art.find(".//PubDate/Year")
            if year_el is not None and year_el.text:
                try:
                    year = int(year_el.text)
                except ValueError:
                    pass

            all_authors = art.findall(".//Author")
            authors = []
            for author in all_authors[:5]:
                last = author.findtext("LastName", "")
                first = author.findtext("ForeName", "")
                if last:
                    authors.append(f"{last} {first}".strip())
            authors_str = ", ".join(authors)
            if len(all_authors) > 5:
                authors_str += " et al."

            doi = ""
            pmid = ""
            for aid in article_el.findall(".//ArticleId"):
                if aid.get("IdType") == "doi":
                    doi = aid.text or ""
                elif aid.get("IdType") == "pubmed":
                    pmid = aid.text or ""

            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

            if title:
                results.append(
                    {
                        "title": title,
                        "doi": doi,
                        "abstract": abstract,
                        "authors": authors_str,
                        "year": year,
                        "source": "PubMed",
                        "url": url,
                    }
                )
        except Exception:
            continue

    return results
