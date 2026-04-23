"""
Pitch-sequence analyzer endpoints.

Three views over the sequence data:
- `GET /sequences/pitcher/{id}`  — one pitcher's 2-pitch combos, filterable by count.
- `GET /sequences/batter/{id}`   — one batter's outcomes on 2-pitch combos.
- `GET /sequences/leaderboard`   — top N players on a specific sequence.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from backend.v2 import player_names
from backend.v2.constants import DEFAULT_MIN_SEQUENCE_N
from backend.v2.db import CursorDep
from backend.v2.models import (
    BatterSequenceRow,
    PitcherSequenceRow,
    SequenceLeaderRow,
)

router = APIRouter()


# --- Pitcher sequences -----------------------------------------------------

PITCHER_SORT_COLS = {
    "whiff_rate_shrunk": "whiff_rate_shrunk DESC NULLS LAST",
    "whiff_rate_raw": "whiff_rate_raw DESC NULLS LAST",
    "put_away_rate_shrunk": "put_away_rate_shrunk DESC NULLS LAST",
    "n_sequences": "n_sequences DESC",
    "lift": "(whiff_rate_shrunk - league_whiff_rate) DESC NULLS LAST",
}


class PitcherSequenceResponse(BaseModel):
    pitcher: int
    player_name: str | None
    rows: list[PitcherSequenceRow]


@router.get("/sequences/pitcher/{pitcher_id}", response_model=PitcherSequenceResponse)
def pitcher_sequences(
    pitcher_id: int = Path(..., description="MLBAM ID"),
    season: int | None = Query(None),
    balls: int | None = Query(None, ge=0, le=3),
    strikes: int | None = Query(None, ge=0, le=2),
    pitch1: str | None = Query(None, description="Pitch-type code, e.g. 'FF'"),
    pitch2: str | None = Query(None),
    min_n: int = Query(DEFAULT_MIN_SEQUENCE_N, ge=0, description="Minimum n_sequences"),
    sort: str = Query("whiff_rate_shrunk", description=f"One of: {list(PITCHER_SORT_COLS)}"),
    limit: int = Query(50, ge=1, le=500),
    con=CursorDep,
):
    if sort not in PITCHER_SORT_COLS:
        raise HTTPException(400, detail=f"Invalid sort. Options: {list(PITCHER_SORT_COLS)}")

    clauses = ["pitcher = ?", "n_sequences >= ?"]
    params: list = [pitcher_id, min_n]
    if season is not None:
        clauses.append("season = ?")
        params.append(season)
    if balls is not None:
        clauses.append("balls_before_p1 = ?")
        params.append(balls)
    if strikes is not None:
        clauses.append("strikes_before_p1 = ?")
        params.append(strikes)
    if pitch1:
        clauses.append("pitch1_type = ?")
        params.append(pitch1)
    if pitch2:
        clauses.append("pitch2_type = ?")
        params.append(pitch2)
    where = " AND ".join(clauses)

    rows = con.execute(
        f"""
        SELECT pitcher, player_name, season, balls_before_p1, strikes_before_p1,
               pitch1_type, pitch2_type, n_sequences, swings_on_p2, whiffs_on_p2,
               two_strike_p2, put_aways,
               whiff_rate_raw, whiff_rate_shrunk, league_whiff_rate,
               put_away_rate_raw, put_away_rate_shrunk, league_put_away_rate
        FROM pitcher_sequences_2pitch
        WHERE {where}
        ORDER BY {PITCHER_SORT_COLS[sort]}
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()

    cols = [
        "pitcher", "player_name", "season", "balls_before_p1", "strikes_before_p1",
        "pitch1_type", "pitch2_type", "n_sequences", "swings_on_p2", "whiffs_on_p2",
        "two_strike_p2", "put_aways",
        "whiff_rate_raw", "whiff_rate_shrunk", "league_whiff_rate",
        "put_away_rate_raw", "put_away_rate_shrunk", "league_put_away_rate",
    ]
    records = [dict(zip(cols, r)) for r in rows]
    header_name = records[0]["player_name"] if records else None
    return {"pitcher": pitcher_id, "player_name": header_name, "rows": records}


# --- Batter sequences ------------------------------------------------------

BATTER_SORT_COLS = {
    "whiff_rate_shrunk": "whiff_rate_shrunk DESC NULLS LAST",
    "whiff_rate_raw": "whiff_rate_raw DESC NULLS LAST",
    "strikeout_rate_shrunk": "strikeout_rate_shrunk DESC NULLS LAST",
    "n_sequences": "n_sequences DESC",
    "lift": "(whiff_rate_shrunk - league_whiff_rate) DESC NULLS LAST",
}


class BatterSequenceResponse(BaseModel):
    batter: int
    batter_name: str | None
    rows: list[BatterSequenceRow]


@router.get("/sequences/batter/{batter_id}", response_model=BatterSequenceResponse)
def batter_sequences(
    batter_id: int = Path(..., description="MLBAM ID"),
    season: int | None = Query(None),
    pitch1: str | None = Query(None),
    pitch2: str | None = Query(None),
    min_n: int = Query(DEFAULT_MIN_SEQUENCE_N, ge=0),
    sort: str = Query("whiff_rate_shrunk", description=f"One of: {list(BATTER_SORT_COLS)}"),
    limit: int = Query(50, ge=1, le=500),
    con=CursorDep,
):
    if sort not in BATTER_SORT_COLS:
        raise HTTPException(400, detail=f"Invalid sort. Options: {list(BATTER_SORT_COLS)}")

    clauses = ["batter = ?", "n_sequences >= ?"]
    params: list = [batter_id, min_n]
    if season is not None:
        clauses.append("season = ?")
        params.append(season)
    if pitch1:
        clauses.append("pitch1_type = ?")
        params.append(pitch1)
    if pitch2:
        clauses.append("pitch2_type = ?")
        params.append(pitch2)
    where = " AND ".join(clauses)

    rows = con.execute(
        f"""
        SELECT batter, season, pitch1_type, pitch2_type, n_sequences,
               swings_on_p2, whiffs_on_p2, two_strike_p2, strikeouts_on_p2,
               whiff_rate_raw, whiff_rate_shrunk, league_whiff_rate,
               strikeout_rate_raw, strikeout_rate_shrunk, league_strikeout_rate
        FROM batter_vs_sequences
        WHERE {where}
        ORDER BY {BATTER_SORT_COLS[sort]}
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()

    cols = [
        "batter", "season", "pitch1_type", "pitch2_type", "n_sequences",
        "swings_on_p2", "whiffs_on_p2", "two_strike_p2", "strikeouts_on_p2",
        "whiff_rate_raw", "whiff_rate_shrunk", "league_whiff_rate",
        "strikeout_rate_raw", "strikeout_rate_shrunk", "league_strikeout_rate",
    ]
    batter_name = player_names.lookup(batter_id)
    records = []
    for r in rows:
        rec = dict(zip(cols, r))
        rec["batter_name"] = batter_name
        records.append(rec)
    return {"batter": batter_id, "batter_name": batter_name, "rows": records}


# --- Leaderboard -----------------------------------------------------------

class SequenceLeaderboard(BaseModel):
    role: str
    pitch1_type: str
    pitch2_type: str
    season: int
    rows: list[SequenceLeaderRow]


@router.get("/sequences/leaderboard", response_model=SequenceLeaderboard)
def sequence_leaderboard(
    pitch1: str = Query(..., description="Pitch 1 code, e.g. 'FF'"),
    pitch2: str = Query(..., description="Pitch 2 code, e.g. 'CH'"),
    season: int = Query(..., description="Season"),
    role: str = Query("pitcher", pattern="^(pitcher|batter)$"),
    balls: int | None = Query(None, ge=0, le=3, description="pitcher-role only; count-slice"),
    strikes: int | None = Query(None, ge=0, le=2, description="pitcher-role only; count-slice"),
    min_n: int = Query(50, ge=0, description="Minimum n_sequences"),
    limit: int = Query(20, ge=1, le=200),
    con=CursorDep,
):
    """Top players on a specific 2-pitch sequence, ranked by lift vs league.

    `role=pitcher` uses `pitcher_sequences_2pitch` (count-sliced).
    `role=batter` uses `batter_vs_sequences` (rolled up across counts).
    """
    if role == "pitcher":
        clauses = [
            "pitch1_type = ?", "pitch2_type = ?", "season = ?", "n_sequences >= ?",
        ]
        params: list = [pitch1, pitch2, season, min_n]
        if balls is not None:
            clauses.append("balls_before_p1 = ?")
            params.append(balls)
        if strikes is not None:
            clauses.append("strikes_before_p1 = ?")
            params.append(strikes)
        where = " AND ".join(clauses)

        rows = con.execute(
            f"""
            SELECT pitcher AS id, player_name AS name, season,
                   pitch1_type, pitch2_type,
                   balls_before_p1, strikes_before_p1,
                   n_sequences, whiff_rate_shrunk, league_whiff_rate,
                   (whiff_rate_shrunk - league_whiff_rate) AS lift
            FROM pitcher_sequences_2pitch
            WHERE {where}
            ORDER BY lift DESC NULLS LAST
            LIMIT ?
            """,
            params + [limit],
        ).fetchall()
        cols = [
            "id", "name", "season", "pitch1_type", "pitch2_type",
            "balls_before_p1", "strikes_before_p1",
            "n_sequences", "whiff_rate_shrunk", "league_whiff_rate", "lift",
        ]
        records = [dict(zip(cols, r)) for r in rows]
    else:
        # batter role — no count slicing; batter_vs_sequences is rolled up
        rows = con.execute(
            """
            SELECT batter AS id, season, pitch1_type, pitch2_type,
                   n_sequences, whiff_rate_shrunk, league_whiff_rate,
                   (whiff_rate_shrunk - league_whiff_rate) AS lift
            FROM batter_vs_sequences
            WHERE pitch1_type = ? AND pitch2_type = ? AND season = ? AND n_sequences >= ?
            ORDER BY lift DESC NULLS LAST
            LIMIT ?
            """,
            [pitch1, pitch2, season, min_n, limit],
        ).fetchall()
        cols = [
            "id", "season", "pitch1_type", "pitch2_type",
            "n_sequences", "whiff_rate_shrunk", "league_whiff_rate", "lift",
        ]
        records = []
        for r in rows:
            rec = dict(zip(cols, r))
            rec["name"] = player_names.lookup(rec["id"])
            rec["balls_before_p1"] = None
            rec["strikes_before_p1"] = None
            records.append(rec)

    return {
        "role": role,
        "pitch1_type": pitch1,
        "pitch2_type": pitch2,
        "season": season,
        "rows": records,
    }
