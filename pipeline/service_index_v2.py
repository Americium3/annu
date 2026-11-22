"""Stage 1 (v2): high-recall facility x service candidates with an evidence status per sentence.

Output has the same columns as workspace.cardinal_virtues.serving_service_index, so the backend can switch to it
without other changes, plus `grade` (3 explicit and corroborated, 2 explicit single statement, 1 related only,
0 only negative/planned/unclear evidence) and `emergency_evidence` (emergency / 24x7 wording at the facility).

What v2 changes compared with the v1 tag column (all found by reading the data, see experiments/README_RESULTS.md):
  recall     every evidence field (procedure, capability, equipment, description, name), extra wordings per service
             (plurals, spellings, CTVS / cardio thoracic, trauma + noun, MRCP, ...), specialty codes that name the
             service itself count as explicit, related specialties are kept as grade 1
  precision  negation / plans / outsourcing / referral looked for before AND after the mention ("MRI (outsourced)"),
             "No. 1", "not required", "plans to increase" are not negations, "bypass" in a gastric / bariatric
             context is not cardiac surgery, dental / jaw fractures are not trauma care, a facility naming ITSELF is
             not "another institution", dentists and pharmacies only get services of their kind
It deliberately does NOT reuse workspace.golden_eval.label_rules (that would make the evaluation circular).

  python pipeline/service_index_v2.py --evidence experiments/data/evidence.parquet \
      --facilities experiments/data/facilities.parquet --out experiments/data/service_index_v2.parquet
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tag_dictionary import TAGS  # noqa: E402
from tag_matcher import TagMatcher  # noqa: E402

# ---------------------------------------------------------------- recall: extra explicit wordings per tag
EXTRA_EXPLICIT = {
    "kidney-dialysis": [r"\brenal replacement therap", r"\bhaemodiafiltration|\bhemodiafiltration", r"\bsled\b"],
    "c-section": [r"\bc[- ]?sections?\b", r"\bc(a)?esarian", r"\blower segment c", r"\boperative (vaginal )?deliver"],
    "nicu": [r"\bnicus\b", r"\bnewborn (icu|intensive)", r"\blevel[- ]?(ii|iii|2|3)\b[^.]{0,20}\b(neonat|nursery|newborn)",
             r"\bneonatal (care )?unit\b"],
    "cardiac-surgery": [r"\b(ctvs|cvts)\b", r"\bcardio[- ]thoracic\b", r"\bcardiothoracic (and|&) vascular", r"\bheart surger",
                        r"\bbypass surgeries\b", r"\bcoronary artery bypass\b", r"\bheart transplant"],
    "mri": [r"\bmrcp\b", r"\bmagnetic resonance cholangio", r"\b\d(\.\d)?\s?-?\s?t(esla)?\b[^.]{0,15}\bmri\b"],
    "burns": [r"\bburns? (icu|ot|theat\w*|surgery|injur\w*|patients?|management)\b", r"\bplastic (and|&) burns?\b",
              r"\bburns? (and|&) plastic\b"],
    "fracture-trauma": [r"\btrauma\s*(care|centre|center|unit|icu|team|facility|services?|surgery|ward|management|cases)\b",
                        r"\bemergency\s*(&|and|/)\s*trauma\b", r"\btrauma\s*(&|and|/)\s*(emergency|critical)", r"\bcasualty\b",
                        r"\baccident (and|&) emergency\b", r"\broad (traffic )?accident"],
    "cataract": [r"\bphaco\w*", r"\bmics\b", r"\bsics\b", r"\bintraocular lens\b", r"\biol\b"],
    "chemotherapy": [r"\bchemo\b", r"\bday[- ]?care chemo", r"\bmedical oncology\b", r"\bradiotherapy\b|\bradiation oncology\b"],
}
# specialty codes (camelCase split, lower) that name the service itself -> explicit; related -> grade 1
SPECIALTY_EXPLICIT = {
    "cardiac-surgery": r"^(cardiac surgery|cardiothoracic surgery|cardio thoracic surgery|cardiothoracic and vascular surgery)$",
    "burns": r"^(burn and trauma plastic surgery|burns? management|burn surgery)$",
    "nicu": r"^(neonatal intensive care)$",
    "fracture-trauma": r"^(trauma surgery|orthopedic trauma and fracture surgery|polytrauma)$",
}
SPECIALTY_RELATED = {
    "kidney-dialysis": r"nephrolog", "c-section": r"obstetric|gyn(a)?ecolog|maternity", "nicu": r"neonat|perinatal",
    "cardiac-surgery": r"cardiolog|cardiac", "mri": r"radiolog|imaging", "burns": r"plastic|reconstruct",
    "fracture-trauma": r"orthop(a)?edic|emergency medicine|critical care", "cataract": r"ophthalmolog",
    "chemotherapy": r"oncolog|cancer|hemato|haemato",
}
# ---------------------------------------------------------------- precision guards (per tag)
SENSE_EXCLUDE = {
    "cardiac-surgery": r"(gastric|bariatric|roux|metabolic|weight|neuro\w*|ileal|jejunal|road)[^.]{0,30}bypass|bypass[^.]{0,30}(gastric|bariatric|road)",
    "fracture-trauma": r"\b(teeth|tooth|dental|maxill\w*|mandib\w*|jaw|facial|zygom\w*|nasal|orbital)\b[^.]{0,30}fractur|fractur\w*[^.]{0,30}\b(teeth|tooth|dental|jaw)\b|psycholog\w* trauma|trauma[- ]informed|emotional trauma",
    "burns": r"\b(burn wound care|minor burns?|razor burn|sun ?burn)\b|\b(no|without|avoid|risk of)\b[^.]{0,20}\bburns?\b",
    "nicu": r"\b(embryo|ivf|co2|bacteri\w*|laborator\w*)\b[^.]{0,20}incubat",
}
NEGATION_AFTER = re.compile(r"(?i)\boutsourc\w*|\(outsource|\breferr(ed|al)\b|\brefers?\b|\btie[- ]?up\b|\bcoming soon\b|\bupcoming\b"
                            r"|\bunder construction\b|\bplans? to (start|open|set up|establish|launch|introduce|add)\b"
                            r"|\bnot (available|functional|operational)\b|\bproposed\b")
NOT_A_NEGATION = re.compile(r"(?i)\bno\.?\s*1\b|\bnot required\b|\bnon[- ]?stop\b|\bplans? to (increase|expand|upgrade|scale)\b"
                            r"|\bwithout (any )?(pain|stitch|injection|cut|scar)")
OTHER_INSTITUTION = re.compile(r"\b(at|of|in|from|with|via|through)\s+(the\s+)?([A-Z][\w.&'-]+(?:\s+[A-Z][\w.&'-]+){0,5})\s+"
                               r"(Hospital|Institute|Medical College|Centre|Center|Clinic)\b")
EMERGENCY = re.compile(r"(?i)24\s*[x/×*]\s*7|24[- ]?(hours?|hrs?)|round[- ]the[- ]clock|\bemergenc|\bcasualty\b|\btrauma\b")
# facility names that announce one specialty ("... Eye Hospital", "Netralaya", "Dental Clinic"): a claim for a service
# of another kind is more likely a merged record (the brief: "some records merge two hospitals") -> down-weighted
NAME_SPECIALTY = {
    "Eyes": r"\b(eye|eyes|netralaya|nethralaya|netra|ophthalm\w*|vision|lasik|retina)\b",
    "Dental": r"\b(dental|dentist\w*|teeth|tooth|smile|orthodont\w*|implant clinic)\b",
    "Women's health & fertility": r"\b(ivf|fertility|test tube)\b",
    "Skin, hair & cosmetic": r"\b(skin|derma\w*|hair|cosmetolog\w*|aesthetic)\b",
    "Cancer": r"\b(cancer|onco\w*)\b",
    "Mental health": r"\b(psychiatr\w*|de-?addiction|mental)\b",
    "Bones, joints & spine": r"\b(ortho\w*|bone|joint|spine)\b(?!.*\b(multi|general|super)\b)",
}
# "... Cancer & General Hospital", "Multispeciality", "Medical College": a general facility, not a single-specialty one
GENERAL_NAME = re.compile(r"(?i)\b(general|multi[- ]?speciality|multi[- ]?specialty|multispeciality|multispecialty|super[- ]?speciality"
                          r"|super[- ]?specialty|medical college|institute of medical|district hospital|civil hospital)\b")
ALWAYS_COMPATIBLE_GROUPS = {"Imaging & diagnostics", "Emergency & critical care"}
NAME_MISMATCH_FACTOR = 0.6
# services that need an inpatient hospital; a clinic claiming them is down-weighted, not excluded
INPATIENT_MAJOR = {"cardiac-surgery", "neurosurgery", "kidney-transplant", "liver-transplant", "bone-marrow-transplant",
                   "burns", "nicu", "picu", "icu"}
CLINIC_INPATIENT_FACTOR = 0.7
WEAK_SOURCE_FACTOR = 0.75     # explicit wording only in specialty / name / description, not in procedure/capability/equipment
DENTAL_CONTEXT = re.compile(r"(?i)\bdent(al|ist\w*|istry)\b|\bteeth\b|\btooth\b|\bendodont|\borthodont")
DENTAL_TAGS = {"root-canal", "dental-implants", "orthodontics", "dentures", "tooth-extraction", "gum-disease"}
GENERIC = {"hospital", "hospitals", "clinic", "centre", "center", "medical", "health", "care", "the", "and", "of", "pvt", "ltd",
           "multispeciality", "multispecialty", "speciality", "specialty", "super", "nursing", "home", "institute", "research"}


def _name_tokens(name: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", (name or "").lower()) if w not in GENERIC}


def _camel(s: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s or "").lower().strip()


def _status(text: str, own_name: set[str], negated_by_rule: bool) -> str:
    if NOT_A_NEGATION.search(text):
        negated_by_rule = False
    if negated_by_rule or NEGATION_AFTER.search(text):
        return "negated_or_planned"
    m = OTHER_INSTITUTION.search(text)
    if m and not (_name_tokens(m.group(3)) & own_name):
        return "attributed_elsewhere"
    return "usable"


def build(evidence: pd.DataFrame, facilities: pd.DataFrame, tags=TAGS) -> pd.DataFrame:
    """evidence: unique_id, field, items (JSON list of {item_idx, text}); facilities: unique_id, name, facility_category."""
    matcher = TagMatcher(tags)
    tag_ids = {t.id for t in tags}
    extra = {t: re.compile("|".join(p), re.I) for t, p in EXTRA_EXPLICIT.items() if t in tag_ids}
    sense = {t: re.compile(p, re.I) for t, p in SENSE_EXCLUDE.items()}
    spec_exp = {t: re.compile(p) for t, p in SPECIALTY_EXPLICIT.items()}
    spec_rel = {t: re.compile(p) for t, p in SPECIALTY_RELATED.items()}
    fac = facilities.set_index("unique_id")
    group_of = {t.id: t.group for t in tags}
    name_rx = {g: re.compile(p, re.I) for g, p in NAME_SPECIALTY.items()}
    by_fac = defaultdict(list)
    for r in evidence.itertuples():
        for it in json.loads(r.items):
            by_fac[r.unique_id].append((r.field, int(it["item_idx"]), it["text"] or ""))
    rows = []
    for uid, items in by_fac.items():
        if uid not in fac.index:
            continue
        name = fac.at[uid, "name"] if isinstance(fac.at[uid, "name"], str) else ""
        category = str(fac.at[uid, "facility_category"] or "")
        own = _name_tokens(name)
        name_groups = set() if GENERAL_NAME.search(name) else {g for g, rx in name_rx.items() if rx.search(name)}
        found = defaultdict(list)          # tag -> [(field, pos, text, status)]
        texts = [(f, p, t) for f, p, t in items if f in ("procedure", "capability", "equipment")]
        for f, p, t in items:
            if f == "description":         # split the description into sentences, keep the field for citations
                texts += [("description", p, s.strip()) for s in re.split(r"(?<=[.;!?])\s+", t) if s.strip()]
        texts.append(("name", 0, name))
        emergency_hits = [t for f, p, t in texts if EMERGENCY.search(t)]
        for f, p, t in texts:
            if not t:
                continue
            matched, negated = matcher.match(t)
            hits = set(matched) | {tg for tg, rx in extra.items() if rx.search(t)}
            dental_sentence = bool(DENTAL_CONTEXT.search(t))
            for tg in hits:
                if tg in sense and sense[tg].search(t):
                    continue
                if dental_sentence and tg not in DENTAL_TAGS:      # "emergency dentistry" is not emergency care
                    continue
                found[tg].append((f, p, t, _status(t, own, False)))
            for tg in set(negated) - hits:
                found[tg].append((f, p, t, _status(t, own, True)))
        for f, p, t in items:
            if f != "specialty":
                continue
            s = _camel(t)
            for tg, rx in spec_exp.items():
                if rx.search(s):
                    found[tg].append(("specialty", p, t, "usable"))
            for tg, rx in spec_rel.items():
                if rx.search(s) and not any(e[0] == "specialty" and e[1] == p for e in found[tg]):
                    found[tg].append(("specialty", p, t, "related"))
        for tg, ev in found.items():
            if category == "dentist" and tg not in DENTAL_TAGS:
                continue
            if category == "pharmacy":
                continue
            usable = [e for e in ev if e[3] == "usable"]
            core = [e for e in usable if e[0] in ("procedure", "capability", "equipment", "specialty", "name")]
            fields = {e[0] for e in core}
            if core:
                grade = 3 if (len(core) >= 2 or len(fields) >= 2) else 2
            elif usable:                    # explicit only in the description
                grade = 2
            elif any(e[3] == "related" for e in ev):
                grade = 1
            else:
                grade = 0
            n_eq = sum(e[0] == "equipment" for e in usable)
            strong = [e for e in usable if e[0] in ("procedure", "capability", "equipment")]
            source_factor = 1.0 if strong or not usable else WEAK_SOURCE_FACTOR
            plaus = 1.0
            if name_groups and group_of.get(tg) not in name_groups | ALWAYS_COMPATIBLE_GROUPS:
                plaus *= NAME_MISMATCH_FACTOR
            if category == "clinic" and tg in INPATIENT_MAJOR:
                plaus *= CLINIC_INPATIENT_FACTOR
            n_else = sum(e[3] == "attributed_elsewhere" for e in ev)
            prio = {"usable": 0, "related": 1, "attributed_elsewhere": 2, "negated_or_planned": 3}
            ordered = sorted(ev, key=lambda e: (prio[e[3]], {"procedure": 0, "capability": 1, "equipment": 2, "name": 3,
                                                             "specialty": 4, "description": 5}[e[0]], e[1]))
            rows.append({
                "unique_id": uid, "tag_id": tg, "grade": grade,
                "eligibility": "formal" if grade >= 2 else ("related" if grade == 1 else "review_blocked"),
                "reason_codes": [] if grade >= 2 else (["related_specialty_only"] if grade == 1 else ["only_negative_planned_or_other_institution"]),
                "evidence_tier": (1 if len(fields - {"name"}) >= 2 else 2 if len(core) >= 2 else 3) if grade >= 2 else 9,
                "n_explicit_usable": len(usable), "n_explicit_elsewhere": n_else, "n_time_bound": 0,
                "n_equipment_usable": n_eq, "n_explicit_fields": len(fields), "n_cited": len(ev),
                "only_equipment": bool(usable) and n_eq == len(usable),
                "emergency_evidence": len(emergency_hits),
                "source_factor": source_factor, "plausibility": plaus,
                "evidence": [{"field": e[0], "pos": e[1], "text": e[2][:400],
                              "evidence_status": "usable" if e[3] == "usable" else e[3], "kind": e[3]} for e in ordered[:8]],
            })
    out = pd.DataFrame(rows)
    emerg = set(out.loc[(out.tag_id == "emergency-24x7") & (out.grade >= 2), "unique_id"])
    out["lists_emergency_24x7"] = out.unique_id.isin(emerg)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--facilities", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = build(pd.read_parquet(a.evidence), pd.read_parquet(a.facilities))
    out.to_parquet(a.out)
    print(out.groupby("eligibility").size().to_string())


if __name__ == "__main__":
    main()
