"""CarePath API: serves the service-first recommender to the React frontend (web/).

Run:  uvicorn main:app --port 8000      (from this folder; see README.md)
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from data_store import get_snapshot
from recommender import LocationNotFound, Recommender, ServiceNotFound
from cross_encoder import CrossEncoderError
from judge import EvidenceJudge
from nlu import LlmClient, Understander

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    snap = get_snapshot(refresh=os.environ.get("CAREPATH_REFRESH") == "1")
    rec = Recommender(snap)
    rec.warmup()  # Fail startup visibly if the default model cannot load; no rule fallback.
    STATE["rec"] = rec
    # One language model (a Databricks serving endpoint) for both LLM steps: reading the request (nlu.py) and
    # judging the top hospitals' own records (judge.py). Without it, both fall back to rules, stated in /api/health.
    llm = None
    if os.environ.get("CAREPATH_LLM_ENDPOINT"):
        try:
            llm = LlmClient(os.environ["CAREPATH_LLM_ENDPOINT"])
        except Exception as exc:
            print(f"LLM unavailable ({type(exc).__name__}); using rules only", file=sys.stderr)
    STATE["nlu"] = Understander(known_place=rec.known_place, llm=llm or False)
    rec.judge = EvidenceJudge(llm) if llm else None
    print(f"CarePath API ready – data: {snap.source}", file=sys.stderr)
    yield


app = FastAPI(title="CarePath API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CAREPATH_CORS", "http://127.0.0.1:5173,http://localhost:5173").split(","),
                   allow_methods=["*"], allow_headers=["*"])


class Coordinates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RecommendationRequest(BaseModel):
    """The service and the location (`coordinates` when "Use my location" gave them), plus the urgency level
    /api/ask found in the person's own words (3 = needs care today: nearer hospitals count more). Any other
    field (radius, ranking, limit, ...) is rejected."""
    model_config = ConfigDict(extra="forbid")
    serviceText: str = Field(min_length=1, max_length=200)
    locationText: str = Field(default="", max_length=200)
    coordinates: Coordinates | None = None
    urgency: int | None = Field(default=None, ge=1, le=4)
    # Let the language model read the top hospitals' records and judge them (slower; the page asks after showing
    # the rules ranking, then animates the change).
    judge: bool = False


class AskRequest(BaseModel):
    """A free-text request ("my father needs dialysis near Cuttack"). `locationText` / `coordinates` are the
    person's saved place or device location, used only when the message names no place."""
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=600)
    locationText: str = Field(default="", max_length=200)
    coordinates: Coordinates | None = None


@app.get("/api/health")
def health():
    rec: Recommender = STATE["rec"]
    return {"status": "ok", "data": rec.snap.source, "facilityServiceRows": len(rec.index), "services": len(rec.tags),
            "ranking": rec.ranking_info(), "understanding": STATE["nlu"].info() if "nlu" in STATE else None,
            "judge": rec.judge.info() if rec.judge else None}


@app.get("/api/services")
def services():
    return STATE["rec"].services()


@app.get("/api/locations")
def locations(q: str = Query(default="", max_length=100)):
    return STATE["rec"].location_suggestions(q)


@app.post("/api/recommendations")
def recommendations(req: RecommendationRequest):
    try:
        return STATE["rec"].recommend(req.serviceText, req.locationText,
                                      req.coordinates.model_dump() if req.coordinates else None, req.urgency,
                                      req.judge)
    except ServiceNotFound as e:
        raise HTTPException(422, {"field": "service", "message": str(e), "suggestions": e.suggestions})
    except LocationNotFound as e:
        raise HTTPException(422, {"field": "location", "message": str(e), "suggestions": e.suggestions})
    except CrossEncoderError as e:
        raise HTTPException(503, {"message": str(e)})


@app.post("/api/ask")
def ask(req: AskRequest):
    """Understand a free-text request, then search when it is clear enough.

    `next` tells the page what to do: "emergency" (emergency score 80+: open the emergency screen, no search),
    "ask_care" (no care found, or a broad word with `careOptions`), "ask_place" (no usable place), or "results"
    (`results` holds the recommendations, ranked with the request's urgency)."""
    rec: Recommender = STATE["rec"]
    nlu: Understander = STATE["nlu"]
    u = nlu.understand(req.text)
    out = nlu_dict = u.dict(nlu.names)
    coords = req.coordinates.model_dump() if req.coordinates else None
    if u.emergency:
        return {**nlu_dict, "next": "emergency"}
    if not u.care_id or u.care_id not in rec.tags.index:
        return {**out, "next": "ask_care"}
    if u.place_text:
        place, use_coords = u.place_text, None
    elif u.place_here and coords:
        place, use_coords = "", coords
    elif u.place_here:
        return {**out, "next": "ask_place", "placeMessage": "Share your location, or type a city, district or PIN."}
    elif coords or req.locationText.strip():
        place, use_coords = req.locationText, coords
        out["place"] = {"text": req.locationText or None, "here": bool(coords), "source": "saved"}
    else:
        return {**out, "next": "ask_place"}
    try:
        results = rec.recommend(u.care_id, place, use_coords, u.level)
    except LocationNotFound as e:
        return {**out, "next": "ask_place", "placeMessage": str(e), "placeSuggestions": e.suggestions}
    except ServiceNotFound as e:
        return {**out, "next": "ask_care", "careMessage": str(e)}
    except CrossEncoderError as e:
        raise HTTPException(503, {"message": str(e)})
    return {**out, "next": "results", "results": results}
