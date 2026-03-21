"""Filter protocol — all filters implement this interface."""

from __future__ import annotations

from typing import Protocol

from skinnytools.models.config import FilterConfig
from skinnytools.models.filter_result import FilterResult


class Filter(Protocol):
    """Protocol for content filters in the pipeline."""

    @property
    def name(self) -> str: ...

    def apply(self, content: str, config: FilterConfig) -> FilterResult: ...
