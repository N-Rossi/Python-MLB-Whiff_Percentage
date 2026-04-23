from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def isolated_data_root(tmp_path, monkeypatch):
    """Point settings.data_root at a temp directory for the test's lifetime."""
    from baseball import config

    monkeypatch.setattr(config.settings, "data_root", tmp_path)
    return tmp_path


@pytest.fixture
def data_root_with_pitches(isolated_data_root):
    """Seed two synthetic month partitions so view / query tests have data to read."""
    apr = pd.DataFrame(
        {
            "game_date": pd.to_datetime(["2024-04-01", "2024-04-02", "2024-04-03"]),
            "game_pk": pd.array([1, 1, 2], dtype="Int64"),
            "pitcher": pd.array([100, 100, 200], dtype="Int64"),
            "batter": pd.array([500, 501, 502], dtype="Int64"),
            "pitch_type": ["FF", "SL", "FF"],
            "release_speed": [95.1, 86.4, 94.8],
            "description": ["ball", "swinging_strike", "called_strike"],
            "game_type": ["R", "R", "R"],
            "p_throws": ["R", "R", "L"],
            "stand": ["R", "L", "R"],
            "zone": pd.array([5, 9, 1], dtype="Int64"),
            "plate_x": [0.1, 0.5, -0.3],
            "plate_z": [2.5, 1.8, 3.1],
        }
    )
    may = pd.DataFrame(
        {
            "game_date": pd.to_datetime(["2024-05-01"]),
            "game_pk": pd.array([3], dtype="Int64"),
            "pitcher": pd.array([300], dtype="Int64"),
            "batter": pd.array([503], dtype="Int64"),
            "pitch_type": ["CH"],
            "release_speed": [82.1],
            "description": ["foul"],
            "game_type": ["R"],
            "p_throws": ["R"],
            "stand": ["L"],
            "zone": pd.array([6], dtype="Int64"),
            "plate_x": [0.2],
            "plate_z": [2.0],
        }
    )

    for month, df in [(4, apr), (5, may)]:
        part_dir = isolated_data_root / "raw" / "statcast" / "season=2024" / f"month={month:02d}"
        part_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(part_dir / "pitches.parquet", compression="zstd", index=False)

    return isolated_data_root
