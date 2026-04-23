"""
Lookup endpoints — the dropdowns. Power the frontend's pick-a-pitcher /
pick-a-batter / pick-a-season UI.

- `/seasons`      — list of seasons that have derived data
- `/pitch-types`  — code → label, the full enumeration
- `/pitchers`     — search-as-you-type over pitcher names
- `/batters`      — search-as-you-type over batter names (Chadwick-backed)
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.v2 import player_names
from backend.v2.constants import PITCH_TYPE_LABELS
from backend.v2.db import CursorDep
from backend.v2.models import PitchTypeOption, Player

router = APIRouter()


class SeasonList(BaseModel):
    seasons: list[int]


@router.get("/seasons", response_model=SeasonList)
def list_seasons(con=CursorDep):
    """Seasons present in the derived tables, newest first."""
    rows = con.execute(
        "SELECT DISTINCT season FROM pitcher_pitch_mix ORDER BY season DESC"
    ).fetchall()
    return {"seasons": [int(r[0]) for r in rows]}


class PitchTypeList(BaseModel):
    pitch_types: list[PitchTypeOption]


@router.get("/pitch-types", response_model=PitchTypeList)
def list_pitch_types(con=CursorDep):
    """All pitch-type codes seen in the data, with human labels from constants."""
    rows = con.execute(
        "SELECT DISTINCT pitch_type FROM pitcher_pitch_mix "
        "WHERE pitch_type IS NOT NULL ORDER BY pitch_type"
    ).fetchall()
    return {
        "pitch_types": [
            {"code": r[0], "label": PITCH_TYPE_LABELS.get(r[0], r[0])}
            for r in rows
        ]
    }


class PlayerList(BaseModel):
    players: list[Player]


@router.get("/pitchers", response_model=PlayerList)
def list_pitchers(
    season: int | None = Query(None, description="Optional season filter"),
    q: str | None = Query(None, description="Case-insensitive substring against name"),
    limit: int = Query(20, ge=1, le=200),
    con=CursorDep,
):
    """Pitchers with at least one pitch in `pitcher_pitch_mix`, searchable by name."""
    clauses = ["player_name IS NOT NULL"]
    params: list = []
    if season is not None:
        clauses.append("season = ?")
        params.append(season)
    if q:
        clauses.append("lower(player_name) LIKE ?")
        params.append(f"%{q.lower()}%")
    where = " AND ".join(clauses)

    rows = con.execute(
        f"""
        SELECT pitcher, ANY_VALUE(player_name) AS name
        FROM pitcher_pitch_mix
        WHERE {where}
        GROUP BY pitcher
        ORDER BY name
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()
    return {"players": [{"id": int(r[0]), "name": r[1]} for r in rows]}


@router.get("/batters", response_model=PlayerList)
def list_batters(
    season: int | None = Query(None, description="Optional season filter"),
    q: str | None = Query(None, description="Case-insensitive substring against name"),
    limit: int = Query(20, ge=1, le=200),
    con=CursorDep,
):
    """Batters with at least one swing in `batter_whiff_profile`.

    Names come from Chadwick Bureau (see `player_names.py`). If the register
    can't be loaded, IDs are returned with the name field populated as
    `"id:665742"` so the UI still renders something selectable.
    """
    where = "batter IS NOT NULL"
    params: list = []
    if season is not None:
        where += " AND season = ?"
        params.append(season)

    rows = con.execute(
        f"SELECT DISTINCT batter FROM batter_whiff_profile WHERE {where}",
        params,
    ).fetchall()
    ids = {int(r[0]) for r in rows}

    matches = player_names.search(q, ids, limit=limit)
    if matches:
        return {"players": matches}

    # Fallback: names unavailable. Show IDs so the UI still works.
    fallback = sorted(ids)[:limit]
    return {"players": [{"id": i, "name": f"id:{i}"} for i in fallback]}
