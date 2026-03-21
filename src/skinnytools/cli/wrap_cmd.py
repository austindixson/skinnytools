"""Wrap command — execute a command and filter its output."""

from __future__ import annotations

import subprocess

import click

from skinnytools.cli.common import handle_errors
from skinnytools.config.defaults import STATS_FILE
from skinnytools.config.loader import load_config, merge_cli_overrides
from skinnytools.core.budget import BudgetTracker
from skinnytools.core.pipeline import process


@click.command("wrap")
@click.argument("command", nargs=-1, required=True)
@click.option("--max-size", type=int, default=None, help="Max output size in chars")
@click.option("--budget", type=int, default=None, help="Token budget")
@click.option("--disable", multiple=True, help="Disable a filter by name")
@click.option("--verbose", is_flag=True, help="Print stats to stderr")
@click.option("--timeout", type=int, default=120, help="Command timeout in seconds")
@handle_errors
def wrap_cmd(
    command: tuple[str, ...],
    max_size: int | None,
    budget: int | None,
    disable: tuple[str, ...],
    verbose: bool,
    timeout: int,
) -> None:
    """Execute a command and filter its output."""
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        click.echo(f"[Command timed out after {timeout}s]", err=True)
        raise SystemExit(1)
    except FileNotFoundError:
        click.echo(f"[Command not found: {command[0]}]", err=True)
        raise SystemExit(1)

    # Combine stdout and stderr
    content = result.stdout
    if result.returncode != 0 and result.stderr:
        content += f"\n[stderr, exit={result.returncode}]:\n{result.stderr}"

    config = load_config()
    pipeline_config = merge_cli_overrides(
        config.pipeline,
        max_size=max_size,
        budget=budget,
        disable=disable,
        verbose=verbose,
    )

    tracker = BudgetTracker(total_budget=pipeline_config.token_budget)
    filtered, stats = process(content, pipeline_config, tracker)

    click.echo(filtered, nl=False)

    if verbose or pipeline_config.verbose:
        click.echo("\n" + stats.to_summary(), err=True)

    try:
        stats.save(STATS_FILE)
    except OSError:
        pass
