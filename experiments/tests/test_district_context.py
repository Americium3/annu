import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import pandas as pd

from experiments.district_context import DistrictContext, parse_value
from experiments.engine import ExperimentEngine
from experiments.io import load_context_table, resolve_location
from experiments.run import run_experiments
from test_experiments import fixture

INSURANCE = "hh_member_covered_health_insurance_pct"
BIRTH = "institutional_birth_5y_pct"


def nfhs_fixture():
    return pd.DataFrame([
        {"district_name": " Jaipur ", "state_ut": "Rajasthan", INSURANCE: "20", BIRTH: "(45.0)", "households_surveyed": "900"},
        {"district_name": "Bangalore", "state_ut": "Karnataka", INSURANCE: "50", BIRTH: "*", "households_surveyed": "1200"},
        {"district_name": "Patna", "state_ut": "Bihar", INSURANCE: "80", BIRTH: "90", "households_surveyed": "800"},
    ])


def aliases_fixture():
    return pd.DataFrame([{"source_state": "Karnataka", "source_district": "Bengaluru Urban",
                          "target_state": "Karnataka", "target_district": "Bangalore", "mapping_type": "name_alias"}])


class DistrictContextTest(unittest.TestCase):
    def test_marker_aware_parsing_and_domain_checks(self):
        self.assertEqual(parse_value("(42.5)", percentage=True), {"raw": "(42.5)", "value": 42.5, "status": "low_sample"})
        for raw, status in (("*", "suppressed"), (None, "missing"), ("null", "missing"), ("oops", "invalid"),
                            ("101", "out_of_range"), ("-1", "out_of_range")):
            result = parse_value(raw, percentage=True)
            self.assertEqual(result["status"], status)
            self.assertIsNone(result["value"])
        self.assertEqual(parse_value("0", percentage=True)["value"], 0)
        self.assertEqual(parse_value("1.5", sample_count=True)["status"], "out_of_range")

    def test_exact_trim_and_reviewed_alias_without_fuzzy_join(self):
        ctx = DistrictContext(nfhs_fixture(), aliases_fixture())
        self.assertEqual(ctx.lookup(" rajasthan ", "JAIPUR")["match_status"], "exact")
        self.assertEqual(ctx.lookup("Karnataka", "Bengaluru Urban")["district"], "Bangalore")
        self.assertEqual(ctx.lookup("Karnataka", "Bangalor")["match_status"], "unmatched")
        self.assertEqual(ctx.lookup(None, "Jaipur")["match_status"], "missing_key")

    def test_duplicate_or_ambiguous_keys_fail_before_join(self):
        with self.assertRaisesRegex(ValueError, "Duplicate normalized"):
            DistrictContext(pd.concat([nfhs_fixture(), nfhs_fixture().iloc[:1]]))
        with self.assertRaisesRegex(ValueError, "unique"):
            DistrictContext(nfhs_fixture(), pd.concat([aliases_fixture(), aliases_fixture()]))

    def test_boundary_change_overrides_even_exact_name_match(self):
        aliases = aliases_fixture()
        aliases.loc[0, ["source_state", "source_district", "mapping_type"]] = ["Rajasthan", "Jaipur", "boundary_change"]
        ctx = DistrictContext(nfhs_fixture(), aliases)
        self.assertEqual(ctx.lookup("Rajasthan", "Jaipur")["match_status"], "boundary_review")
        self.assertNotIn("indicators", ctx.lookup("Rajasthan", "Jaipur"))

    def test_missing_target_alias_is_audited(self):
        aliases = aliases_fixture()
        aliases.loc[0, "target_district"] = "not in NFHS"
        self.assertEqual(DistrictContext(nfhs_fixture(), aliases).lookup("Karnataka", "Bengaluru Urban")["match_status"], "unmatched_alias")

    def test_empty_table_and_bad_bins_fail_visibly(self):
        with self.assertRaises(ValueError):
            DistrictContext(nfhs_fixture().iloc[:0])
        for bins in ([60, 30], [float("nan"), 60], "30"):
            with self.assertRaises(ValueError):
                DistrictContext(nfhs_fixture(), group_bins={INSURANCE: bins})
        with self.assertRaises(ValueError):
            DistrictContext(nfhs_fixture(), group_indicators=["unknown_pct"])

    def test_groups_preserve_small_sample_and_suppression(self):
        ctx = DistrictContext(nfhs_fixture(), group_bins={INSURANCE: [30, 60], BIRTH: [50, 80]})
        a = ctx.query_context({"context_state": "Rajasthan", "context_district": "Jaipur"}, "nicu")
        self.assertEqual(a["groups"][INSURANCE], "lower")
        self.assertEqual(a["groups"][BIRTH], "low_sample")
        self.assertEqual(ctx.query_context({"context_state": "Karnataka", "context_district": "Bangalore"}, "nicu")["groups"][BIRTH], "suppressed")
        self.assertEqual(ctx.query_context({}, "nicu")["groups"][BIRTH], "unmatched_context")
        self.assertEqual(a["sample_metadata"]["households_surveyed"]["value"], 900)
        self.assertFalse(ctx.manifest()["household_counts_used_as_weights"])

    def test_service_display_does_not_invent_mri_or_burn_indicators(self):
        nfhs = nfhs_fixture()
        nfhs["sex_ratio_at_birth_5y_f_per_1000_m"] = "1025"
        ctx = DistrictContext(nfhs)
        q = {"context_state": "Rajasthan", "context_district": "Jaipur"}
        self.assertEqual({m["indicator"] for m in ctx.query_context(q, "mri")["display_indicators"]}, {INSURANCE})
        self.assertEqual({m["indicator"] for m in ctx.query_context(q, "nicu")["display_indicators"]}, {INSURANCE, BIRTH})
        ratio = ctx.lookup("Rajasthan", "Jaipur")["indicators"]["sex_ratio_at_birth_5y_f_per_1000_m"]
        self.assertEqual(ratio["value"], 1025)
        self.assertEqual(ratio["unit"], "ratio")

    def test_read_only_identifier_checked_table_adapter(self):
        spark = Mock()
        spark.sql.return_value.toPandas.return_value = nfhs_fixture()
        load_context_table("catalog.schema.nfhs", spark)
        spark.sql.assert_called_once_with("SELECT * FROM `catalog`.`schema`.`nfhs`")
        with self.assertRaises(ValueError):
            load_context_table("catalog.schema.nfhs; DROP TABLE x", spark)

    def test_context_assignment_is_explicit_or_audited_pin_not_nearest_hospital(self):
        fac, _ = fixture()
        coord = resolve_location("26.9,75.8", fac)
        self.assertNotIn("context_district", coord)
        pins = pd.DataFrame([{"pincode": "302001", "states": '["Rajasthan"]', "districts": '["Jaipur"]', "lat": 26.9, "lon": 75.8}])
        self.assertEqual(resolve_location("302001", fac, pins)["context_district"], "Jaipur")

    def test_rank_invariance_outputs_counts_and_unlabelled_metrics(self):
        fac, ev = fixture()
        # All six records belong to one district, but only one is eligible for this service.
        fac["state"], fac["district"] = "Rajasthan", "Jaipur"
        engine = ExperimentEngine(fac, ev)
        queries = pd.DataFrame([{"query_id": "q", "service": "dialysis", "latitude": 26.9, "longitude": 75.8,
                                 "context_state": "Rajasthan", "context_district": "Jaipur", "density_group": "fixture"}])
        with tempfile.TemporaryDirectory() as out:
            root = Path(out)
            baseline, _, _ = run_experiments(engine, queries, ["rules", "bm25"], root / "baseline")
            runs, metrics, _ = run_experiments(engine, queries, ["rules", "bm25"], root / "nfhs", district_context=DistrictContext(nfhs_fixture()))
            for before, after in zip(baseline, runs):
                self.assertEqual(before["results"], after["results"])
                self.assertEqual(before["candidate_ids"], after["candidate_ids"])
                self.assertEqual(before["audit"], after["audit"])
            for file in ("district_context.csv", "district_join_audit.csv", "query_district_join_audit.csv",
                         "metrics_by_district_context.csv", "district_service_coverage.csv", "district_context.geojson",
                         "district_context_manifest.json", "plots/nfhs_groups_00.png"):
                self.assertTrue((root / "nfhs" / file).exists(), file)
            coverage = pd.read_csv(root / "nfhs/district_service_coverage.csv")
            jaipur = coverage[coverage.district_key.eq("jaipur")].iloc[0]
            self.assertEqual(jaipur.dataset_facility_count, 6)
            self.assertEqual(jaipur.service_text_supported_count, 3)
            self.assertEqual(jaipur.service_location_usable_count, 1)
            groups = pd.read_csv(root / "nfhs/metrics_by_district_context.csv")
            self.assertTrue(groups.precision_at_k.isna().all())
            self.assertTrue(groups.precision_at_k_n.eq(0).all())
            self.assertTrue(groups.query_count.eq(1).all())
            self.assertTrue(metrics.nearby_dataset_facility_count.eq(6).all())
            geo = json.loads((root / "nfhs/district_context.geojson").read_text())
            self.assertEqual(len(geo["features"]), 1)
            self.assertEqual(geo["features"][0]["geometry"]["type"], "Point")
            self.assertIn('id="nfhs"', (root / "nfhs/map.html").read_text())

    def test_no_result_is_not_zero_distance_and_known_positive_counts(self):
        fac, ev = fixture()
        query = pd.DataFrame([{"query_id": "q", "service": "mri", "latitude": 26.9, "longitude": 75.8,
                               "context_state": "Rajasthan", "context_district": "Jaipur"}])
        qrels = pd.DataFrame([{"query_id": "q", "unique_id": "a", "relevance": 3}])
        with tempfile.TemporaryDirectory() as out:
            _, metrics, _ = run_experiments(ExperimentEngine(fac, ev), query, ["rules"], out,
                                             qrels=qrels, district_context=DistrictContext(nfhs_fixture()))
            self.assertEqual(metrics.no_answer.iloc[0], 1)
            self.assertTrue(pd.isna(metrics.top1_distance_km.iloc[0]))
            groups = pd.read_csv(Path(out) / "metrics_by_district_context.csv")
            self.assertTrue(groups.false_abstention.eq(1).all())
            self.assertTrue(groups.precision_at_k.eq(0).all())
            self.assertTrue(groups.precision_at_k_n.eq(1).all())


if __name__ == "__main__":
    unittest.main()
