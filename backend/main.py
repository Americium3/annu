"""CarePath API: serves the service-first recommender to the React frontend (web/).

Run:  uvicorn main:app --port 8000      (from this folder; see README.md)
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from data_store import get_snapshot
from recommender import LocationNotFound, Recommender, ServiceNotFound

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    snap = get_snapshot(refresh=os.environ.get("CAREPATH_REFRESH") == "1")
    STATE["rec"] = Recommender(snap)
    print(f"CarePath API ready – data: {snap.source}", file=sys.stderr)
    yield


app = FastAPI(title="CarePath API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CAREPATH_CORS", "http://127.0.0.1:5173,http://localhost:5173").split(","),
                   allow_methods=["*"], allow_headers=["*"])


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class RecommendationRequest(BaseModel):
    serviceText: str = Field(min_length=1, max_length=200)
    locationText: str = Field(default="", max_length=200)
    radiusKm: float | None = Field(default=None, gt=0, le=500)
    rankingMode: Literal["best_match", "nearest", "most_evidence"] = "best_match"
    limit: int = Field(default=8, ge=1, le=50)
    coordinates: Coordinates | None = None


@app.get("/api/health")
def health():
    rec: Recommender = STATE["rec"]
    return {"status": "ok", "data": rec.snap.source, "facilityServiceRows": len(rec.index), "services": len(rec.tags)}


@app.get("/api/services")
def services():
    return STATE["rec"].services()


@app.get("/api/locations")
def locations(q: str = Query(default="", max_length=100), limit: int = Query(default=8, ge=1, le=20)):
    return STATE["rec"].location_suggestions(q, limit)


@app.post("/api/recommendations")
def recommendations(req: RecommendationRequest):
    try:
        return STATE["rec"].recommend(req.serviceText, req.locationText, req.radiusKm, req.rankingMode, req.limit,
                                      req.coordinates.model_dump() if req.coordinates else None)
    except ServiceNotFound as e:
        raise HTTPException(422, {"field": "service", "message": str(e), "suggestions": e.suggestions})
    except LocationNotFound as e:
        raise HTTPException(422, {"field": "location", "message": str(e), "suggestions": e.suggestions})
