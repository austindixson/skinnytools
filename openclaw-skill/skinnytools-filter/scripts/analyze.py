#!/usr/bin/env python3
"""Analyze a session file for context bloat.

Usage:
    python3 analyze.py /path/to/session.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKINNYTOOLS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(SKINNYTOOLS_ROOT, "src"))

from skinnytools.core.patterns import PATTERNS
from skinnytools.utils.text import format_size


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a session file for bloat")
    parser.add_argument("file", type=str, help="Session file to analyze")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    raw = path.read_text()
    total_size = len(raw)

    print(f"File: {path.name}")
    print(f"Total size: {format_size(total_size)} chars")
    print()

    # Find tool results
    tool_results: list[tuple[str, int]] = []

    # Try JSONL
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            _find_tool_results(obj, tool_results)
        except json.JSONDecodeError:
            continue

    # Try single JSON if JSONL found nothing
    if not tool_results:
        try:
            obj = json.loads(raw)
            _find_tool_results(obj, tool_results)
        except json.JSONDecodeError:
            pass

    if tool_results:
        print(f"Tool results found: {len(tool_results)}")
        sizes = sorted([(s, i) for i, (_, s) in enumerate(tool_results)], reverse=True)
        total_chars = sum(s for s, _ in sizes)
        print(f"Total tool result chars: {format_size(total_chars)}")
        print()
        print("Top 10 largest:")
        for rank, (size, idx) in enumerate(sizes[:10], 1):
            pct = size / total_size * 100
            print(f"  {rank}. Entry {idx}: {format_size(size)} ({pct:.1f}%)")
    else:
        print("No tool results found.")

    # Recursive pattern detection
    print()
    print("Recursive content detection:")
    found = False
    for pattern in PATTERNS:
        matches = [m for m in pattern.regex.finditer(raw) if len(m.group(0)) >= pattern.min_match_size]
        if matches:
            total_chars = sum(len(m.group(0)) for m in matches)
            print(f"  {pattern.name}: {len(matches)} matches, {format_size(total_chars)} chars")
            found = True
    if not found:
        print("  (none detected)")

    # Compression estimate
    if tool_results:
        oversized = sum(s for s, _ in sizes if s > 50_000)
        print()
        print(f"Estimated compression potential: {format_size(oversized)} chars")
        print(f"  ({oversized / total_size * 100:.1f}% of total)")


def _find_tool_results(obj: object, results: list[tuple[str, int]]) -> None:
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


if __name__ == "__main__":
    main()
