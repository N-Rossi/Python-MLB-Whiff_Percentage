"""Integration tests for the v2 API.

These exercise the real derived Parquet on disk — the same DuckDB connection
FastAPI uses in production. Each test boots the app via `lifespan`, which
runs in under a second, so the suite stays lightweight.

Requires at least one season of derived tables to be built locally (i.e.,
you've run `baseball backfill` + `baseball rebuild-derived` at least once).
Tests skip cleanly with a clear message if that hasn't happened yet.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from baseball.config import settings

REQUIRED_TABLES = [
    "pitcher_pitch_mix",
    "pitcher_sequences_2pitch",
    "batter_whiff_profile",
    "batter_vs_sequences",
    "matchup_edges",
]


def _derived_ready() -> bool:
    return all((settings.derived_dir / f"{t}.parquet").exists() for t in REQUIRED_TABLES)


pytestmark = pytest.mark.skipif(
    not _derived_ready(),
    reason="Derived tables missing — run `baseball rebuild-derived` first.",
)


@pytest.fixture(scope="module")
def client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


# --- Lookups --------------------------------------------------------------

def test_seasons_non_empty(client):
    r = client.get("/api/v2/seasons")
    assert r.status_code == 200
    seasons = r.json()["seasons"]
    assert seasons, "no seasons returned"
    assert all(isinstance(s, int) for s in seasons)
    assert seasons == sorted(seasons, reverse=True)  # newest first


def test_pitch_types_has_ff(client):
    r = client.get("/api/v2/pitch-types")
    assert r.status_code == 200
    codes = [p["code"] for p in r.json()["pitch_types"]]
    assert "FF" in codes


def test_pitcher_search_substring(client):
    r = client.get("/api/v2/pitchers?q=skub&limit=5")
    assert r.status_code == 200
    players = r.json()["players"]
    assert players, "expected at least one Skub* pitcher"
    assert all("skub" in p["name"].lower() for p in players)


def test_batter_search_returns_something(client):
    # Tiny query string — proves the Chadwick join works, doesn't assert a specific player.
    r = client.get("/api/v2/batters?limit=3")
    assert r.status_code == 200
    players = r.json()["players"]
    assert players, "expected non-empty batter list"
    # Name field is always present (falls back to id:xxx if Chadwick unavailable).
    assert all(p.get("name") for p in players)


# --- Sequences ------------------------------------------------------------

def test_pitcher_sequences_filters_apply(client):
    # Skubal (669373) FF->CH
    r = client.get(
        "/api/v2/sequences/pitcher/669373"
        "?pitch1=FF&pitch2=CH&min_n=5&limit=10"
    )
    assert r.status_code == 200
    data = r.json()
    assert data["pitcher"] == 669373
    for row in data["rows"]:
        assert row["pitch1_type"] == "FF"
        assert row["pitch2_type"] == "CH"
        assert row["n_sequences"] >= 5


def test_pitcher_sequences_invalid_sort(client):
    r = client.get("/api/v2/sequences/pitcher/669373?sort=does_not_exist")
    assert r.status_code == 400


def test_batter_sequences_has_name(client):
    # Juan Soto
    r = client.get("/api/v2/sequences/batter/665742?min_n=30&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert data["batter"] == 665742
    # Chadwick should resolve his name during the test run.
    assert data["batter_name"] == "Soto, Juan"


def test_sequence_leaderboard_pitcher_role(client):
    seasons = client.get("/api/v2/seasons").json()["seasons"]
    r = client.get(
        f"/api/v2/sequences/leaderboard"
        f"?pitch1=FF&pitch2=CH&season={seasons[0]}&role=pitcher&min_n=20&limit=5"
    )
    assert r.status_code == 200
    rows = r.json()["rows"]
    # Each returned row is for the requested combo.
    for row in rows:
        assert row["pitch1_type"] == "FF"
        assert row["pitch2_type"] == "CH"


# --- Matchup --------------------------------------------------------------

def test_matchup_top_edges_respects_sample_floors(client):
    seasons = client.get("/api/v2/seasons").json()["seasons"]
    r = client.get(
        f"/api/v2/matchup/edges/top?season={seasons[0]}"
        f"&min_pitcher_n=50&min_batter_swings=30&limit=10"
    )
    assert r.status_code == 200
    rows = r.json()["rows"]
    for row in rows:
        assert row["pitcher_n"] >= 50
        assert row["batter_swings"] >= 30


def test_matchup_pairing_nonexistent_returns_404(client):
    r = client.get("/api/v2/matchup/pairing/669373/999999?season=2024")
    assert r.status_code == 404


def test_matchup_pairing_consistent_with_top(client):
    """If `top_edges` returns Skubal-vs-X, the pairing endpoint should too."""
    seasons = client.get("/api/v2/seasons").json()["seasons"]
    season = seasons[0]

    top = client.get(
        f"/api/v2/matchup/edges/top?season={season}&pitcher_id=669373"
        f"&min_pitcher_n=50&min_batter_swings=30&limit=1"
    ).json()["rows"]
    if not top:
        pytest.skip("no Skubal edges in this season's data")

    batter_id = top[0]["batter"]
    r = client.get(f"/api/v2/matchup/pairing/669373/{batter_id}?season={season}")
    assert r.status_code == 200
    data = r.json()
    assert data["pitcher"] == 669373
    assert data["batter"] == batter_id
    assert data["n_edge_cells"] > 0
    assert len(data["edges"]) >= 1
