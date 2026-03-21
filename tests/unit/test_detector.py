"""Tests for content-type detection."""

from __future__ import annotations

import json

from skinnytools.core.detector import ContentType, detect_content_type


def test_json_object():
    assert detect_content_type('{"key": "value"}') == ContentType.JSON_OBJECT


def test_json_array():
    assert detect_content_type('[1, 2, 3]') == ContentType.JSON_ARRAY


def test_log_lines():
    logs = "\n".join(
        f"2024-01-01T00:00:{i:02d}Z INFO msg {i}" for i in range(10)
    )
    assert detect_content_type(logs) == ContentType.LOG_LINES


def test_stack_trace():
    trace = """Traceback (most recent call last):
  File "test.py", line 10, in main
    foo()
  File "test.py", line 5, in foo
    raise ValueError("oops")
ValueError: oops"""
    assert detect_content_type(trace) == ContentType.STACK_TRACE


def test_html():
    assert detect_content_type("<html><body>hello</body></html>") == ContentType.HTML


def test_plain_text():
    assert detect_content_type("just some text") == ContentType.PLAIN_TEXT


def test_empty():
    assert detect_content_type("") == ContentType.PLAIN_TEXT
    assert detect_content_type("   ") == ContentType.PLAIN_TEXT
