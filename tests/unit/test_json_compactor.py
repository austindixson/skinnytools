"""Tests for the JSON compactor filter."""

from __future__ import annotations

import json

from skinnytools.filters.json_compactor import JsonCompactorFilter
from skinnytools.models.config import FilterConfig


def test_strips_nulls():
    content = json.dumps({"a": 1, "b": None, "c": "hello"})
    f = JsonCompactorFilter()
    result = f.apply(content, FilterConfig())
    parsed = json.loads(result.content)
    assert "b" not in parsed
    assert parsed["a"] == 1
    assert parsed["c"] == "hello"


def test_strips_empty_values():
    content = json.dumps({
        "a": 1,
        "b": "",
        "c": [],
        "d": {},
        "e": "keep",
    })
    f = JsonCompactorFilter()
    result = f.apply(content, FilterConfig())
    parsed = json.loads(result.content)
    assert set(parsed.keys()) == {"a", "e"}


def test_strips_metadata_keys():
    content = json.dumps({
        "data": "important",
        "_links": {"self": "/foo"},
        "_meta": {"version": 1},
    })
    f = JsonCompactorFilter()
    result = f.apply(content, FilterConfig())
    parsed = json.loads(result.content)
    assert "data" in parsed
    assert "_links" not in parsed
    assert "_meta" not in parsed


def test_compact_output():
    content = json.dumps({"key": "value"}, indent=4)
    f = JsonCompactorFilter()
    result = f.apply(content, FilterConfig())
    # No whitespace in output
    assert " " not in result.content
    assert result.filtered_size < result.original_size


def test_non_json_passes_through():
    content = "this is not json"
    f = JsonCompactorFilter()
    result = f.apply(content, FilterConfig())
    assert result.content == content
    assert result.compression_ratio == 0.0


def test_nested_nulls(large_json_with_nulls):
    f = JsonCompactorFilter()
    result = f.apply(large_json_with_nulls, FilterConfig())
    assert result.compression_ratio > 0.3  # significant savings
    # Verify valid JSON output
    parsed = json.loads(result.content)
    assert isinstance(parsed, list)
    # Check that nested nulls were stripped
    for item in parsed[:3]:
        assert "description" not in item
        assert "field2" not in item.get("nested", {})


def test_array_of_objects():
    content = json.dumps([
        {"id": 1, "val": None},
        {"id": 2, "_meta": {"x": 1}},
    ])
    f = JsonCompactorFilter()
    result = f.apply(content, FilterConfig())
    parsed = json.loads(result.content)
    assert len(parsed) == 2
    assert "_meta" not in parsed[1]
