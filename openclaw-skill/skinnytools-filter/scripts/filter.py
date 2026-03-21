#!/usr/bin/env python3
"""SkinnyTools filter script for OpenClaw integration.

Reads tool output from stdin or --input, runs through the compression pipeline,
outputs filtered result to stdout.

Usage:
    echo "$TOOL_OUTPUT" | python3 filter.py
    python3 filter.py --input raw_output.txt --max-size 30000
    python3 filter.py --input raw_output.txt --disable recursive --verbose
"""

from __future__ import annotations

import argparse
import sys
import os

# Add skinnytools to path
SKINNYTOOLS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(SKINNYTOOLS_ROOT, "src"))

from skinnytools.core.pipeline import process
from skinnytools.core.budget import BudgetTracker
from skinnytools.models.config import FilterConfig, PipelineConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter tool output through skinnytools")
    parser.add_argument("--input", "-i", type=str, help="Input file (default: stdin)")
    parser.add_argument("--max-size", type=int, default=50_000, help="Max output size in chars")
    parser.add_argument("--budget", type=int, default=500_000, help="Token budget")
    parser.add_argument("--disable", action="append", default=[], help="Disable a filter (repeatable)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print stats to stderr")
    args = parser.parse_args()

    # Read input
    if args.input:
        with open(args.input) as f:
            content = f.read()
    else:
        if sys.stdin.isatty():
            print("Reading from stdin (Ctrl+D to end)...", file=sys.stderr)
        content = sys.stdin.read()

    if not content:
        return

    # Build config
    enabled = tuple(
        f for f in ("recursive", "content_aware", "json_compactor", "truncator", "file_redirect")
        if f not in args.disable
    )
    config = PipelineConfig(
        enabled_filters=enabled,
        filter_config=FilterConfig(max_size=args.max_size),
        token_budget=args.budget,
    )
    tracker = BudgetTracker(total_budget=args.budget)

    # Filter
    filtered, stats = process(content, config, tracker)

    # Output
    sys.stdout.write(filtered)

    if args.verbose:
        print("\n" + stats.to_summary(), file=sys.stderr)


if __name__ == "__main__":
    main()
