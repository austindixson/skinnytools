"""Tests for the smart truncator filter."""

from __future__ import annotations

import json

from skinnytools.filters.truncator import TruncatorFilter
from skinnytools.models.config import FilterConfig


def test_small_content_passes_through():
    content = "hello"
    f = TruncatorFilter()
    result = f.apply(content, FilterConfig(max_size=1000))
    assert result.content == content
    assert not result.was_truncated


def test_truncates_plain_text():
    content = "x" * 100_000
    f = TruncatorFilter()
    result = f.apply(content, FilterConfig(max_size=10_000))
    assert result.filtered_size <= 11_000  # max_size + footer
    assert result.was_truncated
    assert "truncated" in result.content.lower()


def test_preserves_head_and_tail():
    content = "HEAD" + "x" * 100_000 + "TAIL"
    f = TruncatorFilter()
    result = f.apply(content, FilterConfig(max_size=10_000))
    assert result.content.startswith("HEAD")
    assert "TAIL" in result.content


def test_truncates_json_array():
    items = [{"id": i, "data": f"item_{i}" * 100} for i in range(50)]
    content = json.dumps(items)
    f = TruncatorFilter()
    result = f.apply(content, FilterConfig(max_size=5_000))
    assert result.was_truncated
    assert "more items" in result.content


def test_truncates_json_object():
    obj = {f"key_{i}": "v" * 5000 for i in range(20)}
    content = json.dumps(obj)
    f = TruncatorFilter()
    result = f.apply(content, FilterConfig(max_size=10_000))
    assert result.was_truncated
    assert result.filtered_size < result.original_size


def test_footer_includes_sizes():
    content = "x" * 100_000
    f = TruncatorFilter()
    result = f.apply(content, FilterConfig(max_size=10_000))
    assert "Truncated:" in result.content
