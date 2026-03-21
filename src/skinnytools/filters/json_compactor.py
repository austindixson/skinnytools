"""JSON minification — strip nulls, empties, metadata keys."""

from __future__ import annotations

from skinnytools.models.config import FilterConfig
from skinnytools.models.filter_result import FilterResult
from skinnytools.utils.json_utils import (
    compact_json,
    safe_parse,
    strip_empty,
    strip_nulls,
)


class JsonCompactorFilter:
    """Compact JSON by removing nulls, empty values, and metadata keys."""

    @property
    def name(self) -> str:
        return "json_compactor"

    def apply(self, content: str, config: FilterConfig) -> FilterResult:
        original_size = len(content)
        parsed = safe_parse(content)

        if parsed is None:
            return FilterResult(
                content=content,
                original_size=original_size,
                filtered_size=original_size,
                filter_name=self.name,
            )

        # Strip nulls and empty values
        cleaned = strip_nulls(parsed)
        cleaned = strip_empty(cleaned)

        # Strip configurable metadata keys
        if isinstance(cleaned, dict):
            cleaned = _strip_keys(cleaned, config.strip_metadata_keys)
        elif isinstance(cleaned, list):
            cleaned = [
                _strip_keys(item, config.strip_metadata_keys)
                if isinstance(item, dict)
                else item
                for item in cleaned
            ]

        result = compact_json(cleaned)
        filtered_size = len(result)
        return FilterResult(
            content=result,
            original_size=original_size,
            filtered_size=filtered_size,
            filter_name=self.name,
            was_truncated=filtered_size < original_size,
            metadata={
                "keys_stripped": _count_stripped_keys(
                    parsed, config.strip_metadata_keys
                ),
            },
        )


def _strip_keys(obj: dict, keys: tuple[str, ...]) -> dict:
    """Remove specified keys from a dict, recursively."""
    cleaned = {}
    for k, v in obj.items():
        if k in keys:
            continue
        if isinstance(v, dict):
            cleaned[k] = _strip_keys(v, keys)
        elif isinstance(v, list):
            cleaned[k] = [
                _strip_keys(item, keys) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            cleaned[k] = v
    return cleaned


def _count_stripped_keys(obj: object, keys: tuple[str, ...]) -> int:
    """Count how many metadata keys would be stripped."""
    count = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                count += 1
            count += _count_stripped_keys(v, keys)
    elif isinstance(obj, list):
        for item in obj:
            count += _count_stripped_keys(item, keys)
    return count
