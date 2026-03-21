"""Tests for the recursive content filter."""

from __future__ import annotations

import json

from skinnytools.filters.recursive import RecursiveFilter
from skinnytools.models.config import FilterConfig


def test_clean_content_passes_through():
    f = RecursiveFilter()
    config = FilterConfig()
    content = "Hello, this is clean output."
    result = f.apply(content, config)
    assert result.content == content
    assert result.compression_ratio == 0.0


def test_small_content_fast_path():
    f = RecursiveFilter()
    config = FilterConfig(min_match_size=1024)
    content = "small"
    result = f.apply(content, config)
    assert result.content == content
    assert result.filtered_size == len(content)


def test_strips_recursive_session(sample_recursive_session):
    f = RecursiveFilter()
    config = FilterConfig(min_match_size=512)
    result = f.apply(sample_recursive_session, config)
    # Should be significantly smaller
    assert result.filtered_size < result.original_size
    assert result.compression_ratio > 0.1
    # Should contain STRIPPED marker
    assert "STRIPPED" in result.content


def test_strips_escaped_conversation():
    """Test detection of escaped conversation JSON."""
    # Build content with escaped conversation
    inner = json.dumps([
        {"role": "assistant", "content": "x" * 2000},
        {"role": "user", "content": "y" * 2000},
    ])
    outer = json.dumps({"tool_output": inner})

    f = RecursiveFilter()
    config = FilterConfig(min_match_size=512)
    result = f.apply(outer, config)
    assert result.filtered_size < result.original_size


def test_strips_base64_blobs():
    """Test that large base64 blobs are detected and stripped."""
    import base64
    blob = base64.b64encode(b"x" * 1000).decode()
    content = json.dumps({"image": blob, "name": "test"})

    f = RecursiveFilter()
    config = FilterConfig(min_match_size=200)
    result = f.apply(content, config)
    # The base64 blob should be stripped
    assert result.filtered_size < result.original_size


def test_preserves_stripped_markers():
    """Already-stripped content should not be re-processed."""
    content = json.dumps({
        "data": "[STRIPPED:base64_blob, 5.0K chars]",
        "other": "normal content",
    })
    f = RecursiveFilter()
    config = FilterConfig(min_match_size=100)
    result = f.apply(content, config)
    assert "[STRIPPED:base64_blob" in result.content


def test_handles_invalid_json():
    """Non-JSON content should still be pattern-matched."""
    content = "not json but has " + "A" * 600 + " base64-like data"
    f = RecursiveFilter()
    config = FilterConfig(min_match_size=200)
    result = f.apply(content, config)
    # Should still work without crashing
    assert result.filter_name == "recursive"


def test_nested_tool_result_detection():
    """Detect toolResult inside a tool result."""
    inner = {
        "toolResult": {
            "content": [
                {"type": "text", "text": "output " * 200}
            ],
            "toolUseId": "inner_tool",
        }
    }
    outer = json.dumps({
        "output": json.dumps(inner),
    })

    f = RecursiveFilter()
    config = FilterConfig(min_match_size=256)
    result = f.apply(outer, config)
    assert result.filtered_size < result.original_size
