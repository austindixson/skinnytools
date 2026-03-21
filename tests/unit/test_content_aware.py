"""Tests for the content-aware filter."""

from __future__ import annotations

from skinnytools.filters.content_aware import ContentAwareFilter
from skinnytools.models.config import FilterConfig


def test_log_compression(sample_log_output):
    f = ContentAwareFilter()
    result = f.apply(sample_log_output, FilterConfig(max_log_lines=20))
    assert result.filtered_size < result.original_size
    assert "omitted" in result.content
    assert result.metadata["content_type"] == "LOG_LINES"


def test_html_compression():
    html = """
    <html>
    <head><title>Test</title></head>
    <body>
    <script>var x = 1; console.log(x);</script>
    <style>body { color: red; }</style>
    <div class="container">
        <p>Important text here</p>
        <span>More text</span>
    </div>
    </body>
    </html>
    """
    f = ContentAwareFilter()
    result = f.apply(html, FilterConfig())
    assert "<script>" not in result.content
    assert "<style>" not in result.content
    assert "<div" not in result.content
    assert "Important text here" in result.content
    assert "More text" in result.content


def test_stack_trace_compression():
    trace = "Traceback (most recent call last):\n"
    for i in range(30):
        trace += f'  File "module_{i}.py", line {i*10}, in func_{i}\n'
        trace += f"    some_code_{i}()\n"
    trace += "RuntimeError: something broke"

    f = ContentAwareFilter()
    result = f.apply(trace, FilterConfig())
    assert result.filtered_size < result.original_size
    assert "frames omitted" in result.content
    assert "RuntimeError" in result.content


def test_base64_compression():
    # Base64 blob must be on its own line for detection
    content = "header\n" + "A" * 1000 + "\nfooter"
    f = ContentAwareFilter()
    result = f.apply(content, FilterConfig())
    assert "[base64 data" in result.content
    assert result.filtered_size < result.original_size


def test_json_passes_through():
    """JSON content is not compressed by content_aware (handled by json_compactor)."""
    content = '{"key": "value"}'
    f = ContentAwareFilter()
    result = f.apply(content, FilterConfig())
    assert result.content == content


def test_plain_text_passes_through():
    content = "Just a simple message with no special patterns."
    f = ContentAwareFilter()
    result = f.apply(content, FilterConfig())
    assert result.content == content
