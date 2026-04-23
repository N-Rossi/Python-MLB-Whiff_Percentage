"""
Pitcher × batter matchup edges endpoints.

- `GET /matchup/pairing/{pitcher_id}/{batter_id}` — full scouting card for one pair.
- `GET /matchup/edges/top` — general top-N over `matchup_edges` with filters.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from backend.v2 import player_names
from backend.v2.constants import DEFAULT_MIN_BATTER_SWINGS, DEFAULT_MIN_PITCHER_N
from backend.v2.db import CursorDep
from backend.v2.models import MatchupEdgeRow, MatchupPairing

router = APIRouter()


_EDGE_COLS = [
    "pitcher", "player_name", "batter", "season", "pitch_type", "balls", "strikes",
    "pitcher_n", "pitcher_total_in_count", "pitcher_pct_shrunk",
    "batter_swings", "batter_whiffs", "league_whiff_rate", "batter_whiff_shrunk",
    "edge_lift", "edge_weighted",
]


def _edges_to_records(rows) -> list[dict]:
    records = []
    for r in rows:
        rec = dict(zip(_EDGE_COLS, r))
        rec["batter_name"] = player_names.lookup(rec["batter"])
        records.append(rec)
    return records


# --- Pairing scouting card ------------------------------------------------

@router.get(
    "/matchup/pairing/{pitcher_id}/{batter_id}",
    response_model=MatchupPairing,
)
def matchup_pairing(
    pitcher_id: int = Path(...),
    batter_id: int = Path(...),
    season: int = Query(..., description="Season to scout"),
    min_pitcher_n: int = Query(
        0, ge=0, description="Hide rows where the pitcher threw this pitch+count rarely"
    ),
    min_batter_swings: int = Query(0, ge=0),
    con=CursorDep,
):
    """One pair, one season: every (pitch, count) edge sorted by leverage,
    plus the summary row from `matchup_edges_top`."""

    top = con.execute(
        """
        SELECT pitcher, player_name, batter, season,
               best_pitch_type, best_balls, best_strikes,
               best_edge_weighted, best_edge_lift,
               second_pitch_type, second_edge_weighted,
               third_pitch_type, third_edge_weighted,
               n_edge_cells, pitcher_pitches_in_matched_cells
        FROM matchup_edges_top
        WHERE pitcher = ? AND batter = ? AND season = ?
        """,
        [pitcher_id, batter_id, season],
    ).fetchone()

    if not top:
        raise HTTPException(
            404,
            detail=(
                f"No matchup rows for pitcher {pitcher_id} vs batter {batter_id} "
                f"in season {season}. They may not have faced each other, or the "
                f"filter/sample cut dropped everything."
            ),
        )

    edges_rows = con.execute(
        f"""
        SELECT {", ".join(_EDGE_COLS)}
        FROM matchup_edges
        WHERE pitcher = ? AND batter = ? AND season = ?
          AND pitcher_n >= ? AND batter_swings >= ?
        ORDER BY edge_weighted DESC NULLS LAST
        """,
        [pitcher_id, batter_id, season, min_pitcher_n, min_batter_swings],
    ).fetchall()

    batter_name = player_names.lookup(batter_id)
    return {
        "pitcher": int(top[0]),
        "player_name": top[1],
        "batter": int(top[2]),
        "batter_name": batter_name,
        "season": int(top[3]),
        "best_pitch_type": top[4],
        "best_balls": top[5],
        "best_strikes": top[6],
        "best_edge_weighted": top[7],
        "best_edge_lift": top[8],
        "second_pitch_type": top[9],
        "second_edge_weighted": top[10],
        "third_pitch_type": top[11],
        "third_edge_weighted": top[12],
        "n_edge_cells": int(top[13]),
        "pitcher_pitches_in_matched_cells": top[14],
        "edges": _edges_to_records(edges_rows),
    }


# --- Top edges (general-purpose leaderboard) -------------------------------

TOP_SORT_COLS = {
    "edge_weighted": "edge_weighted",
    "edge_lift": "edge_lift",
    "batter_whiff_shrunk": "batter_whiff_shrunk",
    "pitcher_n": "pitcher_n",
    "batter_swings": "batter_swings",
}


def _top_edges_order_by(sort: str, perspective: str) -> str:
    """Build the ORDER BY for /matchup/edges/top.

    - pitcher perspective: DESC (pitcher's biggest leverage first)
    - batter perspective:  ASC  (most negative weighted first — where the
      batter whiffs less than league, weighted by how often the pitcher
      throws it there). Sample-size columns (pitcher_n, batter_swings)
      always sort DESC regardless — "biggest sample" is perspective-neutral.
    """
    col = TOP_SORT_COLS[sort]
    if sort in ("pitcher_n", "batter_swings"):
        return f"{col} DESC"
    direction = "ASC" if perspective == "batter" else "DESC"
    return f"{col} {direction} NULLS LAST"


class EdgesTopResponse(BaseModel):
    rows: list[MatchupEdgeRow]


@router.get("/matchup/edges/top", response_model=EdgesTopResponse)
def top_edges(
    season: int = Query(...),
    pitcher_id: int | None = Query(None, description="Restrict to one pitcher"),
    batter_id: int | None = Query(None, description="Restrict to one batter"),
    pitch_type: str | None = Query(None),
    balls: int | None = Query(None, ge=0, le=3),
    strikes: int | None = Query(None, ge=0, le=2),
    min_pitcher_n: int = Query(DEFAULT_MIN_PITCHER_N, ge=0),
    min_batter_swings: int = Query(DEFAULT_MIN_BATTER_SWINGS, ge=0),
    sort: str = Query("edge_weighted", description=f"One of: {list(TOP_SORT_COLS)}"),
    perspective: str = Query(
        "pitcher",
        pattern="^(pitcher|batter)$",
        description=(
            "'pitcher' surfaces the pitcher's highest-leverage pitches "
            "(edge_weighted DESC). 'batter' surfaces the batter's best "
            "spots — pitches thrown often where the batter whiffs less "
            "than league (edge_weighted ASC). Sample-size sorts are "
            "unaffected."
        ),
    ),
    limit: int = Query(50, ge=1, le=500),
    con=CursorDep,
):
    """Top matchup edges across the league for a season, with any filters.

    With no pitcher/batter filter this scans all ~35M edge rows. Sample-size
    floors (`min_pitcher_n`, `min_batter_swings`) are applied server-side so
    the result is bounded and meaningful."""
    if sort not in TOP_SORT_COLS:
        raise HTTPException(400, detail=f"Invalid sort. Options: {list(TOP_SORT_COLS)}")

    clauses = ["season = ?", "pitcher_n >= ?", "batter_swings >= ?"]
    params: list = [season, min_pitcher_n, min_batter_swings]

    if pitcher_id is not None:
        clauses.append("pitcher = ?")
        params.append(pitcher_id)
    if batter_id is not None:
        clauses.append("batter = ?")
        params.append(batter_id)
    if pitch_type:
        clauses.append("pitch_type = ?")
        params.append(pitch_type)
    if balls is not None:
        clauses.append("balls = ?")
        params.append(balls)
    if strikes is not None:
        clauses.append("strikes = ?")
        params.append(strikes)
    where = " AND ".join(clauses)

    rows = con.execute(
        f"""
        SELECT {", ".join(_EDGE_COLS)}
        FROM matchup_edges
        WHERE {where}
        ORDER BY {_top_edges_order_by(sort, perspective)}
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()

    return {"rows": _edges_to_records(rows)}
