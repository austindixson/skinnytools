"""Config command — show/init configuration."""

from __future__ import annotations

import json

import click

from skinnytools.cli.common import handle_errors
from skinnytools.config.loader import load_config, save_default_config


@click.group("config")
def config_cmd() -> None:
    """Manage skinnytools configuration."""


@config_cmd.command("show")
@handle_errors
def config_show() -> None:
    """Show current configuration."""
    config = load_config()
    click.echo(json.dumps(config.model_dump(), indent=2))


@config_cmd.command("init")
@handle_errors
def config_init() -> None:
    """Write default configuration file."""
    path = save_default_config()
    click.echo(f"Config written to {path}")
