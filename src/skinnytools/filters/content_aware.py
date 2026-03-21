"""Content-type-specific compression strategies."""

from __future__ import annotations

import re

from skinnytools.core.detector import ContentType, detect_content_type
from skinnytools.models.config import FilterConfig
from skinnytools.models.filter_result import FilterResult


class ContentAwareFilter:
    """Apply type-specific compression based on detected content type."""

    @property
    def name(self) -> str:
        return "content_aware"

    def apply(self, content: str, config: FilterConfig) -> FilterResult:
        original_size = len(content)
        content_type = detect_content_type(content)

        handlers = {
            ContentType.LOG_LINES: _compress_logs,
            ContentType.STACK_TRACE: _compress_stack_trace,
            ContentType.HTML: _compress_html,
            ContentType.BASE64: _compress_base64,
        }

        handler = handlers.get(content_type)
        if handler is None:
            return FilterResult(
                content=content,
                original_size=original_size,
                filtered_size=original_size,
                filter_name=self.name,
                metadata={"content_type": content_type.name},
            )

        result = handler(content, config)
        filtered_size = len(result)
        return FilterResult(
            content=result,
            original_size=original_size,
            filtered_size=filtered_size,
            filter_name=self.name,
            was_truncated=filtered_size < original_size,
            metadata={"content_type": content_type.name},
        )


def _compress_logs(text: str, config: FilterConfig) -> str:
    """Collapse repeated log lines, keep first/last + count."""
    lines = text.split("\n")
    if len(lines) <= config.max_log_lines:
        return text

    # Keep first N/2 and last N/2 lines
    half = config.max_log_lines // 2
    head = lines[:half]
    tail = lines[-half:]
    omitted = len(lines) - config.max_log_lines

    # Detect repeated patterns in omitted lines
    middle = lines[half:-half]
    repeated = _count_repeated_lines(middle)

    summary_parts = [
        f"[... {omitted} log lines omitted ...]",
    ]
    if repeated:
        summary_parts.append(
            f"[repeated patterns: {', '.join(f'{v}x {k[:60]}' for k, v in repeated.items())}]"
        )

    return "\n".join(head + summary_parts + tail)


def _count_repeated_lines(lines: list[str]) -> dict[str, int]:
    """Find lines that repeat 3+ times."""
    # Normalize by stripping timestamps
    normalized: dict[str, int] = {}
    ts_pattern = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}\S*\s*")
    for line in lines:
        key = ts_pattern.sub("", line).strip()
        if len(key) > 10:
            normalized[key] = normalized.get(key, 0) + 1
    return {k: v for k, v in normalized.items() if v >= 3}


def _compress_stack_trace(text: str, config: FilterConfig) -> str:
    """Keep error message + first frame + last frame."""
    lines = text.split("\n")
    if len(lines) <= 10:
        return text

    # Find error message (usually last non-empty line)
    error_line = ""
    for line in reversed(lines):
        if line.strip() and not line.startswith(" "):
            error_line = line
            break

    # Keep first 3 lines (header + first frame) and last 3 (last frame + error)
    head = lines[:3]
    tail = lines[-3:]
    omitted = len(lines) - 6

    return "\n".join(
        head
        + [f"    [... {omitted} frames omitted ...]"]
        + tail
    )


def _compress_html(text: str, config: FilterConfig) -> str:
    """Strip HTML tags, keep text content."""
    # Remove script and style blocks entirely
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _compress_base64(text: str, config: FilterConfig) -> str:
    """Replace base64 blobs with size indicators."""
    pattern = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")

    def replace_blob(match: re.Match[str]) -> str:
        size = len(match.group(0))
        return f"[base64 data, {size} chars]"

    return pattern.sub(replace_blob, text)
