import datetime as dt
import sys

import typer

if sys.platform == "win32":
    # Windows consoles default to cp1252 and mangle Unicode (e.g., "Rodón" -> "Rod�n").
    # Python 3.7+ has reconfigure(); ignore failures on exotic streams.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

app = typer.Typer(
    name="baseball",
    help="Data infrastructure for MLB pitch analytics.",
    no_args_is_help=True,
)


@app.command()
def backfill(
    start_season: int = typer.Option(2015, "--start-season"),
    end_season: int = typer.Option(dt.date.today().year, "--end-season"),
    force: bool = typer.Option(False, "--force", help="Re-pull weeks already cached on disk"),
) -> None:
    """Backfill Statcast pitch data for a range of seasons."""
    from baseball.ingest.backfill import run_backfill

    run_backfill(start_season=start_season, end_season=end_season, force=force)


@app.command()
def update(
    date: str | None = typer.Option(None, "--date", help="YYYY-MM-DD; defaults to yesterday"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Pull a single day of Statcast data (nightly in-season refresh)."""
    from baseball.ingest.statcast import ingest_date

    target = dt.date.fromisoformat(date) if date else (dt.date.today() - dt.timedelta(days=1))
    ingest_date(target, force=force)


@app.command("rebuild-derived")
def rebuild_derived(
    table: str | None = typer.Option(None, "--table", help="Rebuild only this table"),
) -> None:
    """Rebuild derived Parquet tables from raw pitch data."""
    raise NotImplementedError


_DIAGNOSTIC_NULL_COLUMNS = (
    "pitch_type",
    "release_speed",
    "zone",
    "description",
    "game_type",
    "p_throws",
    "stand",
    "plate_x",
    "plate_z",
)


@app.command()
def inspect(
    table: str = typer.Option(..., "--table"),
    season: int | None = typer.Option(None, "--season"),
) -> None:
    """Row counts, date coverage, and null-rate diagnostics for a table."""
    from baseball.storage.duckdb_conn import (
        get_connection,
        list_tables,
        register_views,
        table_columns,
    )

    con = get_connection()
    register_views(con)

    if table not in list_tables(con):
        typer.echo(f"Table {table!r} not registered. Available: {list_tables(con)}", err=True)
        raise typer.Exit(code=1)

    cols = table_columns(con, table)
    where = f"WHERE season = {season}" if season and "season" in cols else ""
    if season and "season" not in cols:
        typer.echo(f"Warning: table {table!r} has no `season` column; ignoring --season", err=True)

    row_count = con.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
    typer.echo(f"Table: {table}")
    if where:
        typer.echo(f"Season filter: {season}")
    typer.echo(f"Rows: {row_count:,}")

    if "game_pk" in cols and "game_date" in cols:
        games, first, last = con.execute(
            f"SELECT COUNT(DISTINCT game_pk), MIN(game_date)::DATE, MAX(game_date)::DATE "
            f"FROM {table} {where}"
        ).fetchone()
        typer.echo(f"Games: {games:,}")
        typer.echo(f"Date range: {first} .. {last}")

    if "pitcher" in cols:
        pitchers = con.execute(f"SELECT COUNT(DISTINCT pitcher) FROM {table} {where}").fetchone()[0]
        typer.echo(f"Unique pitchers: {pitchers:,}")
    if "batter" in cols:
        batters = con.execute(f"SELECT COUNT(DISTINCT batter) FROM {table} {where}").fetchone()[0]
        typer.echo(f"Unique batters: {batters:,}")

    null_targets = [c for c in _DIAGNOSTIC_NULL_COLUMNS if c in cols]
    if null_targets and row_count > 0:
        parts = [
            f"SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END)::DOUBLE / COUNT(*) AS {c}"
            for c in null_targets
        ]
        rates = con.execute(f"SELECT {', '.join(parts)} FROM {table} {where}").fetchone()
        typer.echo("\nNull rates:")
        for col, rate in zip(null_targets, rates):
            typer.echo(f"  {col:<20} {rate:>7.2%}")


def _print_df(df) -> None:
    import pandas as pd

    if df is None or len(df.columns) == 0:
        typer.echo("(ok)")
        return
    if len(df) == 0:
        typer.echo("(0 rows)")
        return
    with pd.option_context(
        "display.max_rows", 100,
        "display.max_columns", None,
        "display.width", None,
        "display.max_colwidth", 40,
    ):
        typer.echo(df.to_string(index=False))
    if len(df) > 100:
        typer.echo(f"\n({len(df):,} rows — showing first 100)")


@app.command()
def query(sql: str) -> None:
    """Run an ad-hoc DuckDB SQL query against the pitch data."""
    from baseball.storage.duckdb_conn import get_connection, register_views

    con = get_connection()
    register_views(con)
    _print_df(con.execute(sql).fetchdf())


@app.command()
def shell() -> None:
    """Interactive SQL prompt. Think `psql` for DuckDB, with views pre-registered."""
    from baseball.storage.duckdb_conn import get_connection, list_tables, register_views

    # readline (or pyreadline3 on Windows) gives us history + line editing if available.
    try:
        import readline  # noqa: F401
    except ImportError:
        try:
            import pyreadline3  # noqa: F401
        except ImportError:
            pass

    con = get_connection()
    register_views(con)
    tables = list_tables(con)

    if tables:
        typer.echo(f"Connected. Tables: {', '.join(tables)}")
    else:
        typer.echo("Connected. No tables registered yet — run `baseball backfill` first.")
    typer.echo(
        "Type SQL (terminate with ;).  "
        r"\d TABLE for schema, \dt for table list, \q to quit."
    )
    typer.echo()

    buffer: list[str] = []
    while True:
        prompt = "baseball> " if not buffer else "       -> "
        try:
            line = input(prompt)
        except EOFError:
            typer.echo()
            return
        except KeyboardInterrupt:
            typer.echo()
            buffer = []
            continue

        stripped = line.strip()
        if not stripped and not buffer:
            continue

        if stripped in (r"\q", "exit", "quit"):
            return

        if stripped == r"\dt":
            for t in list_tables(con):
                typer.echo(f"  {t}")
            continue

        if stripped.startswith(r"\d"):
            parts = stripped.split(maxsplit=1)
            if len(parts) == 1:
                for t in list_tables(con):
                    typer.echo(f"  {t}")
                continue
            try:
                _print_df(con.execute(f"DESCRIBE {parts[1]}").fetchdf())
            except Exception as ex:
                typer.echo(f"Error: {ex}")
            continue

        buffer.append(line)
        joined = "\n".join(buffer).rstrip()
        if not joined.endswith(";"):
            continue

        sql = joined.rstrip(";").strip()
        buffer = []
        if not sql:
            continue

        try:
            _print_df(con.execute(sql).fetchdf())
        except KeyboardInterrupt:
            typer.echo("\n(interrupted)")
        except Exception as ex:
            typer.echo(f"Error: {ex}")


if __name__ == "__main__":
    app()
