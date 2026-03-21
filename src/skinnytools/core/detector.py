"""Content-type detection for type-specific compression."""

from __future__ import annotations

import re
from enum import Enum, auto

from skinnytools.utils.json_utils import safe_parse


class ContentType(Enum):
    JSON_OBJECT = auto()
    JSON_ARRAY = auto()
    LOG_LINES = auto()
    STACK_TRACE = auto()
    HTML = auto()
    BASE64 = auto()
    CSV = auto()
    PLAIN_TEXT = auto()


# Heuristic patterns
_LOG_PATTERN = re.compile(
    r"^\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}", re.MULTILINE
)
_STACK_TRACE_PATTERN = re.compile(
    r"(?:Traceback \(most recent call last\)"
    r"|^\s+at\s+\S+\(|^\s+File \".+\", line \d+)",
    re.MULTILINE,
)
_HTML_PATTERN = re.compile(r"<(?:html|div|span|p|body|head)\b", re.IGNORECASE)
_BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/]{200,}={0,2}$", re.MULTILINE)
_CSV_HEADER_PATTERN = re.compile(r'^["\w]+(?:,["\w]+){2,}$', re.MULTILINE)


def detect_content_type(text: str) -> ContentType:
    """Detect the content type of text using heuristics."""
    stripped = text.strip()
    if not stripped:
        return ContentType.PLAIN_TEXT

    # Try JSON first
    parsed = safe_parse(stripped)
    if parsed is not None:
        if isinstance(parsed, dict):
            return ContentType.JSON_OBJECT
        return ContentType.JSON_ARRAY

    # Check for structured text types
    if _STACK_TRACE_PATTERN.search(stripped):
        return ContentType.STACK_TRACE

    if _HTML_PATTERN.search(stripped):
        return ContentType.HTML

    # Count log-like lines
    log_matches = _LOG_PATTERN.findall(stripped[:5000])
    lines = stripped[:5000].count("\n") + 1
    if len(log_matches) > 3 and len(log_matches) / lines > 0.3:
        return ContentType.LOG_LINES

    if _BASE64_PATTERN.search(stripped):
        return ContentType.BASE64

    if _CSV_HEADER_PATTERN.match(stripped):
        return ContentType.CSV

    return ContentType.PLAIN_TEXT
