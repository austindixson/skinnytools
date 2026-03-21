"""Recursive content detection and stripping.

This is the most critical filter — addresses the root cause of context
explosion where tool results contain copies of the session itself.
"""

from __future__ import annotations

import json
import re

from skinnytools.core.patterns import PATTERNS, RecursivePattern
from skinnytools.models.config import FilterConfig
from skinnytools.models.filter_result import FilterResult
from skinnytools.utils.text import format_size


_ALREADY_STRIPPED = re.compile(r"\[STRIPPED:")


class RecursiveFilter:
    """Detect and strip recursively embedded content."""

    @property
    def name(self) -> str:
        return "recursive"

    def apply(self, content: str, config: FilterConfig) -> FilterResult:
        original_size = len(content)

        # Fast path: small content or already processed
        if original_size < config.min_match_size:
            return FilterResult(
                content=content,
                original_size=original_size,
                filtered_size=original_size,
                filter_name=self.name,
            )

        total_stripped = 0
        items_stripped = 0
        result = content

        # Strategy 1: If valid JSON, walk the structure and check
        # string values for recursive content
        try:
            parsed = json.loads(content)
            if isinstance(parsed, (dict, list)):
                cleaned, count = _walk_json(parsed, config.min_match_size)
                if count > 0:
                    result = json.dumps(
                        cleaned, separators=(",", ":"), ensure_ascii=False
                    )
                    total_stripped = original_size - len(result)
                    items_stripped = count
        except (json.JSONDecodeError, ValueError, RecursionError):
            pass

        # Strategy 2: Apply regex patterns on raw text for anything
        # the JSON walker missed (or if content isn't valid JSON)
        if items_stripped == 0:
            result, regex_stripped = _apply_patterns(
                result, config.min_match_size
            )
            items_stripped += regex_stripped

        filtered_size = len(result)
        return FilterResult(
            content=result,
            original_size=original_size,
            filtered_size=filtered_size,
            filter_name=self.name,
            was_truncated=items_stripped > 0,
            metadata={
                "items_stripped": items_stripped,
                "chars_saved": original_size - filtered_size,
            },
        )


def _walk_json(obj: object, min_size: int) -> tuple[object, int]:
    """Recursively walk JSON, replacing large string values that
    contain recursive content with summary placeholders."""
    count = 0

    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if isinstance(v, str) and len(v) >= min_size:
                replacement = _check_string_for_recursion(v, min_size)
                if replacement is not None:
                    cleaned[k] = replacement
                    count += 1
                    continue
            cleaned_v, sub_count = _walk_json(v, min_size)
            cleaned[k] = cleaned_v
            count += sub_count
        return cleaned, count

    if isinstance(obj, list):
        cleaned_list = []
        for item in obj:
            if isinstance(item, str) and len(item) >= min_size:
                replacement = _check_string_for_recursion(item, min_size)
                if replacement is not None:
                    cleaned_list.append(replacement)
                    count += 1
                    continue
            cleaned_item, sub_count = _walk_json(item, min_size)
            cleaned_list.append(cleaned_item)
            count += sub_count
        return cleaned_list, count

    return obj, 0


def _check_string_for_recursion(value: str, min_size: int) -> str | None:
    """Check if a string value contains recursive content.

    Returns a replacement string if recursive, None if clean.
    """
    # Skip already-stripped content
    if _ALREADY_STRIPPED.search(value):
        return None

    for pattern in PATTERNS:
        if len(value) < pattern.min_match_size:
            continue
        match = pattern.regex.search(value)
        if match and len(match.group(0)) >= pattern.min_match_size:
            return (
                f"[STRIPPED:{pattern.name}, {format_size(len(value))} chars]"
            )

    return None


def _apply_patterns(
    text: str, min_size: int
) -> tuple[str, int]:
    """Apply regex patterns directly on text."""
    result = text
    total_count = 0

    for pattern in PATTERNS:
        if len(result) < pattern.min_match_size:
            continue

        matches = list(pattern.regex.finditer(result))
        valid_matches = [
            m for m in matches if len(m.group(0)) >= pattern.min_match_size
        ]

        if not valid_matches:
            continue

        # Replace from end to preserve positions
        for match in reversed(valid_matches):
            replacement = pattern.replacement(match)
            result = result[: match.start()] + replacement + result[match.end() :]
            total_count += 1

    return result, total_count
