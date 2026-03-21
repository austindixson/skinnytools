"""Shared CLI options and utilities."""

from __future__ import annotations

import sys
from functools import wraps
from typing import Any, Callable

import click

from skinnytools.config.defaults import MAX_INPUT_SIZE


def handle_errors(fn: Callable) -> Callable:
    """Decorator that catches exceptions and prints user-friendly errors."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except KeyboardInterrupt:
            click.echo("\nInterrupted.", err=True)
            sys.exit(130)
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    return wrapper


def read_stdin() -> str:
    """Read all of stdin with a hard cap to prevent OOM."""
    if sys.stdin.isatty():
        click.echo("Reading from stdin (Ctrl+D to end)...", err=True)
    content = sys.stdin.read(MAX_INPUT_SIZE)
    if len(content) >= MAX_INPUT_SIZE:
        click.echo(
            f"Warning: input truncated at {MAX_INPUT_SIZE:,} chars",
            err=True,
        )
    return content
