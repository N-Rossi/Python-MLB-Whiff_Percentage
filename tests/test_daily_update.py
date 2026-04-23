from __future__ import annotations

import datetime as dt

import pytest

from baseball.ingest.statcast import WeekResult
from baseball.jobs import daily_update


class _Calls:
    def __init__(self) -> None:
        self.ingest_dates: list[dt.date] = []
        self.rebuild_count = 0


@pytest.fixture
def spied(monkeypatch):
    c = _Calls()

    def fake_ingest(date: dt.date, force: bool = False) -> WeekResult:
        c.ingest_dates.append(date)
        # Default: cached, no new rows. Tests override this per-scenario.
        return WeekResult(date, date, 0, 0.0, was_cached=True)

    def fake_rebuild() -> None:
        c.rebuild_count += 1

    monkeypatch.setattr(daily_update, "ingest_date", fake_ingest)
    monkeypatch.setattr(daily_update, "rebuild_all", fake_rebuild)
    return c


def test_daily_update_default_days_is_yesterday(spied):
    exit_code = daily_update.run()
    assert exit_code == 0
    # Only yesterday should have been ingested.
    assert len(spied.ingest_dates) == 1
    assert spied.ingest_dates[0] == dt.date.today() - dt.timedelta(days=1)


def test_daily_update_multi_day_catchup_in_chronological_order(spied):
    daily_update.run(days=3)
    assert len(spied.ingest_dates) == 3
    # Oldest first so logs read naturally.
    assert spied.ingest_dates == sorted(spied.ingest_dates)


def test_daily_update_skips_rebuild_when_no_fresh_rows(spied):
    daily_update.run(days=2)
    assert spied.rebuild_count == 0


def test_daily_update_triggers_rebuild_when_fresh_rows(monkeypatch, spied):
    # Override fake_ingest to report fresh rows on the second call.
    call_count = {"n": 0}

    def fake_ingest(date: dt.date, force: bool = False) -> WeekResult:
        spied.ingest_dates.append(date)
        call_count["n"] += 1
        was_cached = call_count["n"] == 1
        rows = 0 if was_cached else 1234
        return WeekResult(date, date, rows, 0.0, was_cached)

    monkeypatch.setattr(daily_update, "ingest_date", fake_ingest)
    daily_update.run(days=2)
    assert spied.rebuild_count == 1


def test_daily_update_skip_rebuild_flag_wins_over_fresh_rows(monkeypatch, spied):
    def fake_ingest(date: dt.date, force: bool = False) -> WeekResult:
        spied.ingest_dates.append(date)
        return WeekResult(date, date, 500, 0.0, was_cached=False)

    monkeypatch.setattr(daily_update, "ingest_date", fake_ingest)
    exit_code = daily_update.run(days=1, skip_rebuild=True)
    assert exit_code == 0
    assert spied.rebuild_count == 0


def test_daily_update_rejects_invalid_days(spied):
    assert daily_update.run(days=0) == 2
    assert len(spied.ingest_dates) == 0


def test_daily_update_does_not_rebuild_if_ingest_fails(monkeypatch, spied):
    def fake_ingest(date: dt.date, force: bool = False) -> WeekResult:
        spied.ingest_dates.append(date)
        raise RuntimeError("savant down")

    monkeypatch.setattr(daily_update, "ingest_date", fake_ingest)
    exit_code = daily_update.run(days=2)
    assert exit_code == 1          # failure
    assert spied.rebuild_count == 0


def test_daily_update_rebuild_failure_surfaces_nonzero_exit(monkeypatch, spied):
    def fake_ingest(date: dt.date, force: bool = False) -> WeekResult:
        spied.ingest_dates.append(date)
        return WeekResult(date, date, 500, 0.0, was_cached=False)

    def fake_rebuild_raises() -> None:
        raise RuntimeError("derived build crashed")

    monkeypatch.setattr(daily_update, "ingest_date", fake_ingest)
    monkeypatch.setattr(daily_update, "rebuild_all", fake_rebuild_raises)
    assert daily_update.run(days=1) == 1


def test_daily_update_force_is_passed_through(monkeypatch, spied):
    seen_force = {"value": None}

    def fake_ingest(date: dt.date, force: bool = False) -> WeekResult:
        seen_force["value"] = force
        return WeekResult(date, date, 0, 0.0, was_cached=True)

    monkeypatch.setattr(daily_update, "ingest_date", fake_ingest)
    daily_update.run(days=1, force=True)
    assert seen_force["value"] is True
