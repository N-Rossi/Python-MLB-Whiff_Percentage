from __future__ import annotations

from typer.testing import CliRunner

from baseball.cli import app

runner = CliRunner()


def test_help_lists_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("backfill", "update", "rebuild-derived", "inspect", "query", "shell"):
        assert cmd in result.output, f"command {cmd!r} missing from --help"


def test_query_command_runs(data_root_with_pitches):
    result = runner.invoke(app, ["query", "SELECT COUNT(*) AS n FROM pitches"])
    assert result.exit_code == 0, result.output
    assert "4" in result.output


def test_inspect_pitches(data_root_with_pitches):
    result = runner.invoke(app, ["inspect", "--table", "pitches"])
    assert result.exit_code == 0, result.output
    assert "Rows: 4" in result.output
    assert "Date range:" in result.output


def test_inspect_unknown_table_exits_nonzero(data_root_with_pitches):
    result = runner.invoke(app, ["inspect", "--table", "does_not_exist"])
    assert result.exit_code != 0
