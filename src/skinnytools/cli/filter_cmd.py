"""Filter command — pipe mode: stdin → filtered stdout."""

from __future__ import annotations

import click

from skinnytools.cli.common import handle_errors, read_stdin
from skinnytools.config.defaults import FAST_PATH_THRESHOLD, STATS_FILE
from skinnytools.config.loader import load_config, merge_cli_overrides
from skinnytools.core.budget import BudgetTracker
from skinnytools.core.pipeline import process


@click.command("filter")
@click.option("--max-size", type=int, default=None, help="Max output size in chars")
@click.option("--budget", type=int, default=None, help="Token budget")
@click.option("--disable", multiple=True, help="Disable a filter by name")
@click.option("--verbose", is_flag=True, help="Print stats to stderr")
@handle_errors
def filter_cmd(
    max_size: int | None,
    budget: int | None,
    disable: tuple[str, ...],
    verbose: bool,
) -> None:
    """Read stdin, filter tool output, write to stdout."""
    content = read_stdin()

    # Fast path: small content passes through
    if len(content) <= FAST_PATH_THRESHOLD:
        click.echo(content, nl=False)
        return

    config = load_config()
    pipeline_config = merge_cli_overrides(
        config.pipeline,
        max_size=max_size,
        budget=budget,
        disable=disable,
        verbose=verbose,
    )

    tracker = BudgetTracker(
        total_budget=pipeline_config.token_budget,
    )

    filtered, stats = process(content, pipeline_config, tracker)

    click.echo(filtered, nl=False)

    if verbose or pipeline_config.verbose:
        click.echo("\n" + stats.to_summary(), err=True)

    # Persist stats for `skinnytools stats`
    try:
        stats.save(STATS_FILE)
    except OSError:
        pass  # non-critical
