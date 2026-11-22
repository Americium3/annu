"""High-recall service membership -> evidence scoring -> geographic ranking.

Scores measure textual relevance, NOT clinical quality or service availability.
All methods share candidates, evidence eligibility, location policy and fusion.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from pipeline.tag_dictionary import TAGS

METHODS = ("rules", "tfidf", "bm25", "bi_encoder", "cross_encoder")
FIELDS = ("procedure", "capability", "equipment", "specialty", "specialties", "description")
RELATED = {
    "kidney-dialysis": r"nephrolog|renal medicine",
    "c-section": r"obstetri|maternity|gynecol|gynaecol",
    "emergency-c-section": r"obstetri|maternity|gynecol|gynaecol",
    "nicu": r"neonatolog|newborn care|pediatr|paediatr",
    "cardiac-surgery": r"cardiolog|cardiothoracic",
    "mri": r"radiolog|diagnostic imaging",
    "burns": r"plastic surg|trauma",
}
DEFAULT_SERVICES = ("kidney-dialysis", "emergency-c-section", "nicu", "cardiac-surgery", "mri", "burns")


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def truth(value):
    return str(value).strip().lower() in {"true", "1", "1.0", "yes"}


def clean_text(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"null", "none", "nan", "[]"} else text


def items(value):
    if isinstance(value, (list, tuple, np.ndarray)):
        return list(value)
    text = clean_text(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return [text]


@dataclass(frozen=True)
class Settings:
    text_weight: float = .4
    evidence_weight: float = .3
    distance_weight: float = .3
    distance_decay_km: float = 30.
    max_radius_km: float = 200.
    top_k: int = 3
    max_evidence_per_facility: int = 5
    location_policy: str = "review"  # or respect_resolved: trust supplied, audited location_tier
    fusion: str = "weighted"        # or evidence_first
    bm25_scale: float = 3.
    bi_model: str = "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"
    cross_model: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    model_revision: str | None = None
    device: str = "cpu"
    batch_size: int = 32

    def __post_init__(self):
        weights = (self.text_weight, self.evidence_weight, self.distance_weight)
        if not all(math.isfinite(w) and w >= 0 for w in weights) or not math.isclose(sum(weights), 1):
            raise ValueError("Nonnegative fusion weights must sum to 1")
        if min(self.distance_decay_km, self.max_radius_km, self.bm25_scale) <= 0:
            raise ValueError("Distance and BM25 scales must be positive")
        if min(self.top_k, self.max_evidence_per_facility, self.batch_size) < 1:
            raise ValueError("Counts must be positive")
        if self.location_policy not in {"review", "respect_resolved"}:
            raise ValueError("Unknown location policy")
        if self.fusion not in {"weighted", "evidence_first"}:
            raise ValueError("Unknown fusion")


def catalog():
    result = {t.id: {"id": t.id, "label": t.label, "patterns": list(t.patterns),
                     "synonyms": list(t.synonyms)} for t in TAGS}
    # Emergency C-section is NOT an alias of ordinary C-section.
    result["emergency-c-section"] = {
        **result["c-section"], "id": "emergency-c-section", "label": "Emergency caesarean section",
        "synonyms": ["emergency c section", "emergency cesarean", "emergency caesarean"],
    }
    return result


def canonical_service(text):
    query = norm(text)
    if not query:
        raise ValueError("Empty service")
    hits = []
    for key, service in catalog().items():
        if query in {norm(key), norm(service["label"]), *map(norm, service["synonyms"])}:
            hits.append(key)
    if len(hits) != 1:
        raise ValueError(f"Unknown or ambiguous service {text!r}; use a canonical ID from catalog()")
    return hits[0]


def validate_point(lat, lon):
    try:
        return math.isfinite(float(lat)) and math.isfinite(float(lon)) and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180 and (float(lat), float(lon)) != (0., 0.)
    except (TypeError, ValueError):
        return False


def haversine(lat, lon, lats, lons):
    a, b = np.radians(lat), np.radians(np.asarray(lats, dtype=float))
    h = np.sin((b-a)/2)**2 + np.cos(a)*np.cos(b)*np.sin(np.radians(np.asarray(lons, dtype=float)-lon)/2)**2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def assess(text, field, pattern, related, emergency=False):
    """Conservative heuristics, not medical verification or an entailment model."""
    direct = list(pattern.finditer(text))
    if not direct:
        return "related" if related and re.search(related, text, re.I) else None
    # Check both sides of the match, within punctuation-delimited clause.
    statuses = []
    for match in direct:
        left = max(text.rfind(p, 0, match.start()) for p in (".", ";", "\n")) + 1
        stops = [text.find(p, match.end()) for p in (".", ";", "\n")]
        right = min([p for p in stops if p >= 0] or [len(text)])
        clause = text[left:right]
        prefix = text[max(left, match.start()-70):match.start()]
        negative = (re.search(r"\b(no|not|without|never|non)[\s-]+(?:\w+[\s-]+){0,5}$", prefix, re.I)
                    or re.search(r"\b(discontinued|stopped|unavailable|suspended|not (?:available|provided|offered))\b", clause, re.I))
        planned = re.search(r"\b(plann?ed|planning|proposed|future|will (?:offer|provide|open)|coming soon)\b", clause, re.I)
        historical = re.search(r"\b(trained (?:in|at)|previously worked|formerly|used to|training in)\b", clause, re.I)
        unknown = re.search(r"\b(no explicit|not specified|not mentioned|unknown|unclear|no information)\b", clause, re.I)
        if unknown:
            statuses.append("uncertain")
        elif negative:
            statuses.append("negative")
        elif planned or historical:
            statuses.append("planned_or_historical")
        elif emergency and not re.search(r"\bemergen(?:cy|t)\b", clause, re.I):
            statuses.append("related")
        elif field in {"equipment", "specialty", "specialties"}:
            statuses.append("related")
        else:
            statuses.append("text_supported")
    if "text_supported" in statuses and any(s in statuses for s in ("negative", "planned_or_historical")):
        return "conflict"
    for s in ("text_supported", "conflict", "negative", "planned_or_historical", "uncertain", "related"):
        if s in statuses:
            return s


class ExperimentEngine:
    def __init__(self, facilities, evidence, settings=Settings()):
        started = time.perf_counter()
        self.settings = settings
        self.facilities = facilities.copy()
        if "unique_id" not in facilities or "unique_id" not in evidence:
            raise ValueError("Both inputs need unique_id")
        if facilities.unique_id.isna().any() or facilities.unique_id.astype(str).duplicated().any():
            raise ValueError("Facilities require unique, non-null IDs; resolve duplicates explicitly first")
        self.facilities["unique_id"] = facilities.unique_id.astype(str)
        self.facilities = self.facilities.set_index("unique_id", drop=False)
        self.evidence = evidence.copy()
        needed = {"field", "text"}
        if not needed.issubset(evidence.columns):
            raise ValueError("Evidence needs unique_id, field, text, and preferably item_idx/evidence_status")
        self.evidence["unique_id"] = evidence.unique_id.astype(str)
        self.evidence["text"] = evidence.text.map(clean_text)
        self.evidence = self.evidence[self.evidence.text.ne("") & self.evidence.field.isin(FIELDS)].copy()
        self.orphan_evidence_count = int((~self.evidence.unique_id.isin(self.facilities.index)).sum())
        self.evidence = self.evidence[self.evidence.unique_id.isin(self.facilities.index)].reset_index(drop=True)
        if "item_idx" not in self.evidence:
            self.evidence["item_idx"] = self.evidence.groupby(["unique_id", "field"]).cumcount()
        self.evidence = self.evidence.drop_duplicates(["unique_id", "field", "item_idx", "text"]).reset_index(drop=True)
        if self.evidence.empty:
            raise ValueError("No usable evidence rows")
        # Fit on a fixed, deduplicated corpus, not the location-dependent shortlist.
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, strip_accents="unicode")
        self.texts = list(dict.fromkeys(self.evidence.text))
        self.tfidf = self.vectorizer.fit_transform(self.texts)
        self.text_index = {s: i for i, s in enumerate(self.texts)}
        self.tokens = [Counter(re.findall(r"\b\w+\b", s.lower())) for s in self.texts]
        self.df = Counter(t for doc in self.tokens for t in doc)
        self.avgdl = sum(map(lambda d: sum(d.values()), self.tokens)) / len(self.tokens)
        self._candidates, self._scores, self._models = {}, {}, {}
        self.setup_seconds = time.perf_counter() - started
        payload = self.facilities.sort_index().to_json() + self.evidence.to_json()
        self.data_fingerprint = hashlib.sha256(payload.encode()).hexdigest()

    def candidates(self, service):
        service = canonical_service(service)
        if service in self._candidates:
            return self._candidates[service].copy()
        spec = catalog()[service]
        pattern = re.compile("|".join(f"(?:{p})" for p in spec["patterns"]), re.I)
        rows = []
        # Retain uncertain/negative matches for auditing rather than dropping them at extraction.
        for ev in self.evidence.to_dict("records"):
            state = assess(ev["text"], ev["field"], pattern, RELATED.get(service), service == "emergency-c-section")
            if not state:
                continue
            upstream = clean_text(ev.get("evidence_status")).lower()
            if upstream and upstream not in {"usable", "positive", "text_supported"}:
                state = "upstream_review"
            rows.append({**ev, "service_id": service, "status": state,
                         "evidence_ref": f"{ev['field']}:{ev['item_idx']}",
                         "attribution_verified": upstream == "usable"})
        frame = pd.DataFrame(rows, columns=[*self.evidence.columns, "service_id", "status", "evidence_ref", "attribution_verified"])
        self._candidates[service] = frame
        return frame.copy()

    def _model(self, method):
        if method not in self._models:
            try:
                from sentence_transformers import SentenceTransformer, CrossEncoder
            except ImportError as exc:
                raise RuntimeError("Neural methods require experiments/requirements-neural.txt") from exc
            cls = SentenceTransformer if method == "bi_encoder" else CrossEncoder
            model_id = self.settings.bi_model if method == "bi_encoder" else self.settings.cross_model
            kwargs = {"device": self.settings.device}
            if self.settings.model_revision:
                kwargs["revision"] = self.settings.model_revision
            self._models[method] = cls(model_id, **kwargs)
        return self._models[method]

    def score_service(self, service, method):
        service = canonical_service(service)
        if method not in METHODS:
            raise ValueError(f"Unknown method {method}")
        key = (service, method)
        if key in self._scores:
            return self._scores[key].copy()
        frame = self.candidates(service)
        if frame.empty:
            frame["text_score"] = pd.Series(dtype=float)
            self._scores[key] = frame
            return frame.copy()
        spec = catalog()[service]
        query = " ".join(dict.fromkeys([spec["label"], *spec["synonyms"]]))
        # Shared status priority/cap across methods; never pick evidence using a competitor's score.
        priorities = {"text_supported": 0, "related": 1, "uncertain": 2}
        frame["priority"] = frame.status.map(priorities).fillna(3)
        frame = frame.sort_values(["unique_id", "priority", "evidence_ref", "text"], kind="stable")
        frame = frame.groupby("unique_id", sort=False).head(self.settings.max_evidence_per_facility).copy()
        texts = list(dict.fromkeys(frame.text))
        idx = [self.text_index[t] for t in texts]
        if method == "rules":
            scores = np.ones(len(texts))
        elif method == "tfidf":
            scores = (self.tfidf[idx] @ self.vectorizer.transform([query]).T).toarray().ravel()
        elif method == "bm25":
            terms = set(re.findall(r"\b\w+\b", query.lower()))
            values = []
            for i in idx:
                doc = self.tokens[i]
                dl = sum(doc.values())
                score = 0.
                for term in terms:
                    tf = doc.get(term, 0)
                    idf = math.log(1 + (len(self.tokens)-self.df[term]+.5)/(self.df[term]+.5))
                    score += idf * tf*2.5/(tf+1.5*(.25+.75*dl/max(self.avgdl, 1)))
                values.append(score)
            values = np.asarray(values)
            scores = values/(values+self.settings.bm25_scale)
        elif method == "bi_encoder":
            model = self._model(method)
            vectors = model.encode(texts, batch_size=self.settings.batch_size, normalize_embeddings=True, show_progress_bar=False)
            q = model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
            scores = np.clip(np.asarray(vectors) @ q, 0, 1)
        else:
            model = self._model(method)
            import torch
            scores = np.asarray(model.predict([(query, t) for t in texts], batch_size=self.settings.batch_size,
                                activation_fn=torch.nn.Sigmoid(), show_progress_bar=False)).reshape(-1)
        mapping = dict(zip(texts, map(float, scores)))
        frame["text_score"] = frame.text.map(mapping)
        self._scores[key] = frame
        return frame.copy()

    def recommend(self, service, lat, lon, method="rules"):
        started = time.perf_counter()
        if not validate_point(lat, lon):
            raise ValueError("Invalid query coordinates")
        service = canonical_service(service)
        all_ev = self.candidates(service)
        scored = self.score_service(service, method)
        scored_groups = {uid: group for uid, group in scored.groupby("unique_id", sort=False)}
        result = []
        for uid, ev in all_ev.groupby("unique_id", sort=True):
            fac = self.facilities.loc[uid]
            flags = []
            # Read resolved location atomically; never mix latitude from one source with longitude from another.
            latitude, longitude = None, None
            location_tier = clean_text(fac.get("location_tier")) or "unverified"
            for a, b in (("loc_lat", "loc_lon"), ("best_lat", "best_lon"), ("latitude", "longitude")):
                if validate_point(fac.get(a), fac.get(b)):
                    latitude, longitude = float(fac[a]), float(fac[b])
                    break
            if latitude is None or location_tier in {"blocked", "review_blocked", "unusable", "none"}:
                flags.append("location_unusable")
            conflict = truth(fac.get("flag_coord_pin_conflict"))
            if conflict and (self.settings.location_policy == "review" or location_tier not in {"point_verified", "pin_area"}):
                flags.append("location_conflict")
            if truth(fac.get("core_identity_conflict")):
                flags.append("identity_conflict")
            if clean_text(fac.get("row_status")).lower() in {"fragment", "fragmented", "corrupt", "invalid", "blocked", "review_blocked"}:
                flags.append("upstream_row_blocked")
            statuses = set(ev.status)
            if "conflict" in statuses or ("text_supported" in statuses and "negative" in statuses):
                flags.append("service_evidence_conflict")
            if "text_supported" not in statuses:
                flags.append("no_explicit_text_support")
            group = scored_groups[uid]
            supported = group[group.status == "text_supported"]
            selected = supported if len(supported) else group
            best = selected.sort_values(["text_score", "evidence_ref"], ascending=[False, True]).iloc[0]
            tscore = float(best.text_score)
            es = 1. if "text_supported" in statuses else .25
            distance = float(haversine(lat, lon, [latitude], [longitude])[0]) if latitude is not None else None
            if distance is not None and distance > self.settings.max_radius_km:
                flags.append("outside_radius")
            g = math.exp(-distance/self.settings.distance_decay_km) if distance is not None else 0.
            s = self.settings
            score = s.text_weight*tscore+s.evidence_weight*es+s.distance_weight*g
            quotes = [{"ref": r.evidence_ref, "field": r.field, "text": r.text,
                       "status": r.status, "attribution_verified": bool(r.attribution_verified)}
                      for r in selected.sort_values(["text_score", "evidence_ref"], ascending=[False, True]).head(3).itertuples()]
            if conflict:
                warning = "Coordinate/PIN conflict; resolved location is supplied by the upstream pipeline."
            else:
                warning = "Location is not independently verified by this experiment."
            result.append({"unique_id": uid, "name": clean_text(fac.get("name")), "service_id": service,
                           "method": method, "latitude": latitude, "longitude": longitude,
                           "distance_km": distance, "location_tier": location_tier,
                           "eligible": not flags, "reasons": flags, "score": score,
                           "text_score": tscore, "evidence_score": es, "distance_score": g,
                           "evidence": quotes, "source_urls": items(fac.get("source_urls_clean", fac.get("source_urls"))),
                           "warnings": [warning, "Sources are record-level, not statement citations.",
                                        "Text support is not proof of current service availability."]})
        key = (lambda r: (-r["evidence_score"], -r["score"], r["unique_id"])) if self.settings.fusion == "evidence_first" else (lambda r: (-r["score"], r["unique_id"]))
        result.sort(key=key)
        for rank, row in enumerate([r for r in result if r["eligible"]], 1):
            row["rank"] = rank
        picked = [r for r in result if r["eligible"]][:self.settings.top_k]
        for row in picked:
            row["recommendation_reason"] = (f"Supporting {service} text: {row['evidence'][0]['text']} "
                f"Approximate straight-line distance {row['distance_km']:.1f} km; "
                f"ranked using {method}, evidence and distance ({self.settings.fusion}).")
        return {"service_id": service, "method": method, "query": {"latitude": lat, "longitude": lon},
                "results": picked, "audit": result, "candidate_ids": sorted(all_ev.unique_id.unique()),
                "latency_ms": (time.perf_counter()-started)*1000,
                "settings": asdict(self.settings), "data_fingerprint": self.data_fingerprint}


def geojson(response):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
         "properties": r} for r in response["results"]]}
