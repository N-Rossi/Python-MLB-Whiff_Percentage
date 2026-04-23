from __future__ import annotations

import datetime as dt

import pandas as pd

from baseball.ingest.statcast import (
    _load_manifest,
    _save_manifest,
    _week_already_complete,
    _week_key,
    coerce_types,
    ingest_week,
    iter_weeks,
    month_partition_path,
    season_date_range,
    write_month_partition,
)


def test_iter_weeks_full_chunks():
    start = dt.date(2024, 4, 1)
    end = dt.date(2024, 4, 21)
    weeks = list(iter_weeks(start, end, chunk_days=7))
    assert weeks[0] == (dt.date(2024, 4, 1), dt.date(2024, 4, 7))
    assert weeks[1] == (dt.date(2024, 4, 8), dt.date(2024, 4, 14))
    assert weeks[-1][1] == end
    total_days = sum((b - a).days + 1 for a, b in weeks)
    assert total_days == (end - start).days + 1


def test_iter_weeks_partial_final_chunk():
    start = dt.date(2024, 4, 1)
    end = dt.date(2024, 4, 10)
    weeks = list(iter_weeks(start, end, chunk_days=7))
    assert weeks == [
        (dt.date(2024, 4, 1), dt.date(2024, 4, 7)),
        (dt.date(2024, 4, 8), dt.date(2024, 4, 10)),
    ]


def test_season_date_range():
    start, end = season_date_range(2024)
    assert start == dt.date(2024, 3, 1)
    assert end == dt.date(2024, 11, 30)


def test_coerce_types_casts_dates_and_ids():
    df = pd.DataFrame(
        {
            "game_date": ["2024-04-01", "2024-04-02"],
            "pitcher": [12345.0, 67890.0],
            "pitch_number": [1.0, 2.0],
            "release_speed": [95.2, 88.7],
        }
    )
    out = coerce_types(df)
    assert pd.api.types.is_datetime64_any_dtype(out["game_date"])
    assert out["pitcher"].dtype.name == "Int64"
    assert out["pitch_number"].dtype.name == "Int64"
    assert out["release_speed"].dtype.name == "float64"


def test_coerce_types_preserves_nullable_ids():
    df = pd.DataFrame({"pitcher": [12345.0, float("nan"), 67890.0]})
    out = coerce_types(df)
    assert out["pitcher"].dtype.name == "Int64"
    assert pd.isna(out["pitcher"].iloc[1])
    assert out["pitcher"].iloc[0] == 12345


def test_write_month_partition_round_trip(isolated_data_root):
    df = pd.DataFrame(
        {
            "game_date": pd.to_datetime(["2024-04-01", "2024-04-02"]),
            "pitcher": pd.array([12345, 67890], dtype="Int64"),
            "release_speed": [95.2, 88.7],
        }
    )
    rows = write_month_partition(df, 2024, 4)
    assert rows == 2

    path = month_partition_path(2024, 4)
    assert path.exists()
    assert path.parent.parent.name == "season=2024"
    assert path.parent.name == "month=04"
    assert path.name == "pitches.parquet"

    read_back = pd.read_parquet(path)
    assert len(read_back) == 2
    assert set(read_back["pitcher"]) == {12345, 67890}


def test_write_month_partition_replaces_overlapping_dates(isolated_data_root):
    df1 = pd.DataFrame(
        {
            "game_date": pd.to_datetime(["2024-04-01", "2024-04-02"]),
            "pitcher": pd.array([1, 2], dtype="Int64"),
        }
    )
    write_month_partition(df1, 2024, 4)

    # Re-pull April 1 with different pitcher — April 1 row should be replaced,
    # April 2 row should be untouched.
    df2 = pd.DataFrame(
        {
            "game_date": pd.to_datetime(["2024-04-01"]),
            "pitcher": pd.array([99], dtype="Int64"),
        }
    )
    write_month_partition(df2, 2024, 4)

    result = pd.read_parquet(month_partition_path(2024, 4))
    april_1 = result[result["game_date"] == pd.Timestamp("2024-04-01")]
    april_2 = result[result["game_date"] == pd.Timestamp("2024-04-02")]
    assert list(april_1["pitcher"]) == [99]
    assert list(april_2["pitcher"]) == [2]


def test_manifest_round_trip(isolated_data_root):
    m = _load_manifest()
    assert m == {"completed_weeks": {}}

    key = _week_key(dt.date(2024, 4, 1), dt.date(2024, 4, 7))
    m["completed_weeks"][key] = {"row_count": 1234, "pulled_at": "2026-04-23T00:00:00+00:00"}
    _save_manifest(m)

    m2 = _load_manifest()
    assert m2["completed_weeks"][key]["row_count"] == 1234


def test_week_already_complete_requires_partition_files(isolated_data_root):
    start, end = dt.date(2024, 4, 1), dt.date(2024, 4, 7)
    manifest = {
        "completed_weeks": {
            _week_key(start, end): {"row_count": 500, "pulled_at": "x"},
        }
    }
    # Manifest says the week is done, but no partition file exists yet.
    assert not _week_already_complete(manifest, start, end)

    # After the partition file is created, the cache check passes.
    df = pd.DataFrame(
        {
            "game_date": pd.to_datetime(["2024-04-03"]),
            "pitcher": pd.array([1], dtype="Int64"),
        }
    )
    write_month_partition(df, 2024, 4)
    assert _week_already_complete(manifest, start, end)


def test_week_already_complete_empty_week_needs_no_file(isolated_data_root):
    start, end = dt.date(2024, 4, 1), dt.date(2024, 4, 7)
    manifest = {
        "completed_weeks": {_week_key(start, end): {"row_count": 0, "pulled_at": "x"}},
    }
    assert _week_already_complete(manifest, start, end)


def test_ingest_week_writes_partition_and_updates_manifest(isolated_data_root, monkeypatch):
    # Stub out the network call so we can drive ingest_week end-to-end.
    fake_df = pd.DataFrame(
        {
            "game_date": ["2024-04-29", "2024-04-30", "2024-05-01", "2024-05-05"],
            "pitcher": [101.0, 102.0, 103.0, 104.0],
            "pitch_number": [1.0, 1.0, 1.0, 1.0],
            "release_speed": [95.0, 94.0, 93.0, 92.0],
        }
    )
    monkeypatch.setattr(
        "baseball.ingest.statcast.pull_week",
        lambda s, e: coerce_types(fake_df),
    )

    result = ingest_week(dt.date(2024, 4, 29), dt.date(2024, 5, 5))

    assert result.row_count == 4
    assert not result.was_cached

    # Week straddled April -> May, so two partitions should exist.
    apr = pd.read_parquet(month_partition_path(2024, 4))
    may = pd.read_parquet(month_partition_path(2024, 5))
    assert len(apr) == 2
    assert len(may) == 2
    assert set(apr["pitcher"]) == {101, 102}
    assert set(may["pitcher"]) == {103, 104}

    # Second call with the same week should short-circuit via the manifest.
    called = {"pull": False}

    def _should_not_be_called(s, e):
        called["pull"] = True
        return pd.DataFrame()

    monkeypatch.setattr("baseball.ingest.statcast.pull_week", _should_not_be_called)
    cached_result = ingest_week(dt.date(2024, 4, 29), dt.date(2024, 5, 5))
    assert cached_result.was_cached
    assert cached_result.row_count == 4
    assert called["pull"] is False
