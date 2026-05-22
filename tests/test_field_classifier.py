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


if __name__ == "__main__":
    unittest.main()
