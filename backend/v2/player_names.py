"""
MLBAM ID → 'Last, First' name lookup for batters.

Pitcher names are carried directly in the derived tables (`player_name`
column), so this module is only needed on the batter side. Names come from
Chadwick Bureau's public player register via pybaseball, cached to
`data/player_names.parquet` after the first run.

If the cache can't be built (no network at first startup), we fall back to
an empty dict — endpoints still work but batter names show as `"id:665742"`
instead of "Soto, Juan". The cache is built lazily on first `_load_names()`
call, so startup never blocks on it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from loguru import logger

from baseball.config import settings

CACHE_PATH: Path = settings.data_root / "player_names.parquet"


def _build_cache() -> None:
    """Fetch Chadwick Bureau and write the trimmed lookup to disk."""
    import pandas as pd
    from pybaseball import chadwick_register

    logger.info("Fetching Chadwick Bureau player register (first run, ~1 min)")
    df = chadwick_register(save=False)
    df = df.dropna(subset=["key_mlbam"]).copy()
    df["key_mlbam"] = df["key_mlbam"].astype(int)
    df = df[["key_mlbam", "name_first", "name_last"]]

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_PATH, index=False)
    logger.info(f"Cached {len(df):,} player names to {CACHE_PATH}")


@lru_cache(maxsize=1)
def _load_names() -> dict[int, str]:
    """Return MLBAM ID → 'Last, First'. Empty dict if the cache can't be built."""
    try:
        if not CACHE_PATH.exists():
            _build_cache()
        import pandas as pd

        df = pd.read_parquet(CACHE_PATH)
    except Exception as e:  # noqa: BLE001 — degrade gracefully, never crash the API
        logger.warning(f"Player name lookup unavailable: {e!r}")
        return {}

    names: dict[int, str] = {}
    for row in df.itertuples(index=False):
        first = row.name_first if isinstance(row.name_first, str) else ""
        last = row.name_last if isinstance(row.name_last, str) else ""
        if not (first or last):
            continue
        names[int(row.key_mlbam)] = f"{last}, {first}".strip(", ")
    return names


def lookup(mlbam_id: int | None) -> str | None:
    """Return 'Last, First' or None if the ID isn't in the register."""
    if mlbam_id is None:
        return None
    return _load_names().get(int(mlbam_id))


def search(query: str | None, ids: set[int], limit: int = 20) -> list[dict]:
    """Case-insensitive substring search restricted to `ids`.

    Returns a list of {"id": int, "name": str} sorted alphabetically by name.
    If `query` is empty/None, returns the first `limit` names from `ids`.
    """
    q = (query or "").lower().strip()
    names = _load_names()

    matches: list[tuple[int, str]] = []
    for mlbam_id in ids:
        name = names.get(int(mlbam_id))
        if not name:
            continue
        if q and q not in name.lower():
            continue
        matches.append((int(mlbam_id), name))

    matches.sort(key=lambda pair: pair[1])
    return [{"id": mid, "name": name} for mid, name in matches[:limit]]
