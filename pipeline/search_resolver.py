"""Resolve free-text searches ("piles", "sugar", "slip disc", "MRI") to facilities.

1. Resolve the text to a vocabulary entry with ``data/tags/alias_table.csv``: exact alias,
   then the alias with filler words removed ("piles treatment near me" -> "piles"), then the
   longest alias contained in the text, then a close spelling match ("diabetis").
2. Look for facilities in evidence tiers, strongest first:
     service_evidence   a curated tag graded strong or mention by Prudence (TF-IDF)
     condition_mention  the MeSH condition is named in the facility's evidence sentences
     specialty          the facility lists a specialty that treats the condition
   ``exists_anywhere`` answers "does any facility in the dataset offer this?" using the first
   two tiers only (specialty alone is not evidence of a specific service).
3. If any facility has evidence (service, then condition tier), return the nearest ones, growing
   the radius 50 -> 100 -> 200 km. Evidence further away than that is still returned (nearest
   first, ``far: true``) together with the most comprehensive hospitals nearby. Only when no
   facility anywhere has evidence are specialty matches used (``match_level: specialty``).
   If nothing matches, or the text cannot be resolved, fall back to the most comprehensive
   hospitals nearby (``pipeline/sql/facility_comprehensiveness.sql``), clearly marked as a
   fallback rather than a match.

Facility locations and comprehensiveness scores come from the ``facility_comprehensiveness``
view, exported to CSV (unique_id, name, best_lat, best_lon, comprehensiveness, ...).

Usage:
  python3 pipeline/search_resolver.py "bawaseer"
  python3 pipeline/search_resolver.py "kidney failure" --lat 20.2961 --lon 85.8245 --facilities-csv facilities.csv
"""
from __future__ import annotations

import argparse
import collections
import csv
import difflib
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FILLER_WORDS = {
    "treatment", "treatments", "surgery", "surgeries", "operation", "hospital", "hospitals", "clinic", "clinics",
    "doctor", "doctors", "specialist", "specialists", "centre", "center", "near", "me", "nearby", "best", "for",
    "of", "the", "a", "in", "my", "test", "cure", "care", "problem", "problems", "management",
}
TIERS = ("service_evidence", "condition_mention", "specialty")
RADII_KM = (50, 100, 200)
csv.field_size_limit(sys.maxsize)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


@dataclass
class Resolution:
    query: str
    match_type: str  # exact | filler_removed | contained | spelling | none
    alias: str | None = None
    mesh_id: str | None = None
    mesh_label: str | None = None
    curated_tags: list[str] = field(default_factory=list)
    condition_tag: str | None = None
    fallback_specialties: list[str] = field(default_factory=list)


class SearchResolver:
    def __init__(self, tags_dir: Path = REPO_ROOT / "data" / "tags", facilities: list[dict] | None = None):
        with open(tags_dir / "alias_table.csv") as f:
            self.aliases = {r["alias_normalized"]: r for r in csv.DictReader(f)}
        self._max_alias_words = max(len(a.split()) for a in self.aliases)
        self.by_tag: dict[str, set[str]] = collections.defaultdict(set)
        scores = tags_dir / "facility_tag_scores.csv"
        if scores.exists():  # Prudence grades: strong / mention count as evidence, suggested does not
            with open(scores) as f:
                for r in csv.DictReader(f):
                    if r["class"] in ("strong", "mention"):
                        self.by_tag[r["tag_id"]].add(r["unique_id"])
        for name in ("facility_tags.csv", "facility_condition_tags.csv"):
            path = tags_dir / name
            if path.exists():
                with open(path) as f:
                    for r in csv.DictReader(f):
                        if r["tag_id"].startswith(("specialty:", "mesh:")) or not scores.exists():
                            self.by_tag[r["tag_id"]].add(r["unique_id"])
        self.facilities = {f["unique_id"]: f for f in (facilities or [])}

    # ── 1. text -> vocabulary ──────────────────────────────────────────
    def resolve(self, text: str) -> Resolution:
        q = norm(text)
        row, how = self.aliases.get(q), "exact"
        if row is None:
            stripped = " ".join(w for w in q.split() if w not in FILLER_WORDS)
            row, how = self.aliases.get(stripped), "filler_removed"
        if row is None:
            words = q.split()
            best = None
            for n in range(min(self._max_alias_words, len(words)), 0, -1):
                for i in range(len(words) - n + 1):
                    cand = " ".join(words[i:i + n])
                    if cand in self.aliases and cand not in FILLER_WORDS and len(cand) >= 3:
                        best = cand
                        break
                if best:
                    break
            row, how = (self.aliases[best], "contained") if best else (None, None)
        if row is None and len(q) >= 5:
            close = difflib.get_close_matches(q, self.aliases.keys(), n=1, cutoff=0.85)
            row, how = (self.aliases[close[0]], "spelling") if close else (None, None)
        if row is None:
            return Resolution(query=text, match_type="none")
        split = lambda s: [x for x in s.split(";") if x]  # noqa: E731
        return Resolution(query=text, match_type=how, alias=row["alias"], mesh_id=row["mesh_id"] or None,
                          mesh_label=row["mesh_label"] or None, curated_tags=split(row["curated_tags"]),
                          condition_tag=row["condition_tag"] or None,
                          fallback_specialties=split(row["fallback_specialties"]))

    # ── 2. vocabulary -> facilities by evidence tier ───────────────────
    def tiers(self, res: Resolution) -> dict[str, set[str]]:
        service = set().union(*(self.by_tag.get(t, set()) for t in res.curated_tags)) if res.curated_tags else set()
        condition = set(self.by_tag.get(res.condition_tag, set())) if res.condition_tag else set()
        specialty = set().union(*(self.by_tag.get(s, set()) for s in res.fallback_specialties)) if res.fallback_specialties else set()
        condition -= service
        specialty -= service | condition
        return {"service_evidence": service, "condition_mention": condition, "specialty": specialty}

    # ── 3. nearest results, with comprehensive-hospital fallback ───────
    def _nearby(self, ids, lat, lon, radius):
        out = []
        for uid in ids:
            f = self.facilities.get(uid)
            if f and f.get("best_lat") not in (None, ""):
                km = haversine_km(lat, lon, float(f["best_lat"]), float(f["best_lon"]))
                if km <= radius:
                    out.append((km, uid))
        return sorted(out)

    def _row(self, uid, km, **extra):
        return {"unique_id": uid, "name": self.facilities[uid].get("name"), "km": round(km, 1), **extra}

    def _comprehensive_nearby(self, lat, lon, limit):
        for radius in RADII_KM:
            hospitals = [(km, uid) for km, uid in self._nearby(self.facilities, lat, lon, radius)
                         if self.facilities[uid].get("comprehensiveness") not in (None, "")]
            if hospitals:
                hospitals.sort(key=lambda x: (-float(self.facilities[x[1]]["comprehensiveness"]), x[0]))
                return radius, [self._row(uid, km, comprehensiveness=round(float(self.facilities[uid]["comprehensiveness"]), 3))
                                for km, uid in hospitals[:limit]]
        return None, []

    def search(self, text: str, lat: float | None = None, lon: float | None = None, limit: int = 10) -> dict:
        res = self.resolve(text)
        tiers = self.tiers(res) if res.match_type != "none" else {t: set() for t in TIERS}
        evidence_tiers = [t for t in ("service_evidence", "condition_mention") if tiers[t]]
        result = {
            "resolution": asdict(res),
            "exists_anywhere": bool(evidence_tiers),
            "facilities_anywhere": {t: len(v) for t, v in tiers.items()},
            "match_level": None, "radius_km": None, "far": False, "results": [], "fallback": None,
        }
        if lat is None or lon is None or not self.facilities:
            return result
        # 1. Evidence exists somewhere: nearest facilities with evidence, strongest tier first.
        for tier in evidence_tiers:
            for radius in RADII_KM:
                near = self._nearby(tiers[tier], lat, lon, radius)
                if near:
                    result.update(match_level=tier, radius_km=radius, results=[self._row(u, km) for km, u in near[:limit]])
                    return result
        if evidence_tiers:  # only far away: still the answer, plus a comprehensive hospital nearby
            tier = evidence_tiers[0]
            far = self._nearby(tiers[tier], lat, lon, float("inf"))
            if far:
                result.update(match_level=tier, far=True, results=[self._row(u, km) for km, u in far[:limit]])
                radius, nearby = self._comprehensive_nearby(lat, lon, limit)
                result["fallback"] = {"reason": f"nearest facility with evidence is {far[0][0]:.0f} km away",
                                      "radius_km": radius, "results": nearby}
                return result
        # 2. No evidence anywhere: facilities with a relevant specialty.
        if tiers["specialty"]:
            for radius in RADII_KM:
                near = self._nearby(tiers["specialty"], lat, lon, radius)
                if near:
                    result.update(match_level="specialty", radius_km=radius, results=[self._row(u, km) for km, u in near[:limit]])
                    return result
        # 3. Nothing matched, or the text was not understood: most comprehensive hospitals nearby.
        radius, nearby = self._comprehensive_nearby(lat, lon, limit)
        if nearby:
            result["fallback"] = {"reason": "search text not recognised" if res.match_type == "none"
                                  else "no facility with evidence or a relevant specialty within reach",
                                  "radius_km": radius, "results": nearby}
        return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--facilities-csv", help="export of the facility_comprehensiveness view")
    args = ap.parse_args()
    facilities = None
    if args.facilities_csv:
        with open(args.facilities_csv) as f:
            facilities = list(csv.DictReader(f))
    print(json.dumps(SearchResolver(facilities=facilities).search(args.query, args.lat, args.lon), indent=2))


if __name__ == "__main__":
    main()
