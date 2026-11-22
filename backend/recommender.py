"""Service-first recommender (port of facilities_qc/03_recommender_lib.py, section F) + mapping to web/src/types.ts.

Flow: service text → tag → formal eligibility + location → widening radius → rank score =
evidence strength × closeness. Evidence strength blends the cross-encoder's text match (live default) with
proof strength; closeness depends on how far people travel for this kind of care. Facilities with weak proof
are always listed after those with solid proof. Rules-only ranking (proof × closeness) is an explicit opt-in.
"""
from __future__ import annotations

import difflib
import re
import time
import uuid
from urllib.parse import urlparse

import numpy as np
import pandas as pd

import config
from data_store import Snapshot, haversine_km
from cross_encoder import CrossEncoderScorer, CrossEncoderError
from evidence_support import supported_items


class ServiceNotFound(Exception):
    def __init__(self, message: str, suggestions: list[str]):
        super().__init__(message)
        self.suggestions = suggestions


class LocationNotFound(Exception):
    def __init__(self, message: str, suggestions: list[str]):
        super().__init__(message)
        self.suggestions = suggestions


def _s(v) -> str:
    """String field or '' (pandas gives NaN for missing values)."""
    return v if isinstance(v, str) else ""


def _clean(o):
    """Replace NaN / inf (not valid JSON) with None, recursively."""
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return _clean(float(o))
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def travel_km(tag: str) -> float:
    """How far people reasonably travel for this kind of care (km); closeness halves at this distance."""
    return float(config.TRAVEL_KM_BY_TAG.get(tag, config.TRAVEL_KM_DEFAULT))


def closeness(distance_km, travel: float):
    """1 next door, 0.5 at the travel distance, falling quickly after it."""
    d = np.asarray(distance_km, dtype=float)
    return 1.0 / (1.0 + (d / travel) ** 2)


def proof_strength(df: pd.DataFrame) -> pd.Series:
    """0-1: how strongly the evidence says this facility offers the service, at a location we can trust."""
    tier = df["evidence_tier"].map(config.PROOF_BY_TIER).fillna(0.0)
    equipment = np.where(df["only_equipment"].astype(bool), config.PROOF_ONLY_EQUIPMENT, 1.0)
    other = np.where(df["n_explicit_elsewhere"].fillna(0) > 0, config.PROOF_MENTIONS_OTHER, 1.0)
    location = df["location_tier"].astype(str).map(config.PROOF_BY_LOCATION).fillna(0.7)
    return tier * equipment * other * location


def rank_candidates(ok: pd.DataFrame, tag: str, text_match: pd.Series | None = None) -> pd.DataFrame:
    """Order eligible facilities: solid proof before weak proof; within each, rank score = evidence x closeness
    (ties: nearer first, then id). Evidence is proof strength alone, or blended with the cross-encoder's
    text match when one is given."""
    out = ok.copy()
    out["proof"] = proof_strength(out)
    out["closeness"] = closeness(out["distance_km"].to_numpy(), travel_km(tag))
    if text_match is None:
        out["evidence_strength"] = out["proof"]
    else:
        w = config.RERANK_WEIGHTS
        out["text_match"] = text_match.reindex(out.index).astype(float)
        out["evidence_strength"] = w["text"] * out["text_match"] + w["proof"] * out["proof"]
    out["rank_score"] = out["evidence_strength"] * out["closeness"]
    out["solid_proof"] = (out["proof"] >= config.PROOF_SOLID_MIN) & ~out["only_equipment"].astype(bool)
    return out.sort_values(["solid_proof", "rank_score", "distance_km", "n_explicit_usable", "unique_id"],
                           ascending=[False, False, True, False, True])


_PHONE_SPLIT = re.compile(r"[,;/|]| or |\n")


def contact_phone(raw) -> str | None:
    """First dialable number in the record (records may list several), as digits with an optional leading +."""
    if not isinstance(raw, str):
        return None
    for part in _PHONE_SPLIT.split(raw):
        digits = re.sub(r"[^\d+]", "", part.strip())
        digits = digits[0] + digits[1:].replace("+", "") if digits else ""
        if 8 <= len(digits.lstrip("+")) <= 15:
            return digits
    return None


def contact_website(raw) -> str | None:
    """The record's website as an absolute https URL, or None."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    url = raw.strip().split()[0]
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")
    return url if "." in url.split("://", 1)[1] else None


class Recommender:
    def __init__(self, snap: Snapshot, scorer=None, ranking_method=None):
        self.snap = snap
        self.ranking_method = ranking_method or config.RANKING_METHOD
        if self.ranking_method not in {"cross_encoder", "rules"}:
            raise ValueError("CAREPATH_RANKING_METHOD must be cross_encoder or rules")
        self.ranking_version = ("cross-encoder-x-closeness-v5-claim-guard" if self.ranking_method == "cross_encoder"
                                else "proof-x-closeness-v5-claim-guard")
        self.scorer = scorer if scorer is not None else CrossEncoderScorer(
            config.CROSS_ENCODER_MODEL, config.CROSS_ENCODER_REVISION, config.CROSS_ENCODER_DEVICE,
            config.CROSS_ENCODER_BATCH_SIZE, config.CROSS_ENCODER_MAX_LENGTH,
        )
        self.tags = snap.tags.set_index("tag_id")
        # service phrases → tag ids
        self.phrases: dict[str, set[str]] = {}
        for r in snap.tags.itertuples():
            for ph in [r.tag_id.replace("-", " "), r.label, *r.synonyms, *config.SERVICE_INPUT_SYNONYMS.get(r.tag_id, [])]:
                self.phrases.setdefault(_norm(ph), set()).add(r.tag_id)
        # facilities joined once to the index
        fac = snap.facilities.set_index("unique_id")
        fac["rec_lat"] = fac["loc_lat"].fillna(fac["latitude"])
        fac["rec_lon"] = fac["loc_lon"].fillna(fac["longitude"])
        self.fac = fac
        self.index = snap.index.join(fac, on="unique_id", rsuffix="_fac")
        self.by_tag = {t: g for t, g in self.index.groupby("tag_id")}
        # location reference: districts from precise PINs, cities from verified facility points
        pins = snap.pins.copy()
        pins["pincode"] = pins["pincode"].astype(str)
        self.pins = pins.set_index("pincode")
        prec = pins[pins["is_precise"] & pins["lat"].notna()]
        rows = [(d.upper(), s.upper(), r.lat, r.lon) for r in prec.itertuples() if len(r.states) == 1
                for d in r.districts for s in r.states]
        dist = pd.DataFrame(rows, columns=["district", "state", "lat", "lon"])
        self.districts = (dist.groupby(["district", "state"])
                              .agg(lat=("lat", "median"), lon=("lon", "median"), n_pins=("lat", "size")).reset_index())
        pts = fac[fac["location_tier"] == "point_verified"].copy()
        pts["city"] = pts["address_city"].fillna(pts["city_raw"]).str.upper().str.strip()
        pts["state_u"] = pts["state"].fillna("").str.upper().str.strip()
        self.cities = (pts.groupby(["city", "state_u"])
                          .agg(lat=("loc_lat", "median"), lon=("loc_lon", "median"), n=("loc_lat", "size")).reset_index())
        self.states = set(self.districts["state"]) | set(self.cities["state_u"])

    def warmup(self):
        if self.ranking_method == "cross_encoder":
            self.scorer.warmup()

    def ranking_info(self):
        return {"method": self.ranking_method, "version": self.ranking_version,
                "formula": "evidence x closeness; closeness = 1 / (1 + (km / travel_km)^2)",
                **({"scorer": self.scorer.info(), "weights": config.RERANK_WEIGHTS}
                   if self.ranking_method == "cross_encoder" else {})}

    def _cross_encoder_order(self, within, tag, label):
        """Text match for already-formal candidates, then the shared ranking. No CE threshold certifies capability."""
        within = within.copy()
        if within.empty:
            return rank_candidates(within, tag)
        query = " ".join(dict.fromkeys([label, *self.tags.loc[tag, "synonyms"], *config.SERVICE_INPUT_SYNONYMS.get(tag, [])]))
        selected, texts = {}, []
        for idx, row in within.iterrows():
            # Keep evidence selection independent of model score and stable across requests.
            usable = [e for e in row["evidence"] if e.get("evidence_status") == "usable"
                      and isinstance(e.get("text"), str) and e["text"].strip()]
            usable.sort(key=lambda e: (0 if e.get("field") in {"procedure", "capability", "description"} else 1,
                                       str(e.get("field", "")), str(e.get("pos", e.get("item_idx", ""))), e["text"]))
            # Repeated identical text must not consume the evidence cap.
            unique = {}
            for item in usable:
                unique.setdefault(item["text"], item)
            usable = list(unique.values())[:config.CROSS_ENCODER_MAX_EVIDENCE]
            if not usable:
                raise CrossEncoderError("Formal candidate has no usable evidence text; rebuild the serving index before reranking.")
            selected[idx] = (len(texts), usable)
            texts.extend(e["text"] for e in usable)
        scores = self.scorer.score(query, texts)
        for idx, (start, evidence) in selected.items():
            local = scores[start:start + len(evidence)]
            best = max(range(len(local)), key=local.__getitem__)
            within.at[idx, "ce_text_score"] = float(local[best])
            best_ev = evidence[best]
            within.at[idx, "ce_evidence_ref"] = f"{best_ev.get('field')}:{best_ev.get('pos', best_ev.get('item_idx', ''))}"
            within.at[idx, "ce_best_quote"] = best_ev["text"]
            within.at[idx, "ce_item_count"] = len(evidence)
        return rank_candidates(within, tag, text_match=within["ce_text_score"])

    # ------------------------------------------------------------------ catalog / suggestions
    def services(self) -> list[dict]:
        out = [{"id": r.tag_id, "name": r.label, "synonyms": list(r.synonyms) + config.SERVICE_INPUT_SYNONYMS.get(r.tag_id, [])[:2],
                "category": r.group_name, "facilityCount": int(r.facility_count)}
               for r in self.snap.tags.sort_values("facility_count", ascending=False).itertuples()]
        return out

    def location_suggestions(self, q: str, limit: int = 8) -> list[dict]:
        qn = q.strip().upper()
        if not qn:
            return []
        name = qn.split(",")[0].strip()
        out = []
        d = self.districts[self.districts["district"].str.startswith(name)].sort_values("n_pins", ascending=False)
        for r in d.head(limit).itertuples():
            out.append({"id": f"district:{r.district}|{r.state}", "name": r.district.title(), "region": r.state.title(),
                        "latitude": float(r.lat), "longitude": float(r.lon), "confidence": "high", "kind": "district"})
        c = self.cities[self.cities["city"].str.startswith(name) & (self.cities["n"] >= 3)].sort_values("n", ascending=False)
        seen = {(o["name"].upper(), o["region"].upper()) for o in out}
        for r in c.itertuples():
            if (r.city, r.state_u) in seen or len(out) >= limit or not r.state_u:
                continue
            out.append({"id": f"city:{r.city}|{r.state_u}", "name": r.city.title(), "region": r.state_u.title(),
                        "latitude": float(r.lat), "longitude": float(r.lon), "confidence": "medium", "kind": "city"})
        if re.fullmatch(r"\d{3,6}", name.replace(" ", "")):
            for pin in [p for p in self.pins.index if p.startswith(name.replace(" ", ""))][:limit]:
                r = self.pins.loc[pin]
                if pd.notna(r["lat"]):
                    out.append({"id": f"pin:{pin}", "name": pin, "region": ", ".join(s.title() for s in r["states"]),
                                "latitude": float(r["lat"]), "longitude": float(r["lon"]),
                                "confidence": "high" if r["is_precise"] else "low", "kind": "pincode"})
        return out[:limit]

    # ------------------------------------------------------------------ step 1: service → tag
    def match_service(self, text: str) -> tuple[str, str, list[str]]:
        t = _norm(text)
        if not t:
            raise ServiceNotFound("Enter a service.", [])
        if t in self.phrases and len(self.phrases[t]) == 1:
            return next(iter(self.phrases[t])), "exact", []
        contained = sorted([(len(ph), ids) for ph, ids in self.phrases.items()
                            if len(ph) >= 3 and re.search(rf"\b{re.escape(ph)}\b", t)], key=lambda x: -x[0])
        if contained and len(contained[0][1]) == 1:
            return next(iter(contained[0][1])), "phrase_in_input", []
        toks = set(t.split())
        inside = set().union(*[ids for ph, ids in self.phrases.items() if toks <= set(ph.split())] or [set()])
        if len(inside) == 1:
            return next(iter(inside)), "input_in_phrase", []
        labels = lambda ids: [self.tags.loc[i, "label"] for i in sorted(ids)]
        if len(inside) > 1:
            raise ServiceNotFound(f"'{text}' matches several services. Please pick one.", labels(inside))
        close = difflib.get_close_matches(t, list(self.phrases), n=5, cutoff=0.6)
        sugg = set().union(*[self.phrases[c] for c in close] or [set()])
        raise ServiceNotFound(f"'{text}' is not in the list of {len(self.tags)} services.", labels(sugg))

    # ------------------------------------------------------------------ location
    def resolve_location(self, text: str, coordinates: dict | None) -> dict:
        if coordinates and coordinates.get("latitude") is not None:
            return {"type": "coordinates", "lat": float(coordinates["latitude"]), "lon": float(coordinates["longitude"]),
                    "precision": "point", "name": "Current location", "district": "", "state": "",
                    "note": "user-supplied coordinates", "confidence": "high", "ambiguous": []}
        raw = (text or "").strip()
        m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", raw)
        if m:
            return {"type": "coordinates", "lat": float(m.group(1)), "lon": float(m.group(2)), "precision": "point",
                    "name": raw, "district": "", "state": "", "note": "user-supplied coordinates", "confidence": "high",
                    "ambiguous": []}
        pin = re.sub(r"\D", "", raw) if re.fullmatch(r"[\d\s]{6,7}", raw) else ""
        if pin:
            if pin not in self.pins.index or pd.isna(self.pins.loc[pin, "lat"]):
                raise LocationNotFound(f"PIN {pin} is not in the India Post directory or has no coordinates.", [])
            r = self.pins.loc[pin]
            note = f"centre of PIN {pin}" + ("" if r["is_precise"] else " (PIN area is spread out, distances are rough)")
            return {"type": "pincode", "lat": float(r["lat"]), "lon": float(r["lon"]), "precision": "pin_centre",
                    "name": pin, "district": ", ".join(d.title() for d in r["districts"]),
                    "state": ", ".join(s.title() for s in r["states"]), "note": note,
                    "confidence": "high" if r["is_precise"] else "low", "ambiguous": []}
        parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
        if not parts:
            raise LocationNotFound("Enter a city, district, PIN code or coordinates.", [])
        name = re.sub(r"\s+(DISTRICT|DIST\.?|CITY)$", "", parts[0])
        state = parts[-1] if len(parts) > 1 and parts[-1] in self.states else None
        d = self.districts[self.districts["district"] == name]
        if not len(d):   # "Leh" → "LEH LADAKH": accept a unique district starting with the input
            pre = self.districts[self.districts["district"].str.startswith(name + " ")]
            if pre["district"].nunique() == 1:
                d = pre
        if state:
            d = d[d["state"] == state]
        if len(d):
            d = d.sort_values("n_pins", ascending=False)
            top = d.iloc[0]
            amb = [f"{r.district.title()}, {r.state.title()}" for r in d.itertuples()] if len(d) > 1 else []
            note = f"centre of district {top.district.title()}, {top.state.title()} (from {int(top.n_pins)} PIN centres)"
            if amb:
                note += "; district name exists in several states, assumed the one with most PINs"
            return {"type": "district", "lat": float(top.lat), "lon": float(top.lon), "precision": "district_centre",
                    "name": top.district.title(), "district": top.district.title(), "state": top.state.title(),
                    "note": note, "confidence": "medium" if amb else "high", "ambiguous": amb}
        c = self.cities[self.cities["city"] == name]
        if state:
            c = c[c["state_u"] == state]
        if len(c):
            top = c.sort_values("n", ascending=False).iloc[0]
            return {"type": "city", "lat": float(top.lat), "lon": float(top.lon), "precision": "city_centre",
                    "name": top.city.title(), "district": top.city.title(), "state": top.state_u.title(),
                    "note": f"approximate centre of {top.city.title()} from {int(top.n)} facility addresses",
                    "confidence": "medium", "ambiguous": []}
        sugg = [f"{s['name']}, {s['region']}" for s in self.location_suggestions(name[:4], 5)]
        raise LocationNotFound(f"Could not find '{raw}'. Try a district, city, 6-digit PIN or 'lat, lon'.", sugg)

    # ------------------------------------------------------------------ steps 2–4
    def recommend(self, service_text: str, location_text: str, coordinates: dict | None = None) -> dict:
        """The only inputs are the service and the location (text, or coordinates from "Use my location").
        Radius, result count and ordering are system decisions."""
        limit = config.RESULT_LIMIT
        t0 = time.time()
        tag, how, _ = self.match_service(service_text)
        label = self.tags.loc[tag, "label"]
        loc = self.resolve_location(location_text, coordinates)
        prov = self.by_tag.get(tag, self.index.iloc[0:0]).copy()
        n_dataset = len(prov)
        n_dataset_ok = int((prov["eligibility"] == "formal").sum())

        prov["distance_km"] = haversine_km(loc["lat"], loc["lon"], prov["rec_lat"].to_numpy(float), prov["rec_lon"].to_numpy(float))
        prov["band_idx"] = np.searchsorted(config.DISTANCE_BANDS_KM[1:], prov["distance_km"].to_numpy(), side="right")
        prov["point_first"] = (~prov["location_tier"].astype(str).str.startswith("point")).astype(int)
        prov["attribution"] = (prov["n_explicit_elsewhere"] > 0).astype(int)
        prov["km_point"] = np.where(prov["point_first"] == 0, prov["distance_km"], np.inf)
        ok = prov[prov["eligibility"] == "formal"].copy()
        claim_exclusions = []
        filtered_statements = []
        if config.CLAIM_GUARD_POLICY != "off":
            for idx, candidate in ok.iterrows():
                kept, excluded = supported_items(candidate["evidence"], tag, config.CLAIM_GUARD_POLICY)
                if not kept:
                    claim_exclusions.append({"unique_id": candidate["unique_id"],
                        "reasons": sorted({e["guard_status"] for e in excluded}) or ["no_usable_evidence"]})
                    ok = ok.drop(index=idx)
                else:
                    ok.at[idx, "evidence"] = kept
                    if excluded:
                        # Upstream proof counts/tier must not survive removal of their supporting text.
                        # Conservative downgrade pending a rebuild of the serving evidence tiers.
                        fields = [e.get("field") for e in kept]
                        ok.at[idx, "n_explicit_usable"] = sum(f in {"procedure", "capability", "description"} for f in fields)
                        ok.at[idx, "only_equipment"] = all(f == "equipment" for f in fields)
                        ok.at[idx, "evidence_tier"] = max(3, int(candidate["evidence_tier"]))
                        filtered_statements.append({"unique_id": candidate["unique_id"],
                            "removed": len(excluded), "reasons": sorted({e["guard_status"] for e in excluded}),
                            "proof_downgraded": True})

        n_dataset_ok = len(ok)
        # Candidate pool: at least twice the travel distance for this kind of care, widened (25 -> 50 -> 100 -> 200 km)
        # until a provider is found. Inside it, distance is a ranking factor, not a cut-off.
        steps = list(config.RADIUS_STEPS_KM)
        travel = travel_km(tag)
        first_step = next((r for r in steps if r >= 2 * travel), steps[-1])
        candidates = [r for r in steps if r >= first_step]
        radius = next((r for r in candidates if (ok["distance_km"] <= r).any()), steps[-1])
        pool = ok[ok["distance_km"] <= radius]
        within = (self._cross_encoder_order(pool, tag, label) if self.ranking_method == "cross_encoder"
                  else rank_candidates(pool, tag))
        blocked = prov[(prov["eligibility"] == "review_blocked") & (prov["distance_km"] <= radius)]

        picked = within.head(limit).copy()
        picked["lane"] = ["A" if i < config.K_MAIN else "C" for i in range(len(picked))]

        results = [self._facility(r, i + 1, label, loc, radius) for i, (_, r) in enumerate(picked.iterrows())]

        warnings = [f"{n_dataset} facilities in the dataset list {label} ({n_dataset_ok} with usable evidence and "
                    f"location); {len(within)} within {radius:g} km; {len(blocked)} more within {radius:g} km are "
                    f"review-blocked (identity, location or evidence problems) and not shown."]
        if radius != first_step:
            warnings.append(f"No listed provider within {first_step:g} km; search widened to {radius:g} km.")
        if not len(within):
            near = ok["distance_km"].min() if len(ok) else None
            warnings.insert(0, f"No facility within {radius:g} km lists {label} with usable evidence."
                            + (f" The nearest one in the dataset is about {near:.0f} km away." if near is not None else "")
                            + " This does not mean the service is unavailable in the area.")
        if claim_exclusions:
            warnings.append(f"{len(claim_exclusions)} formal record(s) excluded by statement checks; see claimGuard audit.")
        if loc["ambiguous"]:
            warnings.append("Location is ambiguous: " + "; ".join(loc["ambiguous"]) + f". Using {loc['name']}, {loc['state']}.")
        warnings.append("Service evidence is text extracted from public web pages: confirm availability with the "
                        "facility before travelling.")

        rid = f"req-{uuid.uuid4().hex[:10]}"
        syn = list(self.tags.loc[tag, "synonyms"])
        return _clean({
            "queryContext": {
                "requestId": rid,
                "service": {"canonicalId": tag, "displayName": label, "matchedSynonyms": syn,
                            "confidence": "high" if how == "exact" else "medium"},
                "location": {"type": loc["type"], "inputValue": location_text, "resolvedName": loc["name"],
                             "district": loc["district"], "state": loc["state"], "latitude": loc["lat"],
                             "longitude": loc["lon"], "confidence": loc["confidence"]},
                "searchParameters": {"radiusKm": radius, "limit": limit},
            },
            "results": results,
            "metadata": {
                "requestId": rid, "rankingVersion": self.ranking_version, "ranking": self.ranking_info(),
                "claimGuard": {"policy": config.CLAIM_GUARD_POLICY, "excluded": claim_exclusions,
                               "filteredStatements": filtered_statements},
                "generatedAt": pd.Timestamp.now("UTC").isoformat(timespec="seconds"),
                "totalCandidates": int(len(within)), "returnedCount": len(results), "isPartialResult": len(within) > limit,
                "executionTimeMs": int((time.time() - t0) * 1000), "warnings": warnings,
                "funnel": {"datasetProviders": n_dataset, "datasetRecommendable": n_dataset_ok,
                           "withinRadius": int(len(within)), "reviewBlockedWithinRadius": int(len(blocked)),
                           "radiusStepsKm": steps, "radiusKm": radius, "locationNote": loc["note"],
                           "serviceMatch": how, "dataSource": self.snap.source},
            },
        })

    # ------------------------------------------------------------------ mapping one facility to the UI contract
    def _facility(self, r: pd.Series, rank: int, label: str, loc: dict, radius: float) -> dict:
        uid = r["unique_id"]
        tier = int(r["evidence_tier"])
        ltier = str(r["location_tier"])
        only_eq = bool(r["only_equipment"])
        sources = self._sources(r)
        record_src = sources[0]["id"] if sources else "record"
        evidence = []
        for ev in r["evidence"]:
            usable = ev.get("evidence_status") == "usable"
            strong_field = ev.get("field") in ("procedure", "capability")
            evidence.append({
                "id": f"{uid}-{ev.get('field')}-{ev.get('pos')}",
                "fieldName": f"{ev.get('field')}[{ev.get('pos')}]",
                "matchedService": label,
                "quote": ev.get("text") or "",
                "matchType": "exact",
                "polarity": "positive" if usable else "uncertain",
                "strength": ("strong" if tier == 1 else "medium") if usable and strong_field else ("medium" if usable else "weak"),
                "sourceId": record_src,
            })

        conf = ("high" if tier <= 2 and ltier == "point_verified" and not only_eq
                else "low" if tier == 3 and ltier != "point_verified" or ltier == "pin_area" or only_eq else "medium")
        fields = sorted({ev.get("field") for ev in r["evidence"] if ev.get("evidence_status") == "usable"})
        d = float(r["distance_km"])
        point = ltier.startswith("point") and loc["precision"] == "point"
        dist_txt = f"{d:.1f} km away" if point else f"about {d:.0f} km away"

        # display score: same signals as the sort keys, scaled to the UI's maxima (does NOT decide the order)
        n_src = int(r["n_source_urls"]) if pd.notna(r["n_source_urls"]) else 0
        has_site = isinstance(r["contact_website"], str) and bool(r["contact_website"])
        band = int(r["band_idx"])
        capacity_known = sum(pd.notna(r[c]) for c in ("n_beds", "n_doctors"))
        dup = pd.notna(r["same_name_city_records"]) and r["same_name_city_records"] > 1
        trunc = bool(r["capability_maybe_truncated"]) or bool(r["procedure_maybe_truncated"])
        sb = {
            "serviceMatchScore": 29,
            "evidenceScore": {1: 24, 2: 19, 3: 12}.get(tier, 0) - (4 if only_eq else 0),
            "sourceScore": min(15, (7 if has_site else 0) + min(n_src, 8)),
            "distanceScore": [10, 8, 6, 4, 2, 1, 0][min(band, 6)],
            "locationQualityScore": {"point_verified": 9, "point_unverified": 6, "pin_area": 4}.get(ltier, 0),
            "capacityScore": {0: 0, 1: 4, 2: 7}[capacity_known],
            "penaltyScore": -(3 if r["n_explicit_elsewhere"] > 0 else 0) - (2 if dup else 0) - (1 if trunc else 0),
        }
        # The number shown is the rank score itself, so the order and the number always agree.
        total = int(round(100 * float(r["rank_score"])))
        sb.update({"totalScore": total, "modelVersion": self.ranking_version})
        reranking = None
        if self.ranking_method == "cross_encoder":
            # Components add up to the rank score: text and proof shares of evidence strength, each times closeness.
            w, c = config.RERANK_WEIGHTS, float(r["closeness"])
            sb = {"serviceMatchScore": 100 * c * w["text"] * float(r["text_match"]),
                  "evidenceScore": 100 * c * w["proof"] * float(r["proof"]),
                  "distanceScore": 0, "sourceScore": 0, "locationQualityScore": 0, "capacityScore": 0, "penaltyScore": 0,
                  "totalScore": total, "modelVersion": self.ranking_version}
            reranking = {"method": "cross_encoder", "model": self.scorer.model_name,
                         "textScore": float(r["text_match"]), "evidenceScore": float(r["proof"]),
                         "distanceScore": c, "totalScore": float(r["rank_score"]),
                         "weights": w, "bestEvidenceRef": r["ce_evidence_ref"], "bestEvidenceText": r["ce_best_quote"],
                         "scoredItemCount": int(r["ce_item_count"]),
                         "scoreMeaning": "(text match and proof strength) x closeness for this kind of care; "
                                         "not clinical quality or availability"}

        reasons, msgs, missing = [], ["Current availability, hours, beds and cost are not in the data."], ["current_availability"]
        if only_eq:
            reasons.append("ONLY_EQUIPMENT_EVIDENCE"); msgs.append("Supporting text only mentions equipment, not the service itself.")
        if tier == 3:
            reasons.append("SINGLE_STATEMENT"); msgs.append(f"Only one statement mentions {label}.")
        if ltier == "point_unverified":
            reasons.append("COORDINATES_UNVERIFIED"); msgs.append("Coordinates could not be cross-checked against the PIN.")
        if ltier == "pin_area":
            reasons.append("PIN_AREA_ONLY"); msgs.append("Facility position is known only at PIN-area level.")
        if r["n_explicit_elsewhere"] > 0:
            reasons.append("MENTIONS_OTHER_INSTITUTION"); msgs.append("Some statements also name another institution.")
        if dup:
            reasons.append("POSSIBLE_DUPLICATE"); msgs.append("Another record with the same name and city exists.")
        if trunc:
            reasons.append("LIST_TRUNCATED"); msgs.append("Source lists hit the 50-item cap and may be truncated.")
        if not has_site and not (isinstance(r["contact_phone"], str) and r["contact_phone"]):
            reasons.append("NO_CONTACT"); msgs.append("No phone or website in the data to confirm.")
        for c, f in (("n_beds", "beds"), ("n_doctors", "doctors"), ("year_est", "year_established")):
            if pd.isna(r[c]):
                missing.append(f)
        msgs.append("Confirm with: " + (" | ".join(x for x in [r["contact_phone"], r["contact_website"]]
                                                  if isinstance(x, str) and x) or "no phone/website in data"))
        unc_level = {"high": "low", "medium": "medium", "low": "high"}[conf]
        if unc_level == "low" and len(reasons) > 0:
            unc_level = "medium"
        completeness_fields = [r["contact_phone"], r["contact_website"], r["n_beds"], r["n_doctors"], r["year_est"],
                               r["pincode"], n_src or None, ltier == "point_verified" or None]
        completeness = int(round(100 * sum(1 for v in completeness_fields if isinstance(v, str) and v or
                                           (not isinstance(v, str) and pd.notna(v) and v)) / len(completeness_fields)))
        lane_tag = ("Service relevance and distance" if self.ranking_method == "cross_encoder" else
                    {"A": "Nearest with explicit evidence", "B": "Farther, more supporting detail", "C": "More options"}[r["lane"]])
        tags = [lane_tag] + (["24/7 emergency listed"] if r["lists_emergency_24x7"] else []) + [dist_txt]
        # locality only: the UI appends district, state and PIN itself (no street address in the dataset)
        address = _s(r["city_raw"]) or _s(r["district"]) or _s(r["state"])
        summary = (f"Lists {label}: {int(r['n_explicit_usable'])} supporting statement(s) in "
                   f"{', '.join(fields) or 'no usable field'} (evidence tier {tier}). {dist_txt.capitalize()}"
                   + ("" if point else f" ({'PIN area' if ltier == 'pin_area' else 'from ' + loc['note']})") + ".")
        if reranking is not None:
            summary += (f" Best matching service text: {r['ce_best_quote']} "
                        "Order balances service-text relevance, eligibility and distance.")
        return {
            "id": uid, "rank": rank, "name": _s(r["name"]) or "(unnamed facility)",
            "type": (r["facility_category"] or "facility").title() if isinstance(r["facility_category"], str) else "Facility",
            "operatorType": (r["operator_category"] or "unknown").title() if isinstance(r["operator_category"], str) else "Unknown",
            "address": address, "district": _s(r["district"]), "state": _s(r["state"]),
            "pincode": _s(r["pincode"]), "latitude": float(r["rec_lat"]), "longitude": float(r["rec_lon"]),
            "distanceKm": round(d, 1), "totalScore": total, "confidence": conf,
            "recommendationSummary": summary,
            "scoreBreakdown": sb,
            **({"reranking": reranking} if reranking is not None else {}),
            "evidence": evidence,
            "sources": sources,
            "locationQuality": {"label": {"point_verified": "High confidence", "point_unverified": "Medium confidence",
                                          "pin_area": "PIN area only"}.get(ltier, ltier),
                                "note": _s(r["location_check"])},
            "dataCompleteness": completeness,
            "uncertainty": {"level": unc_level, "reasonCodes": reasons, "messages": msgs, "missingFields": missing,
                            "conflicts": []},
            "tags": tags,
            # Why it ranks here: rank score = proof strength x closeness (see config.py).
            "rankFactors": {
                "proof": round(float(r["proof"]), 2), "closeness": round(float(r["closeness"]), 2),
                "textMatch": round(float(r["text_match"]), 2) if "text_match" in r else None,
                "evidence": round(float(r["evidence_strength"]), 2),
                "score": round(float(r["rank_score"]), 2), "travelKm": travel_km(r["tag_id"]) if "tag_id" in r else None,
                "proofTier": tier, "onlyEquipment": only_eq, "mentionsOther": bool(r["n_explicit_elsewhere"] > 0),
                "locationTier": ltier, "statements": int(r["n_explicit_usable"]),
                "solidProof": bool(r["solid_proof"]),
            },
            # How to check before travelling: the UI shows Call / Website buttons only when these exist.
            "phone": contact_phone(r["contact_phone"]),
            "website": contact_website(r["contact_website"]),
        }

    def _sources(self, r: pd.Series) -> list[dict]:
        site = r["contact_website"] if isinstance(r["contact_website"], str) and r["contact_website"] else None
        site_dom = (urlparse(site if "//" in site else "https://" + site).netloc.lower().removeprefix("www.")) if site else None
        out = []
        if site:
            out.append({"id": f"{r['unique_id']}-site", "url": site if "//" in site else f"https://{site}", "domain": site_dom,
                        "sourceType": "official_site", "title": "Official website (from the facility record)",
                        "retrievedAt": _s(r["recency_of_page_update"]), "supportsClaims": []})
        for i, u in enumerate(r["source_urls"][:5]):
            dom = urlparse(u).netloc.lower().removeprefix("www.")
            if not dom or (site_dom and dom == site_dom and out):
                continue
            stype = ("official_site" if site_dom and dom.endswith(site_dom) else
                     "government" if dom.endswith((".gov.in", ".nic.in", ".gov")) else
                     "social_media" if any(dom.endswith(s) for s in config.SOCIAL_DOMAINS) else
                     "directory" if any(dom.endswith(s) for s in config.DIRECTORY_DOMAINS) else "unknown")
            out.append({"id": f"{r['unique_id']}-src{i}", "url": u, "domain": dom, "sourceType": stype,
                        "title": "Record-level source (not linked to a specific statement)",
                        "retrievedAt": _s(r["recency_of_page_update"]), "supportsClaims": []})
        return out
