"""The cleaned tables are still changing; parsing must survive partial and evolving schemas."""
from __future__ import annotations

import csv
from datetime import date

import pytest

from app.ranking import check_schema, facility_from_row
from app.ranking.loaders import (
    load_evidence_index, load_facilities_file, load_facilities_sql, load_specialty_normalizer,
    load_tag_catalog,
)


def test_minimal_row_with_only_required_columns():
    f = facility_from_row({"unique_id": "u1", "best_lat": "20.1", "best_lon": "85.2"})
    assert f.has_coordinates and f.n_beds is None and f.flags == frozenset()


def test_messy_values_are_parsed_or_nulled():
    f = facility_from_row({
        "unique_id": "u1", "best_lat": "20.1", "best_lon": "85.2",
        "n_beds": "120.0", "n_doctors": "", "n_source_urls": "null",
        "specialties_std": '["nephrology", "ENT"]', "location_confidence": "HIGH",
        "page_last_updated": "2026-03-04T00:00:00", "last_social_post": "not a date",
        "flag_coord_pin_conflict": "true", "flag_implausible_scale": "false",
        "flag_added_next_month": True, "some_new_column": 42,
    }, normalize_specialty=lambda s: {"ENT": "otolaryngology"}.get(s, s))
    assert f.n_beds == 120 and f.n_doctors is None and f.n_source_urls is None
    assert f.specialties == frozenset({"nephrology", "otolaryngology"})
    assert f.n_specialties == 2
    assert f.location_confidence == "high"
    assert f.page_last_updated == date(2026, 3, 4) and f.last_social_post is None
    assert f.flags == frozenset({"coord_pin_conflict", "added_next_month"})


def test_out_of_range_coordinates_are_dropped():
    assert not facility_from_row({"unique_id": "u", "best_lat": "200", "best_lon": "85"}).has_coordinates


def test_schema_report():
    r = check_schema(["unique_id", "best_lat", "best_lon", "n_beds"])
    assert r.ok and "n_doctors" in r.missing_optional
    assert check_schema(["unique_id"]).missing_required == ("best_lat", "best_lon")


def _write_csv(path, header, rows, delimiter=","):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(header)
        w.writerows(rows)


def test_evidence_index_joins_scores_and_refs(tmp_path):
    scores, refs = tmp_path / "scores.csv", tmp_path / "refs.csv"
    _write_csv(scores, ["unique_id", "tag_id", "class", "best_probability", "best_evidence_ref", "regex_sentence_count"],
               [["u1", "mri", "strong", "0.9100", "equipment:3", "2"],
                ["u2", "mri", "suggested", "0.8800", "capability:0", "0"]])
    _write_csv(refs, ["unique_id", "tag_id", "tag_type", "evidence_refs"],
               [["u1", "mri", "service", "equipment:3;procedure:7"],
                ["u1", "specialty:radiology", "specialty", ""]])
    idx = load_evidence_index(scores, refs)
    assert set(idx) == {("u1", "mri"), ("u2", "mri")}
    assert idx[("u1", "mri")].fields == frozenset({"equipment", "procedure"})
    assert idx[("u1", "mri")].best_probability == pytest.approx(0.91)
    assert idx[("u2", "mri")].fields == frozenset({"capability"})
    assert idx[("u2", "mri")].sentence_count == 1


def test_evidence_index_without_refs_file(tmp_path):
    scores = tmp_path / "scores.csv"
    _write_csv(scores, ["unique_id", "tag_id", "class"], [["u1", "mri", "strong"]])
    ev = load_evidence_index(scores, tmp_path / "missing.csv")[("u1", "mri")]
    assert ev.best_probability is None and ev.sentence_count == 1


def test_facilities_file_tsv_with_partial_columns(tmp_path):
    path = tmp_path / "f.tsv"
    _write_csv(path, ["unique_id", "best_lat", "best_lon", "name"], [["u1", "20", "85", "A"], ["", "", "", ""]],
               delimiter="\t")
    facilities, report = load_facilities_file(path)
    assert [f.unique_id for f in facilities] == ["u1"]
    assert "n_beds" in report.missing_optional


def test_facilities_file_missing_required_column(tmp_path):
    path = tmp_path / "f.csv"
    _write_csv(path, ["unique_id", "name"], [["u1", "A"]])
    with pytest.raises(ValueError, match="best_lat"):
        load_facilities_file(path)


class FakeSQL:
    def __init__(self, columns, rows):
        self.columns, self.rows, self.statements = columns, rows, []

    def query(self, statement):
        self.statements.append(statement)
        if statement.endswith("LIMIT 0"):
            return self.columns, []
        selected = [c.split(" AS ")[-1] for c in statement[len("SELECT "):statement.index(" FROM")].split(", ")]
        return selected, [[r.get(c) for c in selected] for r in self.rows]


def test_sql_loader_selects_only_existing_columns(tmp_path):
    db = FakeSQL(["unique_id", "best_lat", "best_lon", "specialties_std", "brand_new"],
                 [{"unique_id": "u1", "best_lat": 20.0, "best_lon": 85.0, "specialties_std": '["cardiology"]'}])
    facilities, report = load_facilities_sql(db, cache_path=tmp_path / "cache.tsv")
    assert facilities[0].specialties == frozenset({"cardiology"})
    assert "n_beds" not in db.statements[-1] and "brand_new" not in db.statements[-1]
    assert "to_json(specialties_std) AS specialties_std" in db.statements[-1]
    cached, _ = load_facilities_file(tmp_path / "cache.tsv")
    assert cached[0].specialties == frozenset({"cardiology"})


def test_committed_catalog_loads():
    tags = load_tag_catalog()
    ids = {t.id for t in tags}
    assert "kidney-dialysis" in ids and any(t.is_specialty for t in tags)
    norm = load_specialty_normalizer()
    assert norm("ENT") == "otolaryngology"
    assert norm("obGy") == "gynecologyAndObstetrics"
    assert norm("Paediatrics") == "pediatrics"
    assert norm("someSpecialtyAddedNextMonth") == "someSpecialtyAddedNextMonth"
