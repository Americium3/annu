"""Unit tests for search_resolver.py on a small synthetic tag set (no Databricks needed).

Run: python3 -m unittest discover -s pipeline/tests
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from search_resolver import SearchResolver  # noqa: E402

ALIASES = [
    # alias, mesh_id, mesh_label, curated_tags, condition_tag, fallback_specialties
    ("piles", "D006484", "Hemorrhoids", "piles-fistula", "mesh:D006484", "specialty:generalSurgery"),
    ("bawaseer", "D006484", "Hemorrhoids", "piles-fistula", "mesh:D006484", "specialty:generalSurgery"),
    ("uveitis", "D014605", "Uveitis", "", "mesh:D014605", "specialty:ophthalmology"),
    ("progeria", "D011371", "Progeria", "", "", "specialty:pediatrics"),
    ("diabetes mellitus", "D003920", "Diabetes Mellitus", "diabetes", "mesh:D003920", "specialty:endocrinology"),
]
FACILITIES = [  # around Bhubaneswar (20.2961, 85.8245)
    {"unique_id": "near-surgery", "name": "Near Surgical", "best_lat": "20.30", "best_lon": "85.83", "comprehensiveness": "0.40"},
    {"unique_id": "far-piles", "name": "Far Piles Clinic", "best_lat": "22.57", "best_lon": "88.36", "comprehensiveness": "0.20"},
    {"unique_id": "eye", "name": "Eye Centre", "best_lat": "20.31", "best_lon": "85.82", "comprehensiveness": "0.30"},
    {"unique_id": "big", "name": "Big Medical College", "best_lat": "20.25", "best_lon": "85.78", "comprehensiveness": "1.10"},
]


def write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


class SearchResolverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        write(d / "alias_table.csv",
              ["alias", "alias_normalized", "source", "mesh_id", "mesh_label", "curated_tags", "condition_tag",
               "fallback_specialties", "facilities_with_condition_evidence"],
              [(a, a, "test", m, l, t, c, s, 0) for a, m, l, t, c, s in ALIASES])
        write(d / "facility_tag_scores.csv",
              ["unique_id", "tag_id", "class", "best_probability", "best_evidence_ref", "regex_sentence_count"],
              [("far-piles", "piles-fistula", "strong", "0.9", "procedure:0", 1),
               ("eye", "diabetes", "suggested", "0.9", "procedure:0", 0)])  # suggested must not count
        write(d / "facility_tags.csv", ["unique_id", "tag_id", "tag_type", "evidence_refs"],
              [("near-surgery", "specialty:generalSurgery", "specialty", ""),
               ("eye", "specialty:ophthalmology", "specialty", "")])
        write(d / "facility_condition_tags.csv", ["unique_id", "tag_id", "evidence_refs"],
              [("eye", "mesh:D014605", "capability:1")])
        cls.r = SearchResolver(tags_dir=d, facilities=FACILITIES)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_resolution_modes(self):
        self.assertEqual(self.r.resolve("Bawaseer").match_type, "exact")
        self.assertEqual(self.r.resolve("piles treatment near me").match_type, "filler_removed")
        self.assertEqual(self.r.resolve("laser for piles and fissure").match_type, "contained")
        self.assertEqual(self.r.resolve("diabetes melitus").match_type, "spelling")
        self.assertEqual(self.r.resolve("xyzzy").match_type, "none")

    def test_far_evidence_beats_nearby_specialty(self):
        # The only facility with evidence for piles is ~360 km away (Kolkata); a general surgeon is next door.
        # Evidence wins (flagged far), and the most comprehensive hospital nearby is offered too.
        out = self.r.search("piles", 20.2961, 85.8245)
        self.assertTrue(out["exists_anywhere"])
        self.assertEqual(out["match_level"], "service_evidence")
        self.assertTrue(out["far"])
        self.assertEqual(out["results"][0]["unique_id"], "far-piles")
        self.assertEqual(out["fallback"]["results"][0]["unique_id"], "big")

    def test_specialty_only_when_no_evidence_anywhere(self):
        out = self.r.search("progeria", 20.2961, 85.8245)
        self.assertFalse(out["exists_anywhere"])
        self.assertIsNone(out["match_level"])  # no pediatrics facility in the fixture -> comprehensive fallback
        self.assertEqual(out["fallback"]["results"][0]["unique_id"], "big")

    def test_condition_mention_tier(self):
        out = self.r.search("uveitis", 20.2961, 85.8245)
        self.assertEqual(out["match_level"], "condition_mention")
        self.assertEqual(out["results"][0]["unique_id"], "eye")

    def test_suggested_grade_is_not_evidence(self):
        out = self.r.search("diabetes mellitus")
        self.assertEqual(out["facilities_anywhere"]["service_evidence"], 0)
        self.assertFalse(out["exists_anywhere"])

    def test_no_evidence_anywhere_reports_false(self):
        out = self.r.search("progeria")
        self.assertFalse(out["exists_anywhere"])

    def test_fallback_to_most_comprehensive_hospital(self):
        out = self.r.search("xyzzy", 20.2961, 85.8245)
        self.assertIsNone(out["match_level"])
        self.assertEqual(out["fallback"]["reason"], "search text not recognised")
        self.assertEqual(out["fallback"]["results"][0]["unique_id"], "big")


if __name__ == "__main__":
    unittest.main()
