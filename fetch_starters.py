"""
Pull Statcast pitch-by-pitch data for every starter in a chosen MLB
division who started more than 3 games, and cache it to CSV.

Source: Baseball Savant only. Fangraphs and Baseball Reference scrapers
are currently broken/blocked, so we derive the starter list directly
from Statcast instead of relying on a third-party stat source.

Usage:
    python fetch_starters.py nl_east
    python fetch_starters.py al_west
    python fetch_starters.py all          # iterate every division

Output (one set of files per division, written to ./data/):
    data/{division}_starters_{SEASON}_roster.csv   -- one row per pitcher
    data/{division}_starters_{SEASON}_pitches.csv  -- one row per pitch
"""

from pathlib import Path
import datetime as dt
import sys
import time

import pandas as pd
from pybaseball import statcast, cache

cache.enable()

# Statcast team abbreviations. Note: Athletics still appear as 'OAK' in
# Statcast even after the Sacramento move; if a future season changes that,
# update here.
DIVISIONS = {
    "al_east":    {"BAL", "BOS", "NYY", "TB",  "TOR"},
    "al_central": {"CWS", "CLE", "DET", "KC",  "MIN"},
    "al_west":    {"HOU", "LAA", "OAK", "SEA", "TEX"},
    "nl_east":    {"ATL", "MIA", "NYM", "PHI", "WSH"},
    "nl_central": {"CHC", "CIN", "MIL", "PIT", "STL"},
    "nl_west":    {"ARI", "COL", "LAD", "SD",  "SF"},
}

SEASON = 2025
MIN_GAMES_STARTED = 3  # "more than 3"
SEASON_START = f"{SEASON}-03-01"
SEASON_END = f"{SEASON}-11-30"

OUT_DIR = Path(__file__).parent / "data"


def _date_chunks(start, end, days=14):
    """Yield (start_iso, end_iso) windows of `days` length."""
    cur = dt.date.fromisoformat(start)
    final = dt.date.fromisoformat(end)
    while cur <= final:
        nxt = min(cur + dt.timedelta(days=days - 1), final)
        yield cur.isoformat(), nxt.isoformat()
        cur = nxt + dt.timedelta(days=1)


def pull_division_statcast(teams):
    """
    Pull pitches per team in 2-week windows with per-window error handling.
    The bulk statcast() call is fragile — if any single day chunk comes back
    as junk (Savant occasionally returns an HTML error page), pybaseball's
    parallel pipeline crashes the whole pull. Doing our own chunking lets us
    skip a bad window and keep going.
    """
    frames = []
    for team in sorted(teams):
        print(f"\n--- {team} ---")
        team_frames = []
        for s, e in _date_chunks(SEASON_START, SEASON_END, days=14):
            try:
                df = statcast(s, e, team=team, verbose=False)
            except Exception as ex:
                print(f"  {s}..{e} FAILED ({ex.__class__.__name__}: {ex}); skipping")
                continue
            if df is None or df.empty:
                continue
            # statcast(team=...) returns games *involving* the team — keep
            # only the rows where this team was actually pitching.
            pitching_team = df["home_team"].where(df["inning_topbot"] == "Top", df["away_team"])
            df = df[pitching_team == team]
            if df.empty:
                continue
            team_frames.append(df)
            print(f"  {s}..{e}: {len(df):,} pitches")
            time.sleep(0.3)  # be polite to Savant
        if team_frames:
            frames.append(pd.concat(team_frames, ignore_index=True))

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    print(f"\nTotal pitches pulled: {len(out):,}")
    return out


def identify_starters(df, teams):
    """
    Return (roster_df, division_pitches_df).
    A "start" = being the pitcher in at_bat_number == 1 of a game for the
    pitching team.
    """
    df = df.copy()
    df["pitching_team"] = df["home_team"].where(df["inning_topbot"] == "Top", df["away_team"])
    div_pitches = df[df["pitching_team"].isin(teams)]

    first_ab = div_pitches[div_pitches["at_bat_number"] == 1]
    starters_per_game = (
        first_ab.groupby(["game_pk", "pitching_team"])["pitcher"]
        .first()
        .reset_index()
    )

    counts = (
        starters_per_game.groupby(["pitcher", "pitching_team"])
        .size()
        .reset_index(name="GS")
    )

    roster = (
        counts.groupby("pitcher", as_index=False)
        .agg(Team=("pitching_team", lambda x: ",".join(sorted(set(x)))),
             GS=("GS", "sum"))
    )
    roster = roster[roster["GS"] > MIN_GAMES_STARTED]

    name_map = (
        div_pitches.drop_duplicates("pitcher")
        .set_index("pitcher")["player_name"]
        .to_dict()
    )
    roster["Name"] = roster["pitcher"].map(name_map)
    roster = roster.rename(columns={"pitcher": "mlbam_id"})
    roster = roster[["Name", "mlbam_id", "Team", "GS"]].sort_values(
        ["Team", "GS"], ascending=[True, False]
    )
    return roster, div_pitches


def fetch_division(division):
    """Fetch and cache pitch data for one division."""
    if division not in DIVISIONS:
        print(f"Unknown division: {division!r}. Choices: {sorted(DIVISIONS)}")
        sys.exit(1)

    teams = DIVISIONS[division]
    roster_csv = OUT_DIR / f"{division}_starters_{SEASON}_roster.csv"
    pitches_csv = OUT_DIR / f"{division}_starters_{SEASON}_pitches.csv"

    print(f"=== Fetching {division.upper()} ({sorted(teams)}) ===")
    df = pull_division_statcast(teams)
    if df is None or df.empty:
        print(f"No Statcast data returned for {division}. Skipping.")
        return

    roster, div_pitches = identify_starters(df, teams)
    print(f"\nFound {len(roster)} {division.upper()} starters with GS > {MIN_GAMES_STARTED}:")
    print(roster.to_string(index=False))

    # Tag rows with the division so the analyze script can filter by it
    roster["division"] = division
    roster.to_csv(roster_csv, index=False)
    print(f"\nWrote roster -> {roster_csv}")

    pitches = div_pitches[div_pitches["pitcher"].isin(roster["mlbam_id"])].copy()
    name_map = roster.set_index("mlbam_id")["Name"].to_dict()
    pitches["pitcher_name"] = pitches["pitcher"].map(name_map)
    pitches["division"] = division

    pitches.to_csv(pitches_csv, index=False)
    print(f"\nWrote {len(pitches):,} pitches across {pitches['pitcher'].nunique()} pitchers")
    print(f"  -> {pitches_csv}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) < 2:
        print(f"Usage: python {Path(__file__).name} <division|all>")
        print(f"Choices: {sorted(DIVISIONS)} | all")
        sys.exit(1)

    target = sys.argv[1].lower()
    if target == "all":
        for div in DIVISIONS:
            fetch_division(div)
    else:
        fetch_division(target)


if __name__ == "__main__":
    main()
