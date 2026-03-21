"""Analyze command — diagnose bloat in session files."""

from __future__ import annotations

import json
from pathlib import Path

import click

from skinnytools.cli.common import handle_errors
from skinnytools.core.patterns import PATTERNS
from skinnytools.utils.text import format_size


@click.command("analyze")
@click.argument("file", type=click.Path(exists=True))
@handle_errors
def analyze_cmd(file: str) -> None:
    """Analyze a session file for context bloat."""
    path = Path(file)
    raw = path.read_text()
    total_size = len(raw)

    click.echo(f"File: {path.name}")
    click.echo(f"Total size: {format_size(total_size)} chars")
    click.echo()

    # Try to parse as JSONL (one JSON object per line)
    tool_results = _extract_tool_results_jsonl(raw)
    if not tool_results:
        # Try as single JSON
        tool_results = _extract_tool_results_json(raw)

    if not tool_results:
        click.echo("No tool results found. Checking for general bloat...")
        _report_pattern_matches(raw)
        return

    click.echo(f"Tool results found: {len(tool_results)}")

    # Size distribution
    sizes = sorted(
        [(size, idx) for idx, (_, size) in enumerate(tool_results)],
        reverse=True,
    )
    total_result_chars = sum(s for s, _ in sizes)
    click.echo(f"Total tool result chars: {format_size(total_result_chars)}")
    click.echo()

    # Top 10 largest
    click.echo("Top 10 largest tool results:")
    for i, (size, idx) in enumerate(sizes[:10]):
        pct = size / total_size * 100
        click.echo(f"  {i+1}. Entry {idx}: {format_size(size)} ({pct:.1f}%)")

    click.echo()
    _report_pattern_matches(raw)

    # Compression estimate
    estimated_savings = sum(
        size for size, _ in sizes if size > 50_000
    )
    click.echo()
    click.echo(f"Estimated compression potential: {format_size(estimated_savings)} chars")
    click.echo(
        f"  ({estimated_savings / total_size * 100:.1f}% of total)"
    )


def _extract_tool_results_jsonl(raw: str) -> list[tuple[str, int]]:
    """Extract tool results from JSONL format."""
    results: list[tuple[str, int]] = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        _find_tool_results(obj, results)
    return results


def _extract_tool_results_json(raw: str) -> list[tuple[str, int]]:
    """Extract tool results from a single JSON object."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return []
    results: list[tuple[str, int]] = []
    _find_tool_results(obj, results)
    return results


def _find_tool_results(
    obj: object, results: list[tuple[str, int]]
) -> None:
    """Recursively find toolResult / tool_result entries."""
    if isinstance(obj, dict):
        for key in ("toolResult", "tool_result", "content"):
            if key in obj:
                val = obj[key]
                serialized = json.dumps(val)
                if len(serialized) > 100:
                    results.append((serialized, len(serialized)))
        for v in obj.values():
            _find_tool_results(v, results)
    elif isinstance(obj, list):
        for item in obj:
            _find_tool_results(item, results)


def _report_pattern_matches(raw: str) -> None:
    """Report recursive pattern matches found in raw text."""
    click.echo("Recursive content detection:")
    found_any = False
    for pattern in PATTERNS:
        matches = list(pattern.regex.finditer(raw))
        valid = [m for m in matches if len(m.group(0)) >= pattern.min_match_size]
        if valid:
            total_chars = sum(len(m.group(0)) for m in valid)
            click.echo(
                f"  {pattern.name}: {len(valid)} matches, "
                f"{format_size(total_chars)} chars"
            )
            found_any = True
    if not found_any:
        click.echo("  (none detected)")
