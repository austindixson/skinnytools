"""CLI entry point for skinnytools."""

from __future__ import annotations

import click

from skinnytools.cli.analyze_cmd import analyze_cmd
from skinnytools.cli.config_cmd import config_cmd
from skinnytools.cli.filter_cmd import filter_cmd
from skinnytools.cli.stats_cmd import stats_cmd
from skinnytools.cli.wrap_cmd import wrap_cmd


@click.group()
@click.version_option(package_name="skinnytools")
def cli() -> None:
    """skinnytools — compress tool results to prevent context explosion.

    Strips recursive session blobs, compacts JSON, truncates oversized
    results, and redirects large outputs to files.
    """


cli.add_command(filter_cmd)
cli.add_command(wrap_cmd)
cli.add_command(analyze_cmd)
cli.add_command(stats_cmd)
cli.add_command(config_cmd)


if __name__ == "__main__":
    cli()
