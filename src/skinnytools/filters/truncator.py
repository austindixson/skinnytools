"""Size-based smart truncation with structure preservation."""

from __future__ import annotations

import json

from skinnytools.models.config import FilterConfig
from skinnytools.models.filter_result import FilterResult
from skinnytools.utils.json_utils import compact_json, safe_parse
from skinnytools.utils.text import format_size, smart_truncate


class TruncatorFilter:
    """Enforce size limits with structure-preserving truncation."""

    @property
    def name(self) -> str:
        return "truncator"

    def apply(self, content: str, config: FilterConfig) -> FilterResult:
        original_size = len(content)

        if original_size <= config.max_size:
            return FilterResult(
                content=content,
                original_size=original_size,
                filtered_size=original_size,
                filter_name=self.name,
            )

        # Try structure-preserving truncation for JSON
        parsed = safe_parse(content)
        if parsed is not None:
            result = _truncate_json(parsed, config.max_size)
        else:
            result, _ = smart_truncate(content, config.max_size)

        footer = (
            f"\n[Truncated: {format_size(original_size)} → "
            f"{format_size(len(result))} chars]"
        )
        result = result + footer
        filtered_size = len(result)

        return FilterResult(
            content=result,
            original_size=original_size,
            filtered_size=filtered_size,
            filter_name=self.name,
            was_truncated=True,
        )


def _truncate_json(obj: object, max_size: int) -> str:
    """Truncate JSON while preserving structure."""
    if isinstance(obj, list):
        return _truncate_array(obj, max_size)
    if isinstance(obj, dict):
        return _truncate_object(obj, max_size)
    return compact_json(obj)[:max_size]


def _truncate_array(arr: list, max_size: int) -> str:
    """Keep first 3 and last 1 items of large arrays."""
    if len(arr) <= 5:
        result = compact_json(arr)
        if len(result) <= max_size:
            return result

    # Keep first 3 + last 1
    keep_head = min(3, len(arr))
    keep_tail = 1 if len(arr) > 3 else 0
    omitted = len(arr) - keep_head - keep_tail

    head_items = arr[:keep_head]
    tail_items = arr[-keep_tail:] if keep_tail else []

    parts = []
    for item in head_items:
        serialized = compact_json(item)
        # Truncate individual items if still too large
        if len(serialized) > 1000:
            if isinstance(item, dict):
                serialized = _truncate_object_values(item, 500)
            else:
                serialized = serialized[:1000] + "..."
        parts.append(serialized)

    if omitted > 0:
        parts.append(f'"[...{omitted} more items...]"')

    for item in tail_items:
        serialized = compact_json(item)
        if len(serialized) > 1000:
            if isinstance(item, dict):
                serialized = _truncate_object_values(item, 500)
            else:
                serialized = serialized[:1000] + "..."
        parts.append(serialized)

    return "[" + ",".join(parts) + "]"


def _truncate_object(obj: dict, max_size: int) -> str:
    """Keep all keys but truncate large values."""
    result = compact_json(obj)
    if len(result) <= max_size:
        return result
    return _truncate_object_values(obj, max_size // max(len(obj), 1))


def _truncate_object_values(obj: dict, max_value_size: int) -> str:
    """Truncate each value in a dict to max_value_size."""
    truncated = {}
    for k, v in obj.items():
        serialized = compact_json(v)
        if len(serialized) > max_value_size:
            if isinstance(v, str):
                truncated[k] = v[:max_value_size] + f"...[{len(v)} total]"
            elif isinstance(v, list):
                truncated[k] = f"[array, {len(v)} items]"
            elif isinstance(v, dict):
                truncated[k] = f"{{object, {len(v)} keys}}"
            else:
                truncated[k] = v
        else:
            truncated[k] = v

    return json.dumps(truncated, separators=(",", ":"), ensure_ascii=False)
