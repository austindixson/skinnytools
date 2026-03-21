"""Filter registry — maps names to instances, builds pipelines."""

from __future__ import annotations

from skinnytools.filters.base import Filter
from skinnytools.filters.content_aware import ContentAwareFilter
from skinnytools.filters.file_redirect import FileRedirectFilter
from skinnytools.filters.json_compactor import JsonCompactorFilter
from skinnytools.filters.recursive import RecursiveFilter
from skinnytools.filters.truncator import TruncatorFilter


_REGISTRY: dict[str, Filter] = {
    "recursive": RecursiveFilter(),
    "content_aware": ContentAwareFilter(),
    "json_compactor": JsonCompactorFilter(),
    "truncator": TruncatorFilter(),
    "file_redirect": FileRedirectFilter(),
}

DEFAULT_ORDER: tuple[str, ...] = (
    "recursive",
    "content_aware",
    "json_compactor",
    "truncator",
    "file_redirect",
)


def get_filter(name: str) -> Filter:
    """Get a filter by name."""
    f = _REGISTRY.get(name)
    if f is None:
        raise ValueError(
            f"Unknown filter: {name}. "
            f"Available: {', '.join(_REGISTRY)}"
        )
    return f


def list_filters() -> list[str]:
    """List all registered filter names."""
    return list(_REGISTRY)


def build_pipeline(
    enabled: tuple[str, ...] | None = None,
) -> list[Filter]:
    """Build ordered list of filters based on enabled names."""
    names = enabled or DEFAULT_ORDER
    return [get_filter(name) for name in names]
