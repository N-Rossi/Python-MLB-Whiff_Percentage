from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FIRST_STATCAST_SEASON = 2015

BACKFILL_CHUNK_DAYS = 7
BACKFILL_SLEEP_SECS = 0.5

PARQUET_COMPRESSION = "zstd"

REGULAR_SEASON_START_MMDD = "03-01"
REGULAR_SEASON_END_MMDD = "11-30"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="BASEBALL_",
        extra="ignore",
    )

    log_level: str = "INFO"
    duckdb_memory_limit: str | None = None
    data_root: Path = PROJECT_ROOT / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_root / "raw" / "statcast"

    @property
    def derived_dir(self) -> Path:
        return self.data_root / "derived"

    @property
    def legacy_dir(self) -> Path:
        return self.data_root / "legacy"

    def ensure_dirs(self) -> None:
        for d in (self.raw_dir, self.derived_dir, self.legacy_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
