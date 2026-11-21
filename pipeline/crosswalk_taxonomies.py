"""Cross-reference the tag catalog with standard healthcare taxonomies.

Service / condition tags  ->  NLM MeSH descriptors (ID, preferred label, tree numbers and
                              top-level MeSH category) and WHO ICD-10 (2019) codes, from the
                              curated labels/codes in ``tag_references.py``. Every MeSH label
                              is resolved live against the NLM MeSH API and every ICD-10 code
                              is validated against the WHO 2019 code set; the script fails on
                              anything it cannot verify.
Specialty tags            ->  NUCC Health Care Provider Taxonomy (v26.1): exact name matches,
                              plus the curated ``SPECIALTY_TO_NUCC`` table for naming
                              differences. Unmatched specialties get a fuzzy "candidate" for
                              review, never an automatic mapping.

Sources:
  MeSH       https://id.nlm.nih.gov/mesh/       (U.S. National Library of Medicine)
  ICD-10     WHO ICD-10 2019, via the ``simple-icd-10`` package
  NUCC       https://www.nucc.org/ provider taxonomy CSV (National Uniform Claim Committee)

Outputs (``data/tags/``):
  taxonomy_crosswalk.json   both layers with full reference details
  taxonomy_crosswalk.csv    one row per (tag, reference) for review

Usage:
  pip install -r pipeline/requirements.txt
  python3 pipeline/crosswalk_taxonomies.py [--nucc-csv nucc_taxonomy_261.csv]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import difflib
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import simple_icd_10 as icd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tag_dictionary import TAGS  # noqa: E402
from tag_references import REFERENCES  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
MESH_API = "https://id.nlm.nih.gov/mesh"
NUCC_VERSION = "26.1"
NUCC_URL = "https://www.nucc.org/images/stories/CSV/nucc_taxonomy_261.csv"

# Specialty tag code -> (NUCC code, relation). "equivalent": same concept; "broader": the
# NUCC code is the nearest parent because NUCC has no code this specific.
SPECIALTY_TO_NUCC: dict[str, tuple[str, str]] = {
    "gynecologyAndObstetrics": ("207V00000X", "equivalent"),
    "dentistry": ("122300000X", "equivalent"),
    "orthopedicSurgery": ("207X00000X", "equivalent"),
    "generalSurgery": ("208600000X", "equivalent"),
    "pathology": ("207ZP0102X", "equivalent"),
    "radiology": ("2085R0202X", "equivalent"),
    "diagnosticRadiology": ("2085R0202X", "equivalent"),
    "endocrinologyAndDiabetesAndMetabolism": ("207RE0101X", "equivalent"),
    "reproductiveEndocrinologyAndInfertility": ("207VE0102X", "equivalent"),
    "neurosurgery": ("207T00000X", "equivalent"),
    "orthodontics": ("1223X0400X", "equivalent"),
    "pulmonology": ("207RP1001X", "equivalent"),
    "anesthesia": ("207L00000X", "equivalent"),
    "neonatologyPerinatalMedicine": ("2080N0001X", "equivalent"),
    "maternalFetalMedicineOrPerinatology": ("207VM0101X", "equivalent"),
    "retinaAndVitreoretinalOphthalmology": ("207WX0107X", "equivalent"),
    "cardiacSurgery": ("208G00000X", "equivalent"),
    "cardiothoracicSurgery": ("208G00000X", "equivalent"),
    "jointReconstructionSurgery": ("207XS0114X", "equivalent"),
    "preventiveMedicine": ("2083P0901X", "equivalent"),
    "publicHealth": ("2083P0901X", "equivalent"),
    "corneaOphthalmology": ("207WX0120X", "equivalent"),
    "glaucomaOphthalmology": ("207WX0009X", "equivalent"),
    "colorectalSurgery": ("208C00000X", "equivalent"),
    "oculoplasticsAndReconstructiveOrbitalSurgery": ("207WX0200X", "equivalent"),
    "obstetricsAndMaternityCare": ("207VX0000X", "equivalent"),
    "pediatricsAndStrabismusOphthalmology": ("207WX0110X", "equivalent"),
    "pediatricOphthalmology": ("207WX0110X", "equivalent"),
    "interventionalRadiology": ("2085R0204X", "equivalent"),
    "painMedicinePMR": ("2081P2900X", "equivalent"),
    "sportsMedicinePMR": ("2081S0010X", "equivalent"),
    "geriatricsInternalMedicine": ("207RG0300X", "equivalent"),
    "gynecologicalOncology": ("207VX0201X", "equivalent"),
    "familyPlanningAndComplexContraception": ("207VC0300X", "equivalent"),
    "pediatricOrthopedicSurgery": ("207XP3100X", "equivalent"),
    "reconstructivePlasticSurgery": ("2086S0122X", "equivalent"),
    "hospiceAndPalliativeInternalMedicine": ("207RH0002X", "equivalent"),
    "podiatry": ("213E00000X", "equivalent"),
    "nuclearMedicineAndMolecularImaging": ("207U00000X", "equivalent"),
    "epilepsyNeurology": ("2084E0001X", "equivalent"),
    "uveitisOphthalmology": ("207WX0108X", "equivalent"),
    "neuropsychiatry": ("2084B0040X", "equivalent"),
    "orthopedicSpineSurgery": ("207XS0117X", "equivalent"),
    "dietetics": ("133V00000X", "equivalent"),
    "pediatricNeurodevelopmentalDisabilities": ("2080P0008X", "equivalent"),
    "urogynecologyAndReconstructivePelvisSurgery": ("207VF0040X", "equivalent"),
    "dentalAnesthesia": ("1223D0004X", "equivalent"),
    "footAndAnkleOrthopedicSurgery": ("207XX0004X", "equivalent"),
    "pediatricNeurology": ("2084N0402X", "equivalent"),
    "physiotherapy": ("225100000X", "equivalent"),
    "pediatricAllergyAndImmunology": ("2080P0201X", "equivalent"),
    "cardiology": ("207RC0000X", "equivalent"),
    "infectiousDiseases": ("207RI0200X", "equivalent"),
    "criticalCareMedicine": ("207RC0200X", "equivalent"),
    "nutritionAndDietetics": ("133V00000X", "equivalent"),
    "microbiology": ("207ZM0300X", "equivalent"),
    "orthopedicSportsMedicine": ("207XX0005X", "equivalent"),
    "handOrUpperExtremityAndPeripheralNerveSurgery": ("207XS0106X", "equivalent"),
    "handAndUpperExtremitiesSurgery": ("207XS0106X", "equivalent"),
    "addictionMedicinePM": ("2083A0300X", "equivalent"),
    "addictionInternalMedicine": ("207RA0401X", "equivalent"),
    "neuromuscularMedicinePMR": ("2081N0008X", "equivalent"),
    "childNeurology": ("2084N0402X", "equivalent"),
    "brainInjuryNeurology": ("2084P0301X", "equivalent"),
    "sleepMedicineNeurology": ("2084S0012X", "equivalent"),
    "oralPathology": ("1223P0106X", "equivalent"),
    "psychology": ("103T00000X", "equivalent"),
    "clinicalPsychology": ("103TC0700X", "equivalent"),
    "audiology": ("231H00000X", "equivalent"),
    "sportsInternalMedicine": ("207RS0010X", "equivalent"),
    "generalThoracicSurgery": ("208G00000X", "equivalent"),
    "orthopedicTraumaAndFractureSurgery": ("207XX0801X", "equivalent"),
    "neurotologyAndOtology": ("207YX0901X", "equivalent"),
    "maxillofacialSurgery": ("204E00000X", "equivalent"),
    "oralMaxillofacialSurgery": ("204E00000X", "equivalent"),
    "prostheticDentistry": ("1223P0700X", "equivalent"),
    "publicHealthDentistry": ("1223D0001X", "equivalent"),
    "geriatricInternalMedicine": ("207RG0300X", "equivalent"),
    "pediatricHematoOncology": ("2080P0207X", "equivalent"),
    "uveaOphthalmology": ("207WX0108X", "equivalent"),
    "facialPlasticsAndReconstructiveOtolaryngology": ("207YS0123X", "equivalent"),
    "interventionalCardiologyCentre": ("207RI0011X", "equivalent"),
    "footSurgery": ("207XX0004X", "equivalent"),
    "histopathology": ("207ZP0101X", "equivalent"),
    "aestheticDentistry": ("122300000X", "broader"),
    "cosmeticDentistry": ("122300000X", "broader"),
    "dentalImplants": ("122300000X", "broader"),
    "dentoalveolarSurgery": ("1223S0112X", "broader"),
    "craniofacialAndCleftOralMaxillofacialSurgery": ("1223S0112X", "broader"),
    "spineNeurosurgery": ("207T00000X", "broader"),
    "skullBaseNeurosurgery": ("207T00000X", "broader"),
    "pediatricNeurosurgery": ("207T00000X", "broader"),
    "cataractAndAnteriorSegmentSurgery": ("207W00000X", "broader"),
    "refractiveSurgeryOphthalmology": ("207W00000X", "broader"),
    "eyeTraumaAndEmergencyEyeCare": ("207W00000X", "broader"),
    "cosmeticDermatology": ("207N00000X", "broader"),
    "hairAndNailDisorders": ("207N00000X", "broader"),
    "minimallyInvasiveSurgeryAndEndourology": ("208800000X", "broader"),
    "andrologyAndMaleFertility": ("208800000X", "broader"),
    "urologicOncology": ("208800000X", "broader"),
    "renalTransplantationUrology": ("208800000X", "broader"),
    "bariatricSurgery": ("208600000X", "broader"),
    "hepatopancreatobiliarySurgery": ("208600000X", "broader"),
    "breastSurgery": ("208600000X", "broader"),
    "endocrineSurgery": ("208600000X", "broader"),
    "shoulderAndElbowOrthopedicSurgery": ("207X00000X", "broader"),
    "orthopedicOncology": ("207X00000X", "broader"),
    "headacheMedicine": ("2084N0400X", "broader"),
    "movementDisorders": ("2084N0400X", "broader"),
    "headAndNeckSurgeryOtolaryngology": ("207Y00000X", "broader"),
    "breastImaging": ("2085R0202X", "broader"),
    "burnAndTraumaPlasticSurgery": ("208200000X", "broader"),
    "aestheticAndCosmeticSurgery": ("208200000X", "broader"),
    "cosmeticSurgery": ("208200000X", "broader"),
    "cosmeticMaxillofacialSurgery": ("204E00000X", "broader"),
    "craniomaxillofacialTraumaSurgery": ("204E00000X", "broader"),
    "oralSurgery": ("204E00000X", "broader"),
    "tmjSurgery": ("204E00000X", "broader"),
    "laryngology": ("207Y00000X", "broader"),
    "rhinology": ("207Y00000X", "broader"),
    "gynecologicalSurgery": ("207V00000X", "broader"),
    "cosmeticGynecology": ("207V00000X", "broader"),
    "neuroanesthesiology": ("207L00000X", "broader"),
    "obstetricAnesthesiology": ("207L00000X", "broader"),
    "andrology": ("208800000X", "broader"),
    "endourology": ("208800000X", "broader"),
    "uroOncology": ("208800000X", "broader"),
    "uroSurgery": ("208800000X", "broader"),
    "lasikSurgery": ("207W00000X", "broader"),
    "iclSurgery": ("207W00000X", "broader"),
    "prkSurgery": ("207W00000X", "broader"),
    "ocularOncology": ("207W00000X", "broader"),
    "arthroscopicSurgery": ("207X00000X", "broader"),
    "dentures": ("1223P0700X", "broader"),
    "rheumatologyAndImmunology": ("207RR0500X", "broader"),
    "palliativeMedicine": ("207RH0002X", "broader"),
    "pediatricOncology": ("2080P0207X", "broader"),
    "pediatricsAndNeonatology": ("208000000X", "broader"),
    "surgicalGastroenterology": ("208600000X", "broader"),
    "gastrointestinalSurgery": ("208600000X", "broader"),
    "upperGIAndForegutSurgery": ("208600000X", "broader"),
    "painManagement": ("207LP2900X", "broader"),
    "neuroOncology": ("2084N0400X", "broader"),
}

# Exact name matches are only trusted inside these provider groupings; elsewhere a name like
# "Radiology" can collide with e.g. a podiatry specialization.
TRUSTED_GROUPINGS = ["Allopathic & Osteopathic Physicians", "Dental Providers", "Eye and Vision Services Providers"]


def fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp)


# ── MeSH ───────────────────────────────────────────────────────────────

def resolve_mesh(labels: list[str]) -> dict[str, dict]:
    def one(label):
        q = urllib.parse.urlencode({"label": label, "match": "exact", "limit": 5})
        hits = [h for h in fetch_json(f"{MESH_API}/lookup/descriptor?{q}") if h["label"] == label]
        if not hits:
            return label, None
        uid = hits[0]["resource"].rsplit("/", 1)[1]
        detail = fetch_json(f"{MESH_API}/{uid}.json")
        raw_trees = detail.get("treeNumber", [])
        raw_trees = [raw_trees] if isinstance(raw_trees, str) else raw_trees  # one tree number -> plain string
        trees = sorted(t.rsplit("/", 1)[1] for t in raw_trees)
        return label, {"id": uid, "label": label, "treeNumbers": trees, "url": f"https://meshb.nlm.nih.gov/record/ui?ui={uid}"}

    with cf.ThreadPoolExecutor(6) as ex:
        resolved = dict(ex.map(one, labels))
    missing = [l for l, v in resolved.items() if v is None]
    if missing:
        raise SystemExit(f"MeSH labels not found (fix tag_references.py): {missing}")
    return resolved


def mesh_tree_labels(tree_numbers: set[str]) -> dict[str, str]:
    """Labels for MeSH tree numbers (e.g. C12 -> Urogenital Diseases) via the NLM SPARQL endpoint."""
    out: dict[str, str] = {}
    trees = sorted(tree_numbers)
    for i in range(0, len(trees), 40):
        values = " ".join(f"mesh:{t}" for t in trees[i:i + 40])
        query = ("PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#> PREFIX mesh: <http://id.nlm.nih.gov/mesh/> "
                 "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
                 f"SELECT ?t ?l WHERE {{ VALUES ?t {{ {values} }} ?d meshv:treeNumber ?t . ?d rdfs:label ?l }}")
        url = f"{MESH_API}/sparql?" + urllib.parse.urlencode({"query": query, "format": "JSON"})
        for b in fetch_json(url)["results"]["bindings"]:
            out[b["t"]["value"].rsplit("/", 1)[1]] = b["l"]["value"]
    return out


# ── ICD-10 ─────────────────────────────────────────────────────────────

def icd10_entry(code: str) -> dict:
    if not icd.is_valid_item(code):
        raise SystemExit(f"Invalid WHO ICD-10 code (fix tag_references.py): {code}")
    kind = "chapter" if icd.is_chapter(code) else "block" if icd.is_block(code) else "category"
    if kind == "category" and "." in code:
        kind = "subcategory"
    chapter = code if icd.is_chapter(code) else next(a for a in icd.get_ancestors(code) if icd.is_chapter(a))
    return {"code": code, "description": icd.get_description(code), "level": kind,
            "chapter": chapter, "chapterDescription": icd.get_description(chapter),
            "url": f"https://icd.who.int/browse10/2019/en#/{code}"}


# ── NUCC ───────────────────────────────────────────────────────────────

def load_nucc(path: str | None) -> list[dict]:
    if path and Path(path).exists():
        raw = Path(path).read_bytes()
    else:
        with urllib.request.urlopen(NUCC_URL, timeout=60) as resp:
            raw = resp.read()
        if path:
            Path(path).write_bytes(raw)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:  # some NUCC releases are Windows-1252 encoded
        text = raw.decode("cp1252")
    return list(csv.DictReader(io.StringIO(text)))


def nucc_norm(s: str) -> str:
    s = s.lower().replace("&", "and")
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"[^a-z]", "", s)


def nucc_entry(row: dict, relation: str, method: str, score: float | None = None) -> dict:
    entry = {"code": row["Code"], "grouping": row["Grouping"], "classification": row["Classification"],
             "specialization": row["Specialization"] or None, "displayName": row["Display Name"],
             "relation": relation, "method": method}
    if score is not None:
        entry["similarity"] = round(score, 3)
    return entry


def map_specialties(tags: list[dict], nucc: list[dict]) -> list[dict]:
    by_code = {r["Code"]: r for r in nucc}
    rank = {g: i for i, g in enumerate(TRUSTED_GROUPINGS)}
    exact: dict[str, dict] = {}
    names: dict[str, dict] = {}
    for r in nucc:
        if r["Grouping"] not in rank:
            continue
        c, sp = r["Classification"].strip(), r["Specialization"].strip()
        keys = {nucc_norm(sp) + nucc_norm(c), nucc_norm(c) + nucc_norm(sp), nucc_norm(sp)} if sp else {nucc_norm(c)}
        for k in keys:
            if k and (k not in exact or rank[r["Grouping"]] < rank[exact[k]["Grouping"]]):
                exact[k] = r
        names[r["Code"]] = r
    for code, (nucc_code, _) in SPECIALTY_TO_NUCC.items():
        if nucc_code not in by_code:
            raise SystemExit(f"SPECIALTY_TO_NUCC[{code!r}] -> {nucc_code} is not in NUCC v{NUCC_VERSION}")

    candidates = {nucc_norm(f"{r['Specialization']} {r['Classification']}" if r["Specialization"] else r["Classification"]): r
                  for r in names.values()}
    out = []
    for t in tags:
        code = t["code"]
        if code in SPECIALTY_TO_NUCC:
            nucc_code, relation = SPECIALTY_TO_NUCC[code]
            ref = nucc_entry(by_code[nucc_code], relation, "curated")
        elif nucc_norm(code) in exact:
            ref = nucc_entry(exact[nucc_norm(code)], "equivalent", "exact-name")
        else:
            best = difflib.get_close_matches(nucc_norm(code), candidates.keys(), n=1, cutoff=0.88)
            if best:
                score = difflib.SequenceMatcher(None, nucc_norm(code), best[0]).ratio()
                ref = nucc_entry(candidates[best[0]], "candidate", "fuzzy-name", score)
            else:
                ref = None
        out.append({"id": t["id"], "code": code, "label": t["label"], "facilityCount": t["facilityCount"], "nucc": ref})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "data" / "tags"))
    ap.add_argument("--nucc-csv", help="local NUCC taxonomy CSV (downloaded to this path if missing)")
    args = ap.parse_args()
    out = Path(args.out_dir)

    if set(REFERENCES) != {t.id for t in TAGS}:
        raise SystemExit(f"tag_references.py out of sync with tag_dictionary.py: {set(REFERENCES) ^ {t.id for t in TAGS}}")

    service = json.loads((out / "service_tags.json").read_text())["tags"]
    specialty = json.loads((out / "specialty_tags.json").read_text())["tags"]

    print("Resolving MeSH descriptors ...", file=sys.stderr)
    mesh = resolve_mesh(sorted({l for r in REFERENCES.values() for l in r["mesh"]}))
    top_trees = {t.split(".")[0] for m in mesh.values() for t in m["treeNumbers"]}
    tree_labels = mesh_tree_labels(top_trees)

    service_rows = []
    for t in service:
        refs = REFERENCES[t["id"]]
        mesh_refs = []
        for label in refs["mesh"]:
            m = dict(mesh[label])
            m["categories"] = sorted({f"{tn.split('.')[0]} {tree_labels.get(tn.split('.')[0], '')}".strip()
                                      for tn in m["treeNumbers"]})
            mesh_refs.append(m)
        service_rows.append({"id": t["id"], "label": t["label"], "kind": t["kind"], "group": t["group"],
                             "facilityCount": t["facilityCount"], "mesh": mesh_refs,
                             "icd10": [icd10_entry(c) for c in refs["icd10"]]})

    print("Mapping specialties to NUCC ...", file=sys.stderr)
    nucc = load_nucc(args.nucc_csv)
    specialty_rows = map_specialties(specialty, nucc)

    by_method: dict[str, int] = {}
    weighted: dict[str, int] = {}
    for s in specialty_rows:
        key = s["nucc"]["relation"] if s["nucc"] else "unmapped"
        by_method[key] = by_method.get(key, 0) + 1
        weighted[key] = weighted.get(key, 0) + s["facilityCount"]
    total_links = sum(s["facilityCount"] for s in specialty_rows)

    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "mesh": {"name": "Medical Subject Headings (MeSH), U.S. National Library of Medicine", "url": "https://id.nlm.nih.gov/mesh/"},
            "icd10": {"name": "WHO ICD-10, 2019 edition", "url": "https://icd.who.int/browse10/2019/en"},
            "nucc": {"name": f"NUCC Health Care Provider Taxonomy v{NUCC_VERSION}", "url": NUCC_URL},
        },
        "serviceTags": {
            "count": len(service_rows),
            "withMesh": sum(1 for s in service_rows if s["mesh"]),
            "withIcd10": sum(1 for s in service_rows if s["icd10"]),
            "meshDescriptors": len(mesh),
        },
        "specialtyTags": {
            "count": len(specialty_rows),
            "byRelation": by_method,
            "facilityWeightedShare": {k: round(v / total_links, 4) for k, v in weighted.items()},
        },
    }
    (out / "taxonomy_crosswalk.json").write_text(json.dumps(
        {"meta": meta, "serviceTags": service_rows, "specialtyTags": specialty_rows}, indent=2, ensure_ascii=False) + "\n")

    with open(out / "taxonomy_crosswalk.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tag_id", "tag_label", "tag_type", "facility_count", "vocabulary", "ref_code", "ref_label", "ref_category", "relation"])
        for s in service_rows:
            for m in s["mesh"]:
                w.writerow([s["id"], s["label"], s["kind"], s["facilityCount"], "MeSH", m["id"], m["label"], "; ".join(m["categories"]), "curated"])
            for c in s["icd10"]:
                w.writerow([s["id"], s["label"], s["kind"], s["facilityCount"], "ICD-10", c["code"], c["description"],
                            f"{c['chapter']} {c['chapterDescription']}", "curated"])
        for s in specialty_rows:
            n = s["nucc"]
            w.writerow([s["id"], s["label"], "specialty", s["facilityCount"], "NUCC",
                        n["code"] if n else "", n["displayName"] if n else "", n["grouping"] if n else "",
                        n["relation"] if n else "unmapped"])

    print(json.dumps(meta["serviceTags"]), file=sys.stderr)
    print(json.dumps(meta["specialtyTags"]), file=sys.stderr)
    print(f"Wrote {out / 'taxonomy_crosswalk.json'} and taxonomy_crosswalk.csv", file=sys.stderr)


if __name__ == "__main__":
    main()
