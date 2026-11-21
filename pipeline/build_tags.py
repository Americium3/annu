"""Build the searchable tag catalog from the cleaned Databricks facility tables.

Two tag layers are produced:

1. Service / condition tags (``data/tags/service_tags.json``)
   Curated in ``tag_dictionary.py`` and matched against the free-text procedure,
   capability and equipment sentences in ``model_evidence_items``. Negated
   mentions ("no dialysis facility") are ignored.

2. Specialty tags (``data/tags/specialty_tags.json``)
   ``model_facilities.specialties_std`` with remaining spelling / alias variants
   merged (e.g. ``Paediatrics``, ``ENT``, ``obstetricsAndGynaecology``). Values
   below ``--min-facilities`` go to ``specialty_unmapped.csv`` for review.

It also writes ``facility_tags.csv``: one row per (facility, tag) with the
evidence sentence references, which later steps use to answer "does any facility
offer X?" and to rank the nearest ones.

Usage:
  export DATABRICKS_HOST=... DATABRICKS_WAREHOUSE_ID=... [DATABRICKS_TOKEN=...]
  python pipeline/build_tags.py                       # query Databricks
  python pipeline/build_tags.py --evidence-cache ev.tsv --specialty-cache sp.tsv   # reuse dumps
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tag_dictionary import TAGS  # noqa: E402
from tag_matcher import TagMatcher  # noqa: E402

SCHEMA = "workspace.cardinal_virtues"
EVIDENCE_FIELDS = ("procedure", "capability", "equipment")
REPO_ROOT = Path(__file__).resolve().parent.parent
csv.field_size_limit(sys.maxsize)

# ── Specialty normalization ────────────────────────────────────────────

BRITISH_TO_AMERICAN = [
    ("paediatr", "pediatr"), ("paedodont", "pedodont"), ("orthopaed", "orthoped"), ("gynaec", "gynec"),
    ("haemat", "hemat"), ("anaesth", "anesth"), ("oesoph", "esoph"), ("foetal", "fetal"), ("homoeo", "homeo"),
    ("gynocolog", "gynecolog"), ("gynae", "gyne"),
]

# normalized key -> canonical normalized key
SPECIALTY_ALIASES = {
    "ent": "otolaryngology", "otorhinolaryngology": "otolaryngology", "entotorhinolaryngologist": "otolaryngology",
    "earnosethroatentspecialist": "otolaryngology",
    "dental": "dentistry", "generaldentistry": "dentistry", "dentalsurgery": "dentistry",
    "obstetricsandgynecology": "gynecologyandobstetrics", "obstetricsgynecology": "gynecologyandobstetrics",
    "obgy": "gynecologyandobstetrics", "obgyn": "gynecologyandobstetrics",
    "orthopedics": "orthopedicsurgery", "orthorthopedicsurgery": "orthopedicsurgery",
    "anesthesiology": "anesthesia",
    "endocrinology": "endocrinologyanddiabetesandmetabolism", "diabetology": "endocrinologyanddiabetesandmetabolism",
    "endocrinologyanddiabetology": "endocrinologyanddiabetesandmetabolism",
    "pedodontics": "pediatricdentistry", "pedodontist": "pediatricdentistry", "kidsdentistry": "pediatricdentistry",
    "pedodonticsandpreventivedentistry": "pediatricdentistry",
    "neonatology": "neonatologyperinatalmedicine", "neonatalperinatalmedicine": "neonatologyperinatalmedicine",
    "criticalcare": "criticalcaremedicine", "icuandcriticalcare": "criticalcaremedicine",
    "intensivecareunit": "criticalcaremedicine",
    "generalmedicine": "internalmedicine", "generalphysician": "internalmedicine", "medicine": "internalmedicine",
    "generalinternalmedicine": "internalmedicine",
    "pulmonarymedicine": "pulmonology", "respiratorymedicine": "pulmonology",
    "pulmonologyandrespiratorymedicine": "pulmonology",
    "oncology": "medicaloncology", "clinicaloncology": "medicaloncology", "cancercare": "medicaloncology",
    "oncosurgery": "surgicaloncology",
    "physiotherapist": "physiotherapy",
    "cardiologist": "cardiology",
    "nutritionanddietetics": "dietetics", "dieteticsandnutrition": "dietetics", "nutrition": "dietetics",
    "dietitiannutritionist": "dietetics", "dietitian": "dietetics",
    "nephrologyincludingdialysis": "nephrology",
    "infertility": "reproductiveendocrinologyandinfertility", "fertility": "reproductiveendocrinologyandinfertility",
    "ivf": "reproductiveendocrinologyandinfertility", "infertilitymedicine": "reproductiveendocrinologyandinfertility",
    "jointreplacementsurgery": "jointreconstructionsurgery",
    "spinesurgery": "orthopedicspinesurgery",
    "cosmetology": "cosmeticdermatology",
    "radiodiagnosis": "diagnosticradiology",
    "orthodontist": "orthodontics", "periodontist": "periodontics", "periodontology": "periodontics",
    "prosthodontist": "prosthodontics", "endodontist": "endodontics",
    "implantology": "dentalimplants", "implantdentistry": "dentalimplants", "dentalimplantology": "dentalimplants",
    "implantologist": "dentalimplants",
    "neuroscience": "neurosciences",
    "dentalimplant": "dentalimplants",
    "accidentandemergency": "emergencymedicine",
    "nephrologyanddialysis": "nephrology",
    "pediatricandstrabismusophthalmology": "pediatricsandstrabismusophthalmology",
    "pediatricophthalmologyandsquint": "pediatricsandstrabismusophthalmology",
    "gyneoncology": "gynecologiconcology", "gynecologicaloncology": "gynecologiconcology",
    "gyneconcology": "gynecologiconcology",
}

LABEL_ACRONYMS = {"Ent": "ENT", "Gi": "GI", "Tmj": "TMJ", "Bmt": "BMT", "Pmr": "PM&R", "Pm": "PM", "Icu": "ICU",
                  "Ivf": "IVF", "Ctvs": "CTVS", "Hpb": "HPB", "Icl": "ICL", "Prk": "PRK",
                  "Hiv": "HIV", "Ct": "CT", "Mri": "MRI"}
LOWER_WORDS = {"and", "or", "of", "for", "the", "in", "with"}


def specialty_key(raw: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", raw.lower())
    for brit, us in BRITISH_TO_AMERICAN:
        key = key.replace(brit, us)
    return SPECIALTY_ALIASES.get(key, key)


def specialty_label(code: str) -> str:
    s = code.replace("–", "-")
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    words = []
    for i, w in enumerate(re.split(r"[\s_/]+", s.strip())):
        if not w:
            continue
        lw = w.lower()
        if i and lw in LOWER_WORDS:
            words.append("&" if lw == "and" else lw)
            continue
        w = w[0].upper() + w[1:]
        words.append(LABEL_ACRONYMS.get(w, w))
    label = " ".join(words)
    return re.sub(r" PM&R$", " (PM&R)", label)


def is_camel_code(raw: str) -> bool:
    return bool(re.fullmatch(r"[a-z][A-Za-z0-9–-]*", raw))


# ── Data access ────────────────────────────────────────────────────────

def load_specialties(args) -> list[tuple[str, list[str]]]:
    if args.specialty_cache and Path(args.specialty_cache).exists():
        with open(args.specialty_cache) as f:
            r = csv.reader(f, delimiter="\t")
            next(r)
            return [(uid, json.loads(arr) if arr else []) for uid, arr in r]
    from databricks_sql import DatabricksSQL
    db = DatabricksSQL()
    _, rows = db.query(f"SELECT unique_id, to_json(specialties_std) FROM {SCHEMA}.model_facilities")
    data = [(uid, json.loads(arr) if arr else []) for uid, arr in rows]
    if args.specialty_cache:
        with open(args.specialty_cache, "w", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["unique_id", "specialties_std"])
            w.writerows((uid, json.dumps(arr)) for uid, arr in data)
    return data


def load_evidence(args) -> list[tuple[str, str, int, str]]:
    if args.evidence_cache and Path(args.evidence_cache).exists():
        with open(args.evidence_cache) as f:
            r = csv.reader(f, delimiter="\t")
            next(r)
            return [(uid, field, int(idx), text) for uid, field, idx, text in r]
    from databricks_sql import DatabricksSQL
    db = DatabricksSQL()
    fields = ", ".join(f"'{f}'" for f in EVIDENCE_FIELDS)
    rows: list[tuple[str, str, int, str]] = []
    buckets = 16  # keep each INLINE result well under the 25 MiB limit
    for b in range(buckets):
        _, part = db.query(
            f"SELECT unique_id, field, item_idx, text FROM {SCHEMA}.model_evidence_items "
            f"WHERE field IN ({fields}) AND pmod(hash(unique_id), {buckets}) = {b}")
        rows += [(uid, field, int(idx), text or "") for uid, field, idx, text in part]
        print(f"  evidence bucket {b + 1}/{buckets}: {len(part)} rows", file=sys.stderr)
    if args.evidence_cache:
        with open(args.evidence_cache, "w", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["unique_id", "field", "item_idx", "text"])
            w.writerows(rows)
    return rows


# ── Builders ───────────────────────────────────────────────────────────

def build_specialty_tags(facilities, min_facilities):
    facilities_by_key: dict[str, set[str]] = collections.defaultdict(set)
    variants: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for uid, arr in facilities:
        for raw in set(arr):
            raw = (raw or "").strip()
            if not raw:
                continue
            key = specialty_key(raw)
            if not key:
                continue
            facilities_by_key[key].add(uid)
            variants[key][raw] += 1

    tags, unmapped, facility_rows = [], [], []
    for key, uids in facilities_by_key.items():
        counter = variants[key]
        # Prefer the most common camelCase spelling as the canonical code.
        camel = [(n, v) for v, n in counter.items() if is_camel_code(v)]
        code = max(camel)[1] if camel else counter.most_common(1)[0][0]
        if len(uids) < min_facilities:
            unmapped.append((code, len(uids), "; ".join(sorted(counter))))
            continue
        tags.append({
            "id": f"specialty:{code}",
            "code": code,
            "label": specialty_label(code),
            "facilityCount": len(uids),
            "variants": [v for v, _ in counter.most_common()],
        })
        facility_rows += [(uid, f"specialty:{code}", "specialty", "") for uid in uids]
    tags.sort(key=lambda t: (-t["facilityCount"], t["code"]))
    unmapped.sort(key=lambda r: (-r[1], r[0]))
    return tags, unmapped, facility_rows


def build_service_tags(evidence, n_examples=3):
    matcher = TagMatcher()
    hits: dict[str, dict[str, list[tuple[str, int]]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    examples: dict[str, list[str]] = collections.defaultdict(list)
    negated: collections.Counter = collections.Counter()
    sentence_counts: collections.Counter = collections.Counter()
    field_counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    for uid, field, idx, text in evidence:
        matched, negated_ids = matcher.match(text)
        negated.update(negated_ids)
        for tag_id in matched:
            hits[tag_id][uid].append((field, idx))
            sentence_counts[tag_id] += 1
            field_counts[tag_id][field] += 1
            if len(examples[tag_id]) < n_examples and len(text) < 220 and text not in examples[tag_id]:
                examples[tag_id].append(text)

    tags, facility_rows = [], []
    for tag in TAGS:
        by_facility = hits.get(tag.id, {})
        tags.append({
            "id": tag.id,
            "label": tag.label,
            "kind": tag.kind,
            "group": tag.group,
            "synonyms": list(tag.synonyms),
            "facilityCount": len(by_facility),
            "evidenceSentenceCount": sentence_counts[tag.id],
            "negatedSentenceCount": negated[tag.id],
            "fieldCounts": {f: field_counts[tag.id][f] for f in EVIDENCE_FIELDS},
            "exampleEvidence": examples[tag.id],
        })
        for uid, refs in by_facility.items():
            facility_rows.append((uid, tag.id, tag.kind, ";".join(f"{f}:{i}" for f, i in refs)))
    return tags, facility_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "data" / "tags"))
    ap.add_argument("--min-facilities", type=int, default=5, help="minimum facilities for a specialty tag")
    ap.add_argument("--evidence-cache", help="TSV cache of evidence sentences (read if present, else written)")
    ap.add_argument("--specialty-cache", help="TSV cache of specialties_std (read if present, else written)")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("Loading specialties ...", file=sys.stderr)
    facilities = load_specialties(args)
    print("Loading evidence sentences ...", file=sys.stderr)
    evidence = load_evidence(args)

    specialty_tags, unmapped, specialty_rows = build_specialty_tags(facilities, args.min_facilities)
    service_tags, service_rows = build_service_tags(evidence)

    all_uids = {uid for uid, _ in facilities}
    tagged_by_service = {r[0] for r in service_rows}
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"facilities": f"{SCHEMA}.model_facilities", "evidence": f"{SCHEMA}.model_evidence_items"},
        "facilityCount": len(all_uids),
        "facilitiesWithServiceTag": len(tagged_by_service & all_uids),
        "evidenceSentencesScanned": len(evidence),
    }

    (out / "service_tags.json").write_text(json.dumps({"meta": meta, "tags": service_tags}, indent=2, ensure_ascii=False) + "\n")
    (out / "specialty_tags.json").write_text(json.dumps(
        {"meta": {**meta, "minFacilities": args.min_facilities, "unmappedValues": len(unmapped)}, "tags": specialty_tags},
        indent=2, ensure_ascii=False) + "\n")

    with open(out / "tags.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "label", "type", "group", "facility_count"])
        for t in sorted(service_tags, key=lambda t: (t["group"], -t["facilityCount"])):
            w.writerow([t["id"], t["label"], t["kind"], t["group"], t["facilityCount"]])
        for t in specialty_tags:
            w.writerow([t["id"], t["label"], "specialty", "", t["facilityCount"]])

    with open(out / "specialty_unmapped.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["value", "facility_count", "raw_variants"])
        w.writerows(unmapped)

    with open(out / "facility_tags.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unique_id", "tag_id", "tag_type", "evidence_refs"])
        w.writerows(sorted(service_rows + specialty_rows))

    print(f"Service/condition tags: {len(service_tags)} "
          f"({sum(1 for t in service_tags if t['facilityCount'])} with ≥1 facility)", file=sys.stderr)
    print(f"Specialty tags: {len(specialty_tags)} (≥{args.min_facilities} facilities); "
          f"{len(unmapped)} rare values set aside", file=sys.stderr)
    print(f"Facilities with ≥1 service tag: {meta['facilitiesWithServiceTag']}/{meta['facilityCount']}", file=sys.stderr)
    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
