"""Find every disease / syndrome named in the facility data and build a search alias table.

Vocabulary ("encyclopedia"):
  * NLM MeSH 2026 descriptors in the Diseases (C) and Mental Disorders (F03) trees, with all
    their entry terms (official synonyms).
  * MedlinePlus health topics (English) with their "also called" names, which add
    plain-language aliases such as "piles" -> Hemorrhoids or "HBP" -> Hypertension. A
    MedlinePlus name is only used when MeSH does not already have that term.

Steps:
  1. Scan all procedure / capability / equipment evidence sentences for every name and
     synonym (word-boundary match, longest match first, negated or planned mentions skipped,
     generic / non-medical senses blocked).
  2. Every MeSH condition found at >= --min-facilities facilities becomes a *condition tag*
     (``mesh:<UI>``), linked to the curated service tags whose MeSH descriptors are the same
     or an ancestor in the MeSH tree, and to fallback specialties by MeSH category.
  3. Write an alias table: every user-facing name (MeSH term, MedlinePlus name, curated tag
     label / synonym) -> MeSH descriptor -> curated tags, condition tag, specialty tags. The
     search step resolves user text with it, falling back from service evidence to condition
     mentions to specialty to the most comprehensive hospital in the region.

Outputs (``data/tags/``):
  condition_tags.json          MeSH conditions found in the data, with counts and links
  alias_table.csv              alias -> MeSH descriptor -> tags (for the search box)
  facility_condition_tags.csv  (gitignored) facility x condition with evidence refs

Usage:
  python3 pipeline/medical_vocabulary.py --evidence-cache /tmp/evidence.tsv \
      [--mesh-xml desc2026.xml] [--medlineplus-xml mplus_topics.xml]
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_tags import REPO_ROOT, load_evidence  # noqa: E402
from tag_dictionary import NEGATION_PATTERN, NEGATION_WINDOW_CHARS, TAGS  # noqa: E402

MESH_URL = "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2026.gz"
MEDLINEPLUS_INDEX = "https://medlineplus.gov/xml.html"

# Terms that are MeSH synonyms but in facility text are generic words or non-medical senses
# ("joint" and "grass" are entry terms of Marijuana Abuse; "eye care" maps to Eye Injuries).
BLOCKED_TERMS = {
    "disease", "diseases", "syndrome", "syndromes", "disorder", "disorders", "condition", "conditions",
    "infection", "infections", "illness", "illnesses", "emergency", "emergencies", "chronic disease",
    "chronic diseases", "chronic condition", "chronic conditions", "chronic illness", "chronic illnesses",
    "joint", "joints", "blunt", "grass", "pot", "weed", "nutrition", "eye care", "eye health",
    "bypass surgery", "covid 19 pandemic", "cysts", "cyst", "deformity", "deformities", "stress",
    "pain", "lesion", "lesions", "injury", "injuries", "wound", "wounds", "trauma", "acute",
    "weight loss", "weight reduction", "weight control", "sterility", "fractures",
}
# Curated tags whose broad MeSH descriptor must not absorb every descendant condition.
NO_DESCENDANT_ROLLUP = {"fracture-trauma": {"D014947"}}  # Wounds and Injuries
# MeSH subtrees that sit under a curated tag's descriptor for classification reasons only.
EXCLUDED_SUBTREES = {
    "skin-disease": ("C17.800.090",),  # Breast Diseases are filed under Skin Diseases
    "mental-health": ("F03.835",),  # psychological sexual dysfunctions (e.g. erectile dysfunction -> urology)
    # MeSH Neoplasms (C04) also holds benign growths; the Cancer tag must not absorb them.
    "cancer": ("C04.182", "C04.445", "C04.834", "C04.557.450.590.450", "C04.557.450.550.400",
               "C04.557.645.375", "C04.557.665.560", "C04.557.470.035", "C04.557.450.565.590.340",
               "C04.557.470.700.600", "C04.557.580.600.580"),  # cysts, hamartoma, precancerous, leiomyoma,
    # lipoma, hemangioma, nevus, adenoma, fibroma, papilloma, neurofibroma
}

# Colloquial English / Hindi names common in Indian searches that MeSH and MedlinePlus lack.
# Mapped to MeSH descriptors by preferred name; the script fails if a name is not found.
COLLOQUIAL_ALIASES = {
    "high bp": "Hypertension", "bp": "Hypertension", "blood pressure": "Hypertension",
    "sugar": "Diabetes Mellitus", "sugar problem": "Diabetes Mellitus", "madhumeh": "Diabetes Mellitus",
    "white patches": "Vitiligo", "white patch": "Vitiligo", "safed daag": "Vitiligo",
    "slip disc": "Intervertebral Disc Displacement", "slipped disc": "Intervertebral Disc Displacement",
    "appendix": "Appendicitis", "fits": "Seizures", "mirgi": "Epilepsy",
    "loose motions": "Diarrhea", "loose motion": "Diarrhea", "acidity": "Gastroesophageal Reflux",
    "brain fever": "Encephalitis", "bawaseer": "Hemorrhoids", "pathri": "Kidney Calculi",
    "motiyabind": "Cataract", "kala motia": "Glaucoma", "peeliya": "Jaundice", "dama": "Asthma",
    "lakwa": "Paralysis", "khujli": "Pruritus", "pcod": "Polycystic Ovary Syndrome", "pcos": "Polycystic Ovary Syndrome", "depression": "Depressive Disorder",
}

# Curated tag group -> fallback specialty codes (used instead of MeSH categories when a
# condition maps to a curated tag, because MeSH files some diseases under several organs).
GROUP_SPECIALTIES = {
    "Kidney & urinary": ["nephrology", "urology"], "Heart & vessels": ["cardiology"],
    "Imaging & diagnostics": ["radiology"], "Cancer": ["medicalOncology", "surgicalOncology"],
    "Women's health & fertility": ["gynecologyAndObstetrics", "reproductiveEndocrinologyAndInfertility"],
    "Children & newborns": ["pediatrics", "neonatologyPerinatalMedicine"], "Eyes": ["ophthalmology"],
    "Bones, joints & spine": ["orthopedicSurgery"], "Brain & nerves": ["neurology", "neurosurgery"],
    "Digestive & liver": ["gastroenterology", "generalSurgery"], "Ear, nose & throat": ["otolaryngology"],
    "Lungs & breathing": ["pulmonology"], "Hormones & metabolism": ["endocrinologyAndDiabetesAndMetabolism"],
    "Infections": ["infectiousDiseases", "internalMedicine"], "Skin, hair & cosmetic": ["dermatology", "plasticSurgery"],
    "Dental": ["dentistry"], "Mental health": ["psychiatry"], "Emergency & critical care": ["emergencyMedicine", "criticalCareMedicine"],
}

# MeSH top-level disease category -> specialty tag codes used as a fallback.
CATEGORY_SPECIALTIES = {
    "C01": ["infectiousDiseases", "internalMedicine"], "C04": ["medicalOncology", "surgicalOncology"],
    "C05": ["orthopedicSurgery", "rheumatology"], "C06": ["gastroenterology", "generalSurgery"],
    "C07": ["dentistry", "oralAndMaxillofacialSurgery"], "C08": ["pulmonology"], "C09": ["otolaryngology"],
    "C10": ["neurology", "neurosurgery"], "C11": ["ophthalmology"], "C12": ["urology", "nephrology"],
    # MeSH 2026 files women's conditions under C12 (there is no C13 any more).
    "C12.050": ["gynecologyAndObstetrics"], "C12.100.250": ["gynecologyAndObstetrics"], "C12.200": ["urology"],
    "C14": ["cardiology"], "C15": ["hematology"],
    "C16": ["pediatrics", "neonatologyPerinatalMedicine"], "C17": ["dermatology"],
    "C18": ["endocrinologyAndDiabetesAndMetabolism", "internalMedicine"],
    "C19": ["endocrinologyAndDiabetesAndMetabolism"], "C20": ["allergyAndImmunology", "rheumatology"],
    "C21": ["emergencyMedicine"], "C23": ["internalMedicine", "familyMedicine"], "C24": ["internalMedicine"],
    "C25": ["emergencyMedicine"], "C26": ["emergencyMedicine", "orthopedicSurgery"], "F03": ["psychiatry"],
}
# Per-descriptor fallback overrides, by MeSH preferred name (checked at start-up).
SPECIALTY_OVERRIDES = {"Leiomyoma": ["gynecologyAndObstetrics", "generalSurgery"]}  # "fibroids" in this data are uterine


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as r:
        return r.read()


def load_mesh(path: str | None) -> dict[str, dict]:
    p = Path(path) if path else None
    if not (p and p.exists()):
        data = gzip.decompress(fetch(MESH_URL))
        p = p or Path("desc2026.xml")
        p.write_bytes(data)
    desc = {}
    for _, el in ET.iterparse(str(p), events=("end",)):
        if el.tag != "DescriptorRecord":
            continue
        trees = [t.text for t in el.findall("TreeNumberList/TreeNumber")]
        if any(t.startswith("C") or t.startswith("F03") for t in trees):
            ui = el.findtext("DescriptorUI")
            name = el.findtext("DescriptorName/String")
            terms = sorted({t.text for t in el.iterfind("ConceptList/Concept/TermList/Term/String")} | {name})
            desc[ui] = {"name": name, "trees": trees, "terms": terms}
        el.clear()
    return desc


def load_medlineplus(path: str | None) -> list[dict]:
    p = Path(path) if path else None
    if not (p and p.exists()):
        latest = sorted(set(re.findall(r"mplus_topics_\d{4}-\d{2}-\d{2}\.xml", fetch(MEDLINEPLUS_INDEX).decode())))[-1]
        p = p or Path(latest)
        p.write_bytes(fetch(f"https://medlineplus.gov/xml/{latest}"))
    topics = []
    for t in ET.parse(str(p)).getroot().iter("health-topic"):
        if t.get("language") != "English":
            continue
        mesh = [m.find("descriptor").get("id") for m in t.findall("mesh-heading") if m.find("descriptor") is not None]
        topics.append({"title": t.get("title"), "also": [a.text for a in t.findall("also-called")], "mesh": mesh})
    return topics


def depth(trees: list[str]) -> int:
    return min(t.count(".") for t in trees)


def build_term_index(desc: dict, topics: list[dict]) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """Return (normalized term -> one descriptor UI, [(alias, source, ui)])."""
    cands: dict[str, set[str]] = collections.defaultdict(set)
    mplus_pref: dict[str, str] = {}
    aliases: list[tuple[str, str, str]] = []
    for ui, d in desc.items():
        for t in d["terms"]:
            cands[norm(t)].add(ui)
            aliases.append((t, "mesh_preferred" if t == d["name"] else "mesh_entry", ui))
    for tp in topics:
        uis = [u for u in tp["mesh"] if u in desc]
        if not uis:
            continue
        ui = min(uis, key=lambda u: (depth(desc[u]["trees"]), u))  # most general heading of the topic
        for t, src in [(tp["title"], "medlineplus_title")] + [(a, "medlineplus_also_called") for a in tp["also"]]:
            if norm(t) not in cands:
                cands[norm(t)].add(ui)
            if norm(t) in cands and any(u in uis for u in cands[norm(t)]):
                mplus_pref.setdefault(norm(t), next(u for u in uis if u in cands[norm(t)]))
            aliases.append((t, src, ui))
    by_name = {d["name"]: ui for ui, d in desc.items()}
    for alias, name in COLLOQUIAL_ALIASES.items():
        if name not in by_name:
            raise SystemExit(f"COLLOQUIAL_ALIASES[{alias!r}]: MeSH descriptor {name!r} not found")
        cands[norm(alias)] = {by_name[name]}
        mplus_pref[norm(alias)] = by_name[name]
        aliases.append((alias, "colloquial_curated", by_name[name]))

    index = {}
    for t, uis in cands.items():
        if t in BLOCKED_TERMS:
            continue
        if t in mplus_pref:
            index[t] = mplus_pref[t]
            continue
        exact = [u for u in uis if norm(desc[u]["name"]) == t]
        pool = exact or list(uis)
        index[t] = min(pool, key=lambda u: (depth(desc[u]["trees"]), -len(desc[u]["terms"]), u))
    return index, aliases


def scan(evidence, index: dict[str, str]):
    data_terms = {t: u for t, u in index.items() if len(t) >= 5 or " " in t}  # short acronyms are ambiguous in prose
    maxn = max(len(t.split()) for t in data_terms)
    neg = re.compile(NEGATION_PATTERN, re.I)
    hits: dict[str, dict[str, list[str]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    term_counts: collections.Counter = collections.Counter()
    examples: dict[str, list[str]] = collections.defaultdict(list)
    for uid, field, idx, text in evidence:
        low = text.lower()
        toks = [(m.group(), m.start()) for m in re.finditer(r"[a-z0-9]+", low)]
        seen = set()
        i = 0
        while i < len(toks):
            step = 1
            for n in range(min(maxn, len(toks) - i), 0, -1):
                g = " ".join(w for w, _ in toks[i:i + n])
                ui = data_terms.get(g)
                if ui is None:
                    continue
                step = n
                if not neg.search(low[max(0, toks[i][1] - NEGATION_WINDOW_CHARS):toks[i][1]]) and ui not in seen:
                    seen.add(ui)
                    hits[ui][uid].append(f"{field}:{idx}")
                    term_counts[(ui, g)] += 1
                    if len(examples[ui]) < 3 and len(text) < 200 and text not in examples[ui]:
                        examples[ui].append(text)
                break
            i += step
    return hits, term_counts, examples


def curated_tag_trees(crosswalk: dict) -> dict[str, list[tuple[str, str]]]:
    """tag_id -> [(descriptor UI, tree number)] for curated condition/service tags."""
    out = collections.defaultdict(list)
    for t in crosswalk["serviceTags"]:
        for m in t["mesh"]:
            for tn in m["treeNumbers"]:
                if tn[0] == "C" or tn.startswith("F03"):
                    out[t["id"]].append((m["id"], tn))
    return out


def map_to_curated(ui: str, trees: list[str], tag_trees) -> list[str]:
    tags = []
    for tag_id, pairs in tag_trees.items():
        blocked = NO_DESCENDANT_ROLLUP.get(tag_id, set())
        valid = [t for t in trees if not any(t.startswith(x) for x in EXCLUDED_SUBTREES.get(tag_id, ()))]
        for desc_ui, tn in pairs:
            if desc_ui == ui or (desc_ui not in blocked and any(t == tn or t.startswith(tn + ".") for t in valid)):
                tags.append(tag_id)
                break
    return sorted(tags)


TAG_GROUP = {t.id: t.group for t in TAGS}


def category_specialties(tree: str) -> list[str]:
    """Longest-prefix lookup in CATEGORY_SPECIALTIES; benign growths go to general surgery, not oncology."""
    if tree.startswith("C04") and any(tree.startswith(x) for x in EXCLUDED_SUBTREES["cancer"]):
        return ["generalSurgery"]
    parts = tree.split(".")
    for k in range(len(parts), 0, -1):
        key = ".".join(parts[:k])
        if key in CATEGORY_SPECIALTIES:
            return CATEGORY_SPECIALTIES[key]
    return CATEGORY_SPECIALTIES.get(tree[:3], [])


def specialties_for(trees: list[str], available: set[str], curated: list[str] | None = None,
                    name: str | None = None) -> list[str]:
    if name in SPECIALTY_OVERRIDES:
        specs = set(SPECIALTY_OVERRIDES[name])
    elif curated:
        specs = {s for tag in curated for s in GROUP_SPECIALTIES.get(TAG_GROUP[tag], [])}
    else:
        # C23 (signs & symptoms) / C24 (occupational) map to general medicine; use them only when the
        # condition has no organ-specific branch (e.g. amblyopia is C11 eye *and* C23).
        specific = [t for t in trees if t[:3] not in ("C23", "C24")]
        specs = {s for t in (specific or trees) for s in category_specialties(t)}
    return sorted(s for s in specs if s in available)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "data" / "tags"))
    ap.add_argument("--evidence-cache")
    ap.add_argument("--mesh-xml", help="local MeSH desc2026 XML (downloaded here if missing)")
    ap.add_argument("--medlineplus-xml", help="local MedlinePlus health topics XML (downloaded here if missing)")
    ap.add_argument("--min-facilities", type=int, default=3)
    args = ap.parse_args()
    out = Path(args.out_dir)

    desc = load_mesh(args.mesh_xml)
    missing = set(SPECIALTY_OVERRIDES) - {d["name"] for d in desc.values()}
    if missing:
        raise SystemExit(f"SPECIALTY_OVERRIDES names not in MeSH: {missing}")
    topics = load_medlineplus(args.medlineplus_xml)
    index, aliases = build_term_index(desc, topics)
    print(f"MeSH condition descriptors: {len(desc):,}; MedlinePlus topics: {len(topics):,}; "
          f"searchable terms: {len(index):,}", file=sys.stderr)

    evidence = [r for r in load_evidence(args) if r[3]]
    hits, term_counts, examples = scan(evidence, index)

    crosswalk = json.loads((out / "taxonomy_crosswalk.json").read_text())
    tag_trees = curated_tag_trees(crosswalk)
    specialty_codes = {t["code"] for t in json.loads((out / "specialty_tags.json").read_text())["tags"]}

    conditions = []
    for ui, by_fac in hits.items():
        if len(by_fac) < args.min_facilities:
            continue
        d = desc[ui]
        conditions.append({
            "id": f"mesh:{ui}", "meshId": ui, "label": d["name"], "treeNumbers": d["trees"],
            "categories": sorted({t[:3] for t in d["trees"]}),
            "facilityCount": len(by_fac), "sentenceCount": sum(len(v) for v in by_fac.values()),
            "matchedTerms": [g for (u, g), _ in term_counts.most_common() if u == ui][:5],
            "curatedTags": (curated := map_to_curated(ui, d["trees"], tag_trees)),
            "fallbackSpecialties": [f"specialty:{s}" for s in specialties_for(d["trees"], specialty_codes, curated, d["name"])],
            "exampleEvidence": examples[ui],
        })
    conditions.sort(key=lambda c: (-c["facilityCount"], c["label"]))
    condition_ids = {c["meshId"] for c in conditions}
    uncovered = [c for c in conditions if not c["curatedTags"]]

    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "vocabulary": {"mesh": "NLM MeSH 2026, trees C (Diseases) and F03 (Mental Disorders)",
                       "medlineplus": "MedlinePlus health topics (English), also-called names"},
        "meshConditionDescriptors": len(desc),
        "conditionsFoundInData": len(hits),
        "conditionTags": len(conditions),
        "conditionTagsCoveredByCuratedTags": len(conditions) - len(uncovered),
        "minFacilities": args.min_facilities,
    }
    (out / "condition_tags.json").write_text(json.dumps({"meta": meta, "tags": conditions}, indent=2, ensure_ascii=False) + "\n")

    with open(out / "facility_condition_tags.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unique_id", "tag_id", "evidence_refs"])
        for ui in sorted(condition_ids):
            for uid, refs in sorted(hits[ui].items()):
                w.writerow([uid, f"mesh:{ui}", ";".join(refs)])

    # Alias table: MeSH / MedlinePlus names for every condition descriptor, plus curated tag names.
    cond_by_ui = {c["meshId"]: c for c in conditions}
    rows, seen = [], set()
    source_rank = {"colloquial_curated": 0, "medlineplus_title": 1, "medlineplus_also_called": 2, "mesh_preferred": 3, "mesh_entry": 4}
    for alias, source, ui in sorted(aliases, key=lambda a: source_rank[a[1]]):
        n = norm(alias)
        if not n or n in seen or n in BLOCKED_TERMS or index.get(n) != ui:
            continue  # keep one row per alias: the descriptor the search index resolves it to
        if source == "mesh_entry" and "," in alias:  # skip inverted index forms like "Cancer, Breast"
            continue
        seen.add(n)
        d = desc[ui]
        c = cond_by_ui.get(ui)
        curated = c["curatedTags"] if c else map_to_curated(ui, d["trees"], tag_trees)
        rows.append({
            "alias": alias, "alias_normalized": norm(alias), "source": source, "mesh_id": ui, "mesh_label": d["name"],
            "curated_tags": ";".join(curated),
            "condition_tag": f"mesh:{ui}" if c else "",
            "fallback_specialties": ";".join(f"specialty:{s}" for s in specialties_for(d["trees"], specialty_codes, curated, d["name"])),
            "facilities_with_condition_evidence": c["facilityCount"] if c else 0,
        })
    for t in TAGS:
        for alias, source in [(t.label, "tag_label"), (t.id.replace("-", " "), "tag_id")] + [(s, "tag_synonym") for s in t.synonyms]:
            if norm(alias) in seen:
                continue
            seen.add(norm(alias))
            specs = specialties_for([], specialty_codes, [t.id])
            rows.append({"alias": alias, "alias_normalized": norm(alias), "source": source, "mesh_id": "", "mesh_label": "",
                         "curated_tags": t.id, "condition_tag": "",
                         "fallback_specialties": ";".join(f"specialty:{x}" for x in specs),
                         "facilities_with_condition_evidence": 0})
    rows.sort(key=lambda r: (r["alias_normalized"], r["source"]))
    with open(out / "alias_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(json.dumps(meta, indent=2), file=sys.stderr)
    print(f"alias rows: {len(rows):,}", file=sys.stderr)
    print("Most frequent conditions with no curated tag:", file=sys.stderr)
    for c in uncovered[:25]:
        print(f"  {c['facilityCount']:5}  {c['label']}  ({', '.join(c['categories'])})", file=sys.stderr)


if __name__ == "__main__":
    main()
