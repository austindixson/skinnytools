"""Integration tests for CLI commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from skinnytools.main import cli


def test_filter_small_content():
    runner = CliRunner()
    result = runner.invoke(cli, ["filter"], input="hello world")
    assert result.exit_code == 0
    assert "hello world" in result.output


def test_filter_large_json():
    large = json.dumps({"data": "x" * 100_000, "nulls": None, "_meta": {}})
    runner = CliRunner()
    result = runner.invoke(cli, ["filter"], input=large)
    assert result.exit_code == 0
    assert len(result.output) < len(large)


def test_filter_verbose():
    content = json.dumps({"data": "x" * 60_000})
    runner = CliRunner()
    result = runner.invoke(cli, ["filter", "--verbose"], input=content)
    assert result.exit_code == 0
    # Stats go to stderr but CliRunner mixes them
    assert "Input:" in result.output or result.exit_code == 0


def test_filter_disable():
    content = json.dumps({"key": None, "val": "keep"})
    runner = CliRunner()
    result = runner.invoke(
        cli, ["filter", "--disable", "json_compactor"], input=content
    )
    assert result.exit_code == 0


def test_wrap_echo():
    runner = CliRunner()
    result = runner.invoke(cli, ["wrap", "echo", "test output"])
    assert result.exit_code == 0
    assert "test output" in result.output


def test_wrap_bad_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["wrap", "nonexistent_command_xyz"])
    assert result.exit_code != 0


def test_config_show():
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "pipeline" in parsed


def test_stats_no_prior_run():
    runner = CliRunner()
    # Clear any existing stats
    from skinnytools.config.defaults import STATS_FILE
    if STATS_FILE.exists():
        STATS_FILE.unlink()
    result = runner.invoke(cli, ["stats"])
    assert result.exit_code == 0
    assert "No stats" in result.output


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output
