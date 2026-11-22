from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carepath_model.ontology import parse_obo, term_aliases  # noqa: E402
from carepath_model.condition_service import ConditionServiceMapper  # noqa: E402
from carepath_model.facility_reranker import (  # noqa: E402
    rerank_condition_candidate,
)
from carepath_model.query import (  # noqa: E402
    AliasEntry,
    MentionExtractor,
    Urgency,
    detect_urgency,
    distance_weight,
)
from carepath_model.ranking import FacilityCandidate, rank_candidates  # noqa: E402
from carepath_model.service_catalog import (  # noqa: E402
    infer_action_service_type,
    infer_service_urgency,
)
from carepath_model.taxonomy import normalize_text, weak_label  # noqa: E402


class TaxonomyTests(unittest.TestCase):
    @staticmethod
    def _condition_mapper() -> ConditionServiceMapper:
        edges = [
            {
                "condition_id": "HP:1",
                "condition_label": "Chest pain",
                "source_kind": "phenotype",
                "action_id": "MAXO:1",
                "action_label": "clinical assessment",
                "relation": "is_observable_through",
            },
            {
                "condition_id": "HP:2",
                "condition_label": "Dyspnea",
                "source_kind": "phenotype",
                "action_id": "MAXO:1",
                "action_label": "clinical assessment",
                "relation": "is_observable_through",
            },
            {
                "condition_id": "HP:3",
                "condition_label": "Stroke",
                "source_kind": "phenotype",
                "action_id": "MAXO:2",
                "action_label": "neurologist evaluation",
                "relation": "is_observable_through",
            },
            {
                "condition_id": "HP:4",
                "condition_label": "Fever",
                "source_kind": "phenotype",
                "action_id": "MAXO:1",
                "action_label": "clinical assessment",
                "relation": "is_observable_through",
            },
            {
                "condition_id": "HP:5",
                "condition_label": "Pneumonia",
                "source_kind": "phenotype",
                "action_id": "MAXO:1",
                "action_label": "clinical assessment",
                "relation": "is_observable_through",
            },
        ]
        tags = [
            {
                "tag_id": "x-ray",
                "label": "X-ray",
                "group_name": "Imaging & diagnostics",
            },
            {
                "tag_id": "asthma-copd",
                "label": "Asthma / COPD",
                "group_name": "Lungs & breathing",
            },
        ]
        return ConditionServiceMapper(edges, [], tags)

    def test_normalizes_british_spelling_and_abbreviations(self) -> None:
        self.assertEqual(
            normalize_text("Haemodialysis & ECG services"),
            "hemodialysis and electrocardiography services",
        )

    def test_classifies_direct_procedure(self) -> None:
        label = weak_label("procedure_arr", "Provides hemodialysis and peritoneal dialysis")
        self.assertEqual(label.category, "therapeutic_procedure")
        self.assertEqual(label.evidence_role, "direct_procedure")

    def test_classifies_emergency_capability(self) -> None:
        label = weak_label("capability_arr", "24x7 emergency and trauma centre")
        self.assertEqual(label.category, "emergency_availability")
        self.assertEqual(label.evidence_role, "direct_capability")

    def test_classifies_diagnostic_equipment_as_service(self) -> None:
        label = weak_label("equipment_arr", "On-site MRI scanner")
        self.assertEqual(label.category, "diagnostic_imaging")
        self.assertEqual(label.evidence_role, "defines_service")

    def test_classifies_plain_dialysis_value_as_renal_device(self) -> None:
        label = weak_label("equipment_arr", "Dialysis")
        self.assertEqual(label.category, "renal_device")
        self.assertEqual(label.evidence_role, "supports_service")

    def test_accessibility_is_not_clinical_evidence(self) -> None:
        label = weak_label("equipment_arr", "Wheelchair accessible entrance")
        self.assertEqual(label.category, "accessibility")
        self.assertEqual(label.evidence_role, "context_only")

    def test_negated_text_is_not_positive_evidence(self) -> None:
        label = weak_label("capability_arr", "No dialysis unit")
        self.assertEqual(label.category, "unclassified")
        self.assertEqual(label.evidence_role, "negative")

    def test_parses_obo_name_synonyms_and_parents(self) -> None:
        terms = parse_obo(
            """
[Term]
id: MAXO:0000900
name: electrocardiography
synonym: "ECG" EXACT []
synonym: "EKG" EXACT []
xref: NCIT:C38053
is_a: MAXO:0000493 ! diagnostic procedure
"""
        )
        self.assertEqual(len(terms), 1)
        self.assertEqual(terms[0].parents, ["MAXO:0000493"])
        self.assertEqual(
            term_aliases(terms[0]),
            ("electrocardiography", "ECG", "EKG"),
        )

    def test_extracts_multiple_mentions_and_prefers_longest_phrase(self) -> None:
        extractor = MentionExtractor(
            [
                AliasEntry("Chest pain", "HP:0100749", "phenotype", "chest pain"),
                AliasEntry("Pain", "HP:0012531", "phenotype", "pain"),
                AliasEntry("Diabetes", "MONDO:0005015", "disease", "diabetes"),
            ]
        )
        mentions = extractor.extract("Chest pain, diabetes and no pain at rest")
        self.assertEqual(
            [(mention.concept_id, mention.matched_label) for mention in mentions],
            [
                ("HP:0100749", "Chest pain"),
                ("MONDO:0005015", "Diabetes"),
            ],
        )

    def test_negated_emergency_is_not_emergency(self) -> None:
        self.assertEqual(detect_urgency("No chest pain, routine review"), Urgency.ROUTINE)
        self.assertEqual(detect_urgency("Crushing chest pain now"), Urgency.EMERGENCY)
        self.assertEqual(
            detect_urgency("No chest pain or fever, stroke symptoms"),
            Urgency.EMERGENCY,
        )
        self.assertEqual(detect_urgency("Emergency C-section"), Urgency.EMERGENCY)
        self.assertEqual(detect_urgency("Urgent C-section"), Urgency.URGENT)

    def test_urgency_increases_distance_weight(self) -> None:
        self.assertGreater(
            distance_weight(Urgency.EMERGENCY),
            distance_weight(Urgency.URGENT),
        )
        self.assertGreater(
            distance_weight(Urgency.URGENT),
            distance_weight(Urgency.ROUTINE),
        )

    def test_detects_chinese_emergency_and_negation(self) -> None:
        self.assertEqual(detect_urgency("突发卒中，意识不清"), Urgency.EMERGENCY)
        self.assertEqual(detect_urgency("没有胸痛，常规复查"), Urgency.ROUTINE)

    def test_condition_pipeline_sets_urgency_before_service_mapping(self) -> None:
        mapping = self._condition_mapper().resolve(
            "severe chest pain and shortness of breath"
        )
        self.assertEqual(mapping.urgency, Urgency.EMERGENCY)
        self.assertEqual(
            {item.condition_label for item in mapping.conditions},
            {"Chest pain", "Dyspnea"},
        )
        self.assertEqual(
            {item.service_label for item in mapping.services},
            {"clinical assessment"},
        )

    def test_condition_pipeline_stops_negation_at_clause_boundary(self) -> None:
        mapping = self._condition_mapper().resolve(
            "no chest pain, fever for three days"
        )
        self.assertEqual(mapping.urgency, Urgency.ROUTINE)
        self.assertEqual(
            [item.condition_label for item in mapping.conditions],
            ["Fever"],
        )
        self.assertIn("chest pain", mapping.negated_mentions)

    def test_condition_pipeline_does_not_map_chinese_symptom_aliases(self) -> None:
        mapping = self._condition_mapper().resolve("胸痛并呼吸困难")
        self.assertEqual(mapping.urgency, Urgency.EMERGENCY)
        self.assertEqual(mapping.conditions, ())

    def test_condition_pipeline_expands_related_treatment_concepts(self) -> None:
        mapping = self._condition_mapper().resolve("pneumonia")
        self.assertIn("chest x ray", mapping.treatment_terms)
        self.assertIn(
            "x-ray",
            {tag.tag_id for tag in mapping.related_tags},
        )

    def test_two_stage_reranker_prefers_specific_direct_evidence(self) -> None:
        direct = rerank_condition_candidate(
            {
                "relevance": 0.80,
                "direct_relevance": 0.80,
                "weak_relevance": 0.0,
                "evidence": [
                    {
                        "route_type": "condition_action",
                        "field": "procedure_arr",
                        "strength": "strong",
                        "quote": "Performs the requested procedure",
                    }
                ],
            },
            distance_score=0.50,
            urgency=Urgency.ROUTINE,
            facility_source_count=2,
            candidate_pool_size=10,
        )
        weak = rerank_condition_candidate(
            {
                "relevance": 0.50,
                "direct_relevance": 0.0,
                "weak_relevance": 0.50,
                "evidence": [
                    {
                        "route_type": "condition_related_tag",
                        "field": "equipment_arr",
                        "strength": "weak",
                        "quote": "Generic equipment",
                    }
                ],
            },
            distance_score=0.50,
            urgency=Urgency.ROUTINE,
            facility_source_count=1,
            candidate_pool_size=10,
        )
        self.assertGreater(direct.evidence_score, weak.evidence_score)
        self.assertGreater(direct.total_score, weak.total_score)
        self.assertAlmostEqual(sum(direct.weights.values()), 1.0)

    def test_two_stage_reranker_raises_distance_weight_for_emergency(self) -> None:
        candidate = {
            "relevance": 0.70,
            "direct_relevance": 0.0,
            "weak_relevance": 0.70,
            "evidence": [
                {
                    "route_type": "condition_text_tag",
                    "field": "capability_arr",
                    "strength": "weak",
                    "quote": "24/7 emergency service",
                }
            ],
        }
        routine = rerank_condition_candidate(
            candidate,
            distance_score=0.80,
            urgency=Urgency.ROUTINE,
            facility_source_count=2,
            candidate_pool_size=20,
        )
        emergency = rerank_condition_candidate(
            candidate,
            distance_score=0.80,
            urgency=Urgency.EMERGENCY,
            facility_source_count=2,
            candidate_pool_size=20,
        )
        self.assertGreater(
            emergency.weights["distance"],
            routine.weights["distance"],
        )

    def test_emergency_increases_distance_effect(self) -> None:
        candidates = [
            FacilityCandidate("near", "Near", 0.80, 5.0, 25.0, True),
            FacilityCandidate("relevant", "Relevant", 1.0, 20.0, 25.0, True),
        ]
        routine = rank_candidates(candidates, Urgency.ROUTINE)
        emergency = rank_candidates(candidates, Urgency.EMERGENCY)
        routine_by_id = {item.unique_id: item.final_score for item in routine}
        emergency_by_id = {item.unique_id: item.final_score for item in emergency}
        self.assertGreater(
            emergency_by_id["near"] - emergency_by_id["relevant"],
            routine_by_id["near"] - routine_by_id["relevant"],
        )

    def test_facility_without_direct_service_is_excluded(self) -> None:
        ranked = rank_candidates(
            [FacilityCandidate("near", "Near", 1.0, 1.0, 25.0, False)],
            Urgency.EMERGENCY,
        )
        self.assertEqual(ranked, [])

    def test_service_catalog_urgency_and_type(self) -> None:
        self.assertEqual(
            infer_service_urgency("Emergency C-section"),
            "emergency",
        )
        self.assertEqual(
            infer_service_urgency("Dialysis"),
            "routine",
        )
        self.assertEqual(
            infer_service_urgency("Caesarean section"),
            "urgent",
        )
        self.assertEqual(
            infer_action_service_type(["diagnostic", "treatment"]),
            "mixed_action_service",
        )


if __name__ == "__main__":
    unittest.main()
