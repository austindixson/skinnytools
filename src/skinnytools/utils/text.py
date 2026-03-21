"""Shared text utilities for token estimation and truncation."""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def smart_truncate(text: str, max_size: int) -> tuple[str, bool]:
    """Truncate text preserving head and tail.

    Returns (truncated_text, was_truncated).
    Keeps first 80% and last 10% of max_size, with a marker in between.
    """
    if len(text) <= max_size:
        return text, False

    marker = f"\n\n[... truncated {len(text) - max_size:,} chars ...]\n\n"
    marker_len = len(marker)
    available = max_size - marker_len
    if available <= 0:
        return text[:max_size], True

    head_size = int(available * 0.8)
    tail_size = available - head_size

    head = text[:head_size]
    tail = text[-tail_size:] if tail_size > 0 else ""

    return head + marker + tail, True


def escape_depth(text: str, pos: int = 0) -> int:
    """Count levels of backslash escaping at a position."""
    depth = 0
    while pos > 0 and text[pos - 1] == "\\":
        depth += 1
        pos -= 1
    return depth


def format_size(size: int) -> str:
    """Format byte/char count for display."""
    if size < 1_000:
        return f"{size}"
    if size < 1_000_000:
        return f"{size / 1_000:.1f}K"
    return f"{size / 1_000_000:.1f}M"
