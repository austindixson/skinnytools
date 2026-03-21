"""Tests for text utilities."""

from __future__ import annotations

from skinnytools.utils.text import estimate_tokens, format_size, smart_truncate


def test_estimate_tokens():
    assert estimate_tokens("hello world") == 2  # 11 // 4
    assert estimate_tokens("") == 0


def test_smart_truncate_no_truncation():
    text, was = smart_truncate("hello", 100)
    assert text == "hello"
    assert not was


def test_smart_truncate_preserves_head_tail():
    text = "HEAD" + "x" * 10_000 + "TAIL"
    result, was = smart_truncate(text, 1000)
    assert was
    assert result.startswith("HEAD")
    assert "TAIL" in result
    assert "truncated" in result


def test_format_size():
    assert format_size(500) == "500"
    assert format_size(1500) == "1.5K"
    assert format_size(1_500_000) == "1.5M"
