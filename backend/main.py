"""
FastAPI backend for MLB Pitch Analytics.

Run from project root:
    uvicorn backend.main:app --reload --port 8000

Endpoints:
    GET  /api/reports                              -> report catalog (home page)
    GET  /api/divisions                            -> cached divisions on disk
    GET  /api/first-pitch-offspeed/meta            -> pitch-type labels, constants
    POST /api/first-pitch-offspeed/compute         -> full result payload

The heavy lifting stays in reports/first_pitch_offspeed/analyze.py — this file
is a thin HTTP shell over it.
"""

from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from reports.first_pitch_offspeed.analyze import (
    compute,
    available_divisions,
    OFFSPEED_PITCH_TYPES,
    PITCH_TYPE_LABELS,
    FASTBALL_TYPES,
    NON_OFFSPEED,
)


app = FastAPI(title="MLB Pitch Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


REPORTS = [
    {
        "id": "first_pitch_offspeed",
        "path": "/reports/first-pitch-offspeed",
        "title": "First-pitch offspeed: CSW% & whiff%",
        "summary": (
            "Do hard throwers (96+ mph fastball) get more CSW% / whiffs when "
            "leading an at-bat with an offspeed pitch than soft throwers? "
            "Splits by velo and 4-seam vs. offspeed vertical separation. Toggle "
            "CSW% (called strikes + whiffs / pitches) or whiff% as the headline metric."
        ),
    },
]


@app.get("/api/reports")
def list_reports():
    return {"reports": REPORTS}


@app.get("/api/divisions")
def list_divisions():
    return {"divisions": available_divisions()}


@app.get("/api/first-pitch-offspeed/meta")
def first_pitch_offspeed_meta():
    return {
        "offspeed_pitch_types": list(OFFSPEED_PITCH_TYPES),
        "pitch_type_labels": PITCH_TYPE_LABELS,
        "fastball_types": sorted(FASTBALL_TYPES),
        "non_offspeed": sorted(NON_OFFSPEED),
    }


class ComputeRequest(BaseModel):
    pitch_types: Optional[List[str]] = None
    location: Optional[str] = Field(None, description="null | 'in' | 'out'")
    platoon: Optional[str] = Field(None, description="null | 'same' | 'opp'")
    p_throws_filter: Optional[str] = Field(None, description="null | 'L' | 'R'")
    velo_floor: Optional[float] = 90.9
    min_fastballs: int = 50
    min_4seam: int = 30
    min_offspeed: int = 30
    min_swings: int = 0
    min_pitches: int = 0
    divisions: Optional[List[str]] = None


@app.post("/api/first-pitch-offspeed/compute")
def first_pitch_offspeed_compute(req: ComputeRequest):
    try:
        result = compute(
            pitch_types=set(req.pitch_types) if req.pitch_types else None,
            location=req.location,
            platoon=req.platoon,
            p_throws_filter=req.p_throws_filter,
            velo_floor=req.velo_floor,
            min_fastballs=req.min_fastballs,
            min_4seam=req.min_4seam,
            min_offspeed=req.min_offspeed,
            min_swings=req.min_swings,
            min_pitches=req.min_pitches,
            divisions=req.divisions,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result
