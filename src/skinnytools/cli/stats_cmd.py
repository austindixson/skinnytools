"""Stats command — show compression stats from last run."""

from __future__ import annotations

import click

from skinnytools.cli.common import handle_errors
from skinnytools.config.defaults import STATS_FILE
from skinnytools.models.stats import CompressionStats


@click.command("stats")
@handle_errors
def stats_cmd() -> None:
    """Show compression stats from the last filter run."""
    if not STATS_FILE.exists():
        click.echo("No stats available. Run 'skinnytools filter' first.")
        return

    stats = CompressionStats.load(STATS_FILE)
    click.echo(stats.to_summary())
