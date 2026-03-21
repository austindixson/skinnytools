"""Safe JSON parsing and manipulation utilities."""

from __future__ import annotations

import json
from typing import Any


def safe_parse(text: str) -> dict | list | None:
    """Parse JSON, returning None on failure (never raises)."""
    try:
        result = json.loads(text)
        if isinstance(result, (dict, list)):
            return result
        return None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def measure_depth(obj: Any, current: int = 0, limit: int = 100) -> int:
    """Measure maximum nesting depth of a JSON-like structure."""
    if current >= limit:
        return current
    if isinstance(obj, dict):
        if not obj:
            return current + 1
        return max(
            measure_depth(v, current + 1, limit) for v in obj.values()
        )
    if isinstance(obj, list):
        if not obj:
            return current + 1
        return max(
            measure_depth(item, current + 1, limit) for item in obj
        )
    return current


def strip_nulls(obj: Any) -> Any:
    """Recursively strip null values from dicts and lists."""
    if isinstance(obj, dict):
        return {
            k: strip_nulls(v)
            for k, v in obj.items()
            if v is not None
        }
    if isinstance(obj, list):
        return [strip_nulls(item) for item in obj if item is not None]
    return obj


def strip_empty(obj: Any) -> Any:
    """Recursively strip null, empty string, empty list, empty dict values."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            v = strip_empty(v)
            if v is None or v == "" or v == [] or v == {}:
                continue
            cleaned[k] = v
        return cleaned
    if isinstance(obj, list):
        cleaned = []
        for item in obj:
            item = strip_empty(item)
            if item is None or item == "" or item == [] or item == {}:
                continue
            cleaned.append(item)
        return cleaned
    return obj


def compact_json(obj: Any) -> str:
    """Serialize JSON with minimal whitespace."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
