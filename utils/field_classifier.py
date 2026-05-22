"""Offline academic-field classifier.

Maps a paper's (ISSN, journal name) to one of the 26 OpenAlex fields, or to
"Multidisciplinary" (megajournals) / "Unknown" (no match). Pure and deterministic;
backed by a shipped lookup table (data/journal_fields.json.gz). No network, no API key."""

from __future__ import annotations

import gzip
import json
import re
import threading
from pathlib import Path

# Canonical OpenAlex field list (aligned with Scopus ASJC), 26 entries.
FIELDS_26 = [
    "Agricultural and Biological Sciences",
    "Arts and Humanities",
    "Biochemistry, Genetics and Molecular Biology",
    "Business, Management and Accounting",
    "Chemical Engineering",
    "Chemistry",
    "Computer Science",
    "Decision Sciences",
    "Dentistry",
    "Earth and Planetary Sciences",
    "Economics, Econometrics and Finance",
    "Energy",
    "Engineering",
    "Environmental Science",
    "Health Professions",
    "Immunology and Microbiology",
    "Materials Science",
    "Mathematics",
    "Medicine",
    "Neuroscience",
    "Nursing",
    "Pharmacology, Toxicology and Pharmaceutics",
    "Physics and Astronomy",
    "Psychology",
    "Social Sciences",
    "Veterinary",
]

MULTIDISCIPLINARY = "Multidisciplinary"
UNKNOWN = "Unknown"


def normalize_name(s) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_issn(s) -> str:
    return (s or "").strip().upper()


def _entry_label(entry: dict) -> str:
    return MULTIDISCIPLINARY if entry.get("m") else entry.get("f") or UNKNOWN


def _lookup(by_issn: dict, by_name: dict, issn: str, venue: str):
    """Pure lookup against provided tables. Returns (field_label, field_source)."""
    key = normalize_issn(issn)
    if key and key in by_issn:
        return (_entry_label(by_issn[key]), "issn")
    nm = normalize_name(venue)
    if nm and nm in by_name:
        return (_entry_label(by_name[nm]), "name")
    return (UNKNOWN, "none")


_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "journal_fields.json.gz"
_lock = threading.Lock()
_by_issn = None
_by_name = None


def _ensure_loaded():
    global _by_issn, _by_name
    if _by_issn is not None:
        return
    with _lock:
        if _by_issn is not None:
            return
        try:
            with gzip.open(_DATA_PATH, "rt", encoding="utf-8") as f:
                data = json.load(f)
            _by_issn = data.get("by_issn", {})
            _by_name = data.get("by_name", {})
        except Exception:
            # Missing/corrupt table -> classify everything as Unknown; app still works.
            _by_issn, _by_name = {}, {}


def classify(issn: str, venue: str):
    """Public entry point: (field_label, field_source) using the shipped table."""
    _ensure_loaded()
    return _lookup(_by_issn, _by_name, issn, venue)
