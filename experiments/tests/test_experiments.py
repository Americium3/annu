import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.engine import ExperimentEngine, Settings, canonical_service, geojson
from experiments.evaluation import annotation_pool, evaluate
from experiments.io import augment_facility_text, resolve_location, table_name
from experiments.run import run_experiments


def fixture():
    facilities = pd.DataFrame([
        {"unique_id": "a", "name": "Alpha", "best_lat": 26.91, "best_lon": 75.78, "state": "Rajasthan", "district": "Jaipur", "location_tier": "point_verified"},
        {"unique_id": "b", "name": "Beta", "best_lat": 26.92, "best_lon": 75.79},
        {"unique_id": "c", "name": "Gamma", "best_lat": 26.93, "best_lon": 75.80},
        {"unique_id": "d", "name": "Delta", "best_lat": 26.94, "best_lon": 75.81},
        {"unique_id": "e", "name": "Epsilon", "best_lat": 26.95, "best_lon": 75.82, "core_identity_conflict": True},
        {"unique_id": "f", "name": "Zeta", "best_lat": 26.96, "best_lon": 75.83, "flag_coord_pin_conflict": True, "location_tier": "pin_area"},
    ])
    evidence = pd.DataFrame([
        {"unique_id": "a", "field": "procedure", "item_idx": 0, "text": "We provide dialysis treatment at this hospital."},
        {"unique_id": "b", "field": "specialty", "item_idx": 0, "text": "nephrology"},
        {"unique_id": "c", "field": "procedure", "item_idx": 0, "text": "Dialysis is not available at this hospital."},
        {"unique_id": "d", "field": "capability", "item_idx": 0, "text": "A future dialysis unit is planned."},
        {"unique_id": "e", "field": "procedure", "item_idx": 0, "text": "Dialysis treatment provided."},
        {"unique_id": "f", "field": "procedure", "item_idx": 0, "text": "Dialysis treatment provided."},
        {"unique_id": "a", "field": "procedure", "item_idx": 1, "text": "We offer caesarean section."},
        {"unique_id": "b", "field": "procedure", "item_idx": 1, "text": "Emergency caesarean section is provided."},
    ])
    return facilities, evidence


class ExperimentsTest(unittest.TestCase):
    def setUp(self):
        self.fac, self.ev = fixture()
        self.engine = ExperimentEngine(self.fac, self.ev)

    def test_high_recall_retains_related_negated_and_planned(self):
        candidates = self.engine.candidates("dialysis")
        self.assertEqual(set(candidates.unique_id), set("abcdef"))
        statuses = candidates.set_index("unique_id").status.to_dict()
        self.assertEqual(statuses["b"], "related")
        self.assertEqual(statuses["c"], "negative")
        self.assertEqual(statuses["d"], "planned_or_historical")

    def test_all_lexical_methods_same_candidates_and_eligibility(self):
        for method in ("rules", "tfidf", "bm25"):
            r = self.engine.recommend("dialysis", 26.9, 75.8, method)
            self.assertEqual(r["candidate_ids"], list("abcdef"))
            self.assertEqual([x["unique_id"] for x in r["results"]], ["a"])
            self.assertTrue(all(np.isfinite(x["score"]) for x in r["audit"]))
            self.assertEqual(geojson(r)["features"][0]["geometry"]["coordinates"], [75.78, 26.91])

    def test_emergency_is_not_ordinary_c_section(self):
        self.assertNotEqual(canonical_service("emergency c section"), canonical_service("c-section"))
        result = self.engine.recommend("emergency c section", 26.9, 75.8)
        self.assertEqual([x["unique_id"] for x in result["results"]], ["b"])

    def test_conflicting_service_statements_block(self):
        ev = pd.concat([self.ev, pd.DataFrame([{"unique_id": "a", "field": "procedure", "item_idx": 2,
                                              "text": "Dialysis has been discontinued."}])], ignore_index=True)
        r = ExperimentEngine(self.fac, ev).recommend("dialysis", 26.9, 75.8)
        self.assertEqual(r["results"], [])

    def test_upstream_attribution_review_not_overridden(self):
        self.ev["evidence_status"] = "usable"
        self.ev.loc[self.ev.unique_id.eq("a"), "evidence_status"] = "elsewhere"
        r = ExperimentEngine(self.fac, self.ev).recommend("dialysis", 26.9, 75.8)
        self.assertEqual(r["results"], [])

    def test_respect_resolved_does_not_resolve_conflict_itself(self):
        r = ExperimentEngine(self.fac, self.ev, Settings(location_policy="respect_resolved")).recommend("dialysis", 26.9, 75.8)
        self.assertEqual({x["unique_id"] for x in r["results"]}, {"a", "f"})

    def test_no_mixed_coordinate_sources(self):
        self.fac.loc[self.fac.unique_id.eq("a"), "loc_lat"] = 10.
        r = ExperimentEngine(self.fac, self.ev).recommend("dialysis", 26.9, 75.8)
        self.assertEqual(r["results"][0]["latitude"], 26.91)

    def test_description_and_specialty_augmentation(self):
        self.fac["description"] = "Hospital provides MRI imaging."
        self.fac["specialties_std"] = '["radiology"]'
        ev = augment_facility_text(self.fac, self.ev)
        self.assertEqual(sum(ev.field.eq("description")), 6)
        self.assertEqual(sum(ev.field.eq("specialty")), 6)

    def test_bad_parameters_and_duplicate_ids(self):
        with self.assertRaises(ValueError):
            Settings(text_weight=2)
        with self.assertRaises(ValueError):
            ExperimentEngine(pd.concat([self.fac, self.fac.iloc[:1]]), self.ev)
        with self.assertRaises(ValueError):
            self.engine.recommend("dialysis", 100, 75)
        with self.assertRaises(ValueError):
            table_name("schema;DROP TABLE x")

    def test_empty_service_no_crash(self):
        self.assertEqual(self.engine.recommend("mri", 26.9, 75.8)["results"], [])

    def test_qrels_unknown_not_counted_as_false(self):
        run = self.engine.recommend("dialysis", 26.9, 75.8)
        run["query_id"] = "q"
        p, _ = evaluate([run], pd.DataFrame(columns=["query_id", "unique_id", "relevance"]))
        self.assertTrue(pd.isna(p.precision_at_k.iloc[0]))
        qrels = pd.DataFrame([{"query_id": "q", "unique_id": "a", "relevance": 3}])
        p, _ = evaluate([run], qrels)
        self.assertAlmostEqual(p.precision_at_k.iloc[0], 1/3)
        self.assertEqual(p.precision_returned.iloc[0], 1)
        self.assertEqual(p.ndcg_at_k_pool.iloc[0], 1)
        self.assertEqual(p.candidate_recall_pool.iloc[0], 1)

    def test_false_abstention_uses_known_positives(self):
        run = self.engine.recommend("mri", 26.9, 75.8)
        run["query_id"] = "q"
        p, _ = evaluate([run], pd.DataFrame([{"query_id": "q", "unique_id": "a", "relevance": 3}]))
        self.assertEqual(p.false_abstention.iloc[0], 1)
        self.assertEqual(p.candidate_recall_pool.iloc[0], 0)

    def test_unjudged_outputs_and_duplicate_qrels(self):
        run = self.engine.recommend("dialysis", 26.9, 75.8)
        run["query_id"] = "q"
        qrels = pd.DataFrame([{"query_id": "q", "unique_id": "b", "relevance": 1}])
        p, _ = evaluate([run], qrels)
        self.assertTrue(pd.isna(p.precision_at_k.iloc[0]))
        with self.assertRaises(ValueError):
            evaluate([run], pd.concat([qrels, qrels]))

    def test_neural_scoring_contract_with_fake_encoder(self):
        class Fake:
            def encode(self, texts, **kwargs):
                return np.tile([1., 0.], (len(texts), 1))
        self.engine._models["bi_encoder"] = Fake()
        run = self.engine.recommend("dialysis", 26.9, 75.8, "bi_encoder")
        self.assertEqual(run["results"][0]["text_score"], 1.)

    def test_resolve_exact_city_pin_and_ambiguous(self):
        loc = resolve_location("Jaipur, Rajasthan", self.fac)
        self.assertEqual(loc["precision"], "district_area")
        pins = pd.DataFrame([{"pincode": "302001", "states": '["rajasthan"]', "districts": '["jaipur"]', "lat": 26.9, "lon": 75.8}])
        self.assertEqual(resolve_location("302001", self.fac, pins)["precision"], "pin_area")
        pins.loc[0, "states"] = '["rajasthan", "other"]'
        with self.assertRaises(ValueError):
            resolve_location("302001", self.fac, pins)

    def test_end_to_end_writes_outputs_and_blinded_pool(self):
        with tempfile.TemporaryDirectory() as out:
            queries = pd.DataFrame([{"query_id": "q", "service": "dialysis", "latitude": 26.9, "longitude": 75.8}])
            runs, _, _ = run_experiments(self.engine, queries, ["rules", "bm25"], out)
            for file in ("map.html", "runs.json", "manifest.json", "annotation_pool.csv", "service_candidates.csv", "plots/method_comparison.png"):
                self.assertTrue((Path(out)/file).exists(), file)
            json.loads((Path(out)/"runs.json").read_text())
            self.assertNotIn("score", annotation_pool(runs).columns)
            with self.assertRaises(ValueError):
                run_experiments(self.engine, queries, ["rules"], out)


if __name__ == "__main__":
    unittest.main()
