"""Recursive pattern catalog for detecting embedded session content."""

from __future__ import annotations

import re
from dataclasses import dataclass

from skinnytools.utils.text import format_size


@dataclass(frozen=True)
class RecursivePattern:
    """A pattern that identifies recursively embedded content."""

    name: str
    description: str
    regex: re.Pattern[str]
    min_match_size: int

    def replacement(self, match: re.Match[str]) -> str:
        size = len(match.group(0))
        return f"[STRIPPED:{self.name}, {format_size(size)} chars]"


# Escaped conversation JSON: \"role\":\"assistant\" with 1+ escape levels
_ESCAPED_CONVERSATION = RecursivePattern(
    name="escaped_conversation",
    description="Escaped conversation turns embedded in string values",
    regex=re.compile(
        r'(?:\\"){1,}role(?:\\"){1,}\s*:\s*(?:\\"){1,}'
        r'(?:assistant|user|system)(?:\\"){1,}'
        r'[^"]{500,}?'
        r'(?=(?:\\"){1,}role(?:\\"){1,}|"[,}\]])',
        re.DOTALL,
    ),
    min_match_size=1024,
)

# Nested toolResult blobs inside tool output
_NESTED_TOOL_RESULT = RecursivePattern(
    name="nested_tool_result",
    description="toolResult or tool_result objects nested inside tool output",
    regex=re.compile(
        r'"(?:toolResult|tool_result)"'
        r'\s*:\s*'
        r'(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\[[\s\S]{500,}?\])',
        re.DOTALL,
    ),
    min_match_size=512,
)

# Thinking blocks (model reasoning that shouldn't be in output)
_THINKING_BLOCKS = RecursivePattern(
    name="thinking_block",
    description="Model thinking/reasoning blocks embedded in output",
    regex=re.compile(
        r'(?:"type"\s*:\s*"thinking"\s*,\s*"thinking"\s*:\s*"[^"]{500,}?"'
        r'|<thinking>[\s\S]{500,}?</thinking>)',
        re.DOTALL,
    ),
    min_match_size=500,
)

# Base64 binary blobs
_BASE64_BLOBS = RecursivePattern(
    name="base64_blob",
    description="Large base64-encoded binary data",
    regex=re.compile(
        r'[A-Za-z0-9+/]{500,}={0,2}',
    ),
    min_match_size=500,
)

# Session/messages arrays containing full conversation history
_SESSION_ARRAYS = RecursivePattern(
    name="session_array",
    description="Messages/session arrays containing conversation history",
    regex=re.compile(
        r'"(?:messages|conversation|session|history)"\s*:\s*\['
        r'[\s\S]{1000,}?'
        r'\](?=\s*[,}])',
        re.DOTALL,
    ),
    min_match_size=2048,
)

# All patterns in priority order (most impactful first)
PATTERNS: tuple[RecursivePattern, ...] = (
    _ESCAPED_CONVERSATION,
    _SESSION_ARRAYS,
    _NESTED_TOOL_RESULT,
    _THINKING_BLOCKS,
    _BASE64_BLOBS,
)
