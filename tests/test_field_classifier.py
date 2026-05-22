import unittest

from utils.field_classifier import FIELDS_26, normalize_name, _lookup


class ClassifierCoreTests(unittest.TestCase):
    def test_fields_count(self):
        self.assertEqual(len(FIELDS_26), 26)
        self.assertIn("Chemistry", FIELDS_26)
        self.assertIn("Social Sciences", FIELDS_26)

    def test_normalize_name(self):
        self.assertEqual(normalize_name("  J. Am. Chem. Soc. "), "j am chem soc")
        self.assertEqual(normalize_name(None), "")

    def test_lookup_by_issn(self):
        by_issn = {"0002-7863": {"f": "Chemistry", "m": 0}}
        self.assertEqual(_lookup(by_issn, {}, "0002-7863", ""), ("Chemistry", "issn"))

    def test_lookup_by_name_fallback(self):
        by_name = {"nature communications": {"f": "Multidisciplinary", "m": 1}}
        self.assertEqual(_lookup({}, by_name, "", "Nature Communications"), ("Multidisciplinary", "name"))

    def test_lookup_megajournal_flag(self):
        by_issn = {"2045-2322": {"f": "Biology", "m": 1}}
        self.assertEqual(_lookup(by_issn, {}, "2045-2322", ""), ("Multidisciplinary", "issn"))

    def test_lookup_unknown(self):
        self.assertEqual(_lookup({}, {}, "", "Some Unindexed Zine"), ("Unknown", "none"))


class BuildEntryTests(unittest.TestCase):
    def _source(self):
        return {
            "id": "https://openalex.org/S123",
            "display_name": "Journal of the American Chemical Society",
            "issn_l": "0002-7863",
            "issn": ["0002-7863", "1520-5126"],
            "alternate_titles": ["JACS"],
            "abbreviated_title": "J. Am. Chem. Soc.",
            "works_count": 100000,
            "topics": [
                {"display_name": "Organic synthesis", "count": 700, "field": {"display_name": "Chemistry"}},
                {"display_name": "Catalysis", "count": 200, "field": {"display_name": "Chemistry"}},
                {"display_name": "Materials", "count": 100, "field": {"display_name": "Materials Science"}},
            ],
        }

    def test_build_entry_dominant_field(self):
        from scripts.build_journal_fields import build_entry
        e = build_entry(self._source(), multi_threshold=0.5)
        self.assertEqual(e["field"], "Chemistry")
        self.assertFalse(e["multi"])
        self.assertIn("0002-7863", e["issns"])
        self.assertIn("1520-5126", e["issns"])
        self.assertIn("journal of the american chemical society", e["names"])
        self.assertIn("jacs", e["names"])
        self.assertIn("j am chem soc", e["names"])

    def test_build_entry_multidisciplinary(self):
        from scripts.build_journal_fields import build_entry
        src = {
            "issn_l": "2045-2322", "issn": ["2045-2322"], "display_name": "Scientific Reports",
            "alternate_titles": [], "abbreviated_title": "",
            "topics": [
                {"field": {"display_name": "Medicine"}, "count": 300},
                {"field": {"display_name": "Biology"}, "count": 280},
                {"field": {"display_name": "Physics and Astronomy"}, "count": 250},
            ],
        }
        e = build_entry(src, multi_threshold=0.5)
        self.assertTrue(e["multi"])  # no field exceeds 50%

    def test_build_entry_no_topics_returns_none(self):
        from scripts.build_journal_fields import build_entry
        self.assertIsNone(build_entry({"issn_l": "x", "topics": []}, multi_threshold=0.5))


if __name__ == "__main__":
    unittest.main()
