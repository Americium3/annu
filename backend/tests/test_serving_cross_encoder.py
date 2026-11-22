"""Serving-path tests with deterministic logits; no model download or Databricks."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from cross_encoder import CrossEncoderScorer, CrossEncoderError
from data_store import Snapshot
from recommender import Recommender


class FakeModel:
    def __init__(self):
        self.calls = []

    def predict(self, pairs, **kwargs):
        self.calls.append(list(pairs))
        return np.array([4. if "specialized" in text else -4. for _, text in pairs])


def snapshot():
    facilities, index = [], []
    for uid, lat, status, tier, text in (
        ("near", 26.91, "formal", 1, "We provide dialysis."),
        ("far", 26.96, "formal", 3, "Our specialized dialysis treatment unit offers haemodialysis."),
        ("blocked", 26.90, "review_blocked", 1, "Our specialized dialysis treatment is provided."),
        ("outside", 27.5, "formal", 1, "Our specialized dialysis unit is open."),
    ):
        facilities.append({
            "unique_id": uid, "name": uid.title(), "loc_lat": lat, "loc_lon": 75.8,
            "latitude": lat, "longitude": 75.8, "location_tier": "point_verified", "location_check": "fixture",
            "city_raw": "Jaipur", "address_city": "Jaipur", "district": "Jaipur", "state": "Rajasthan",
            "pincode": "302001", "facility_category": "hospital", "operator_category": "private",
            "contact_phone": "1234567890", "contact_website": "https://example.org", "source_urls": [],
            "n_source_urls": 0, "n_beds": 10, "n_doctors": 2, "year_est": 2000,
            "n_explicit_elsewhere": 0, "same_name_city_records": 1, "capability_maybe_truncated": False,
            "procedure_maybe_truncated": False, "recency_of_page_update": "",
        })
        index.append({"unique_id": uid, "tag_id": "kidney-dialysis", "eligibility": status, "evidence_tier": tier,
                      "n_explicit_usable": 1, "n_explicit_elsewhere": 0, "only_equipment": False,
                      "lists_emergency_24x7": False, "evidence": [
                          {"text": text, "field": "procedure", "pos": 0, "evidence_status": "usable"},
                          {"text": "unusable specialized dialysis text", "field": "procedure", "pos": 1,
                           "evidence_status": "elsewhere"}]})
    tags = pd.DataFrame([{"tag_id": "kidney-dialysis", "label": "Dialysis", "group_name": "Renal",
                          "synonyms": ["haemodialysis"], "facility_count": 4}])
    pins = pd.DataFrame([{"pincode": "302001", "lat": 26.9, "lon": 75.8, "is_precise": True,
                          "states": ["Rajasthan"], "districts": ["Jaipur"]}])
    return Snapshot(tags, pd.DataFrame(index), pd.DataFrame(facilities), pins, "fixture", "fixture")


class ServingCrossEncoderTest(unittest.TestCase):
    def setUp(self):
        self.model = FakeModel()
        self.scorer = CrossEncoderScorer(model=self.model)
        self.rec = Recommender(snapshot(), scorer=self.scorer)

    def test_actual_serving_default_reorders_using_cross_encoder(self):
        self.assertEqual(config.RANKING_METHOD, "cross_encoder")
        r = self.rec.recommend("dialysis", "26.9,75.8")
        self.assertEqual([f["id"] for f in r["results"]], ["far", "near"])
        self.assertEqual(r["metadata"]["ranking"]["method"], "cross_encoder")
        # Pool starts at twice the travel distance for dialysis (15 km), i.e. the 50 km step.
        self.assertEqual(r["queryContext"]["searchParameters"]["radiusKm"], 50)
        passages = [text for call in self.model.calls for _, text in call]
        self.assertEqual(len(passages), 2)  # blocked, outside and unusable text never scored
        self.assertNotIn("unusable specialized dialysis text", passages)
        scores = [f["reranking"]["totalScore"] for f in r["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        json.dumps(r, allow_nan=False)

    def test_score_breakdown_matches_rank_and_traces_best_evidence(self):
        r = self.rec.recommend("dialysis", "26.9,75.8")["results"][0]
        sb, detail = r["scoreBreakdown"], r["reranking"]
        self.assertEqual(detail["bestEvidenceRef"], "procedure:0")
        self.assertIn(detail["bestEvidenceText"], [e["quote"] for e in r["evidence"]])
        self.assertAlmostEqual(sum(sb[k] for k in sb if k.endswith("Score") and k != "totalScore"), 100 * detail["totalScore"])
        self.assertEqual(r["totalScore"], round(100 * detail["totalScore"]))
        self.assertEqual(detail["evidenceScore"], .55)  # proof strength of a tier-3 statement at a verified point

    def test_repeat_location_query_reuses_service_text_pair_scores(self):
        self.rec.recommend("dialysis", "26.9,75.8")
        self.rec.recommend("haemodialysis", "26.901,75.8")
        self.assertEqual(len(self.model.calls), 1)

    def test_explicit_rules_comparison_does_not_load_model(self):
        rec = Recommender(snapshot(), scorer=self.scorer, ranking_method="rules")
        rec.warmup()
        r = rec.recommend("dialysis", "26.9,75.8")
        self.assertEqual([f["id"] for f in r["results"]], ["near", "far"])
        self.assertNotIn("reranking", r["results"][0])
        self.assertEqual(self.model.calls, [])

    def test_empty_radius_returns_no_results_without_inference(self):
        r = self.rec.recommend("dialysis", "0,75.8")
        self.assertEqual(r["results"], [])
        self.assertEqual(self.model.calls, [])

    def test_model_failure_is_503_not_rules_fallback(self):
        import main
        with patch.object(self.model, "predict", side_effect=RuntimeError("model failed")):
            with patch.dict(main.STATE, {"rec": self.rec}):
                with self.assertRaises(main.HTTPException) as error:
                    main.recommendations(main.RecommendationRequest(serviceText="dialysis", locationText="26.9,75.8"))
        self.assertEqual(error.exception.status_code, 503)

    def test_http_startup_warms_default_and_health_reports_it(self):
        import main
        from fastapi.testclient import TestClient
        with patch.object(main, "get_snapshot", return_value=snapshot()), patch.object(main, "Recommender", return_value=self.rec):
            with TestClient(main.app) as client:
                health = client.get("/api/health").json()
                self.assertEqual(health["ranking"]["method"], "cross_encoder")
                self.assertTrue(health["ranking"]["scorer"]["loaded"])
                response = client.post("/api/recommendations", json={"serviceText": "dialysis", "locationText": "26.9,75.8"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["results"][0]["id"], "far")
                self.assertEqual(client.post("/api/recommendations", json={"serviceText": "dialysis", "mode": "rules"}).status_code, 422)

    def test_startup_model_failure_does_not_report_ready(self):
        import main
        from fastapi.testclient import TestClient
        with patch.object(main, "get_snapshot", return_value=snapshot()), patch.object(main, "Recommender", return_value=self.rec):
            with patch.object(self.model, "predict", side_effect=RuntimeError("unavailable")):
                with self.assertRaises(CrossEncoderError):
                    with TestClient(main.app):
                        self.fail("Startup must not succeed without the default model")

    def test_formal_row_without_usable_evidence_fails_visibly(self):
        self.rec.by_tag["kidney-dialysis"].at[0, "evidence"] = []
        with self.assertRaises(CrossEncoderError):
            self.rec.recommend("dialysis", "26.9,75.8")

    def test_ties_have_stable_id_order(self):
        snap = snapshot()
        snap.facilities["loc_lat"], snap.facilities["latitude"] = 26.91, 26.91
        for i in snap.index.index:
            snap.index.at[i, "evidence_tier"] = 1  # equal proof too, so only the id can break the tie
            snap.index.at[i, "evidence"] = [{"text": "We provide dialysis.", "field": "procedure", "pos": 0, "evidence_status": "usable"}]
        r = Recommender(snap, scorer=self.scorer).recommend("dialysis", "26.9,75.8")
        self.assertEqual([f["id"] for f in r["results"]], ["far", "near", "outside"])


class ScorerTest(unittest.TestCase):
    def test_sigmoid_once_empty_dedup_and_cache_eviction(self):
        class Model:
            def predict(self, pairs, **kwargs):
                return np.array([0. if text == "zero" else 1000. if text == "positive" else -1000. for _, text in pairs])
        scorer = CrossEncoderScorer(model=Model(), cache_size=1)
        self.assertEqual(scorer.score("q", []), [])
        self.assertEqual(scorer.score("q", ["zero", "positive", "negative", "zero"]), [.5, 1., 0., .5])
        self.assertEqual(scorer.info()["cachedPairs"], 1)

    def test_bad_logits_do_not_become_scores(self):
        for output in (np.array([float("nan")]), np.array([[1., 2.]])):
            class Model:
                def predict(self, pairs, **kwargs):
                    return output
            with self.assertRaises(CrossEncoderError):
                CrossEncoderScorer(model=Model()).score("q", ["passage"])

    def test_load_failure_is_not_swallowed_and_warmup_invokes_inference(self):
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            with self.assertRaises(CrossEncoderError):
                CrossEncoderScorer().warmup()
        model = FakeModel()
        CrossEncoderScorer(model=model).warmup()
        self.assertEqual(len(model.calls), 1)


if __name__ == "__main__":
    unittest.main()
