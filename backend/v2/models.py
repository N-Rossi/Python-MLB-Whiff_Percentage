"""Pydantic response models for the v2 API — one place for auto-docs + typed clients."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Player(BaseModel):
    id: int
    name: str


class PitchTypeOption(BaseModel):
    code: str
    label: str


class PitcherSequenceRow(BaseModel):
    pitcher: int
    player_name: str | None = None
    season: int
    balls_before_p1: int
    strikes_before_p1: int
    pitch1_type: str
    pitch2_type: str
    n_sequences: int
    swings_on_p2: int
    whiffs_on_p2: int
    two_strike_p2: int
    put_aways: int
    whiff_rate_raw: float | None
    whiff_rate_shrunk: float | None
    league_whiff_rate: float | None
    put_away_rate_raw: float | None
    put_away_rate_shrunk: float | None
    league_put_away_rate: float | None


class BatterSequenceRow(BaseModel):
    batter: int
    batter_name: str | None = None
    season: int
    pitch1_type: str
    pitch2_type: str
    n_sequences: int
    swings_on_p2: int
    whiffs_on_p2: int
    two_strike_p2: int
    strikeouts_on_p2: int
    whiff_rate_raw: float | None
    whiff_rate_shrunk: float | None
    league_whiff_rate: float | None
    strikeout_rate_raw: float | None
    strikeout_rate_shrunk: float | None
    league_strikeout_rate: float | None


class SequenceLeaderRow(BaseModel):
    """One row of a sequence leaderboard — either pitcher or batter role."""

    id: int = Field(description="pitcher or batter MLBAM ID, depending on role")
    name: str | None = None
    season: int
    pitch1_type: str
    pitch2_type: str
    balls_before_p1: int | None = Field(
        None, description="only populated for pitcher role (where sequences are count-sliced)"
    )
    strikes_before_p1: int | None = None
    n_sequences: int
    whiff_rate_shrunk: float | None
    league_whiff_rate: float | None
    lift: float | None = Field(None, description="whiff_rate_shrunk - league_whiff_rate")


class MatchupEdgeRow(BaseModel):
    pitcher: int
    player_name: str | None = None
    batter: int
    batter_name: str | None = None
    season: int
    pitch_type: str
    balls: int
    strikes: int
    pitcher_n: int
    pitcher_total_in_count: int
    pitcher_pct_shrunk: float | None
    batter_swings: int
    batter_whiffs: int
    league_whiff_rate: float | None
    batter_whiff_shrunk: float | None
    edge_lift: float | None
    edge_weighted: float | None


class MatchupPairing(BaseModel):
    """Scouting-card view: header + every (pitch, count) edge for one pairing."""

    pitcher: int
    player_name: str | None = None
    batter: int
    batter_name: str | None = None
    season: int
    best_pitch_type: str | None
    best_balls: int | None
    best_strikes: int | None
    best_edge_weighted: float | None
    best_edge_lift: float | None
    second_pitch_type: str | None
    second_edge_weighted: float | None
    third_pitch_type: str | None
    third_edge_weighted: float | None
    n_edge_cells: int
    pitcher_pitches_in_matched_cells: int | None
    edges: list[MatchupEdgeRow]
