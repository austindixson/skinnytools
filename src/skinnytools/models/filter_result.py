"""Filter result model — output of each filter stage."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, computed_field


class FilterResult(BaseModel):
    """Immutable result from a single filter stage."""

    model_config = ConfigDict(frozen=True)

    content: str
    original_size: int
    filtered_size: int
    filter_name: str
    was_truncated: bool = False
    was_redirected: bool = False
    redirect_path: str | None = None
    metadata: dict[str, str | int | bool] = {}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def compression_ratio(self) -> float:
        if self.original_size == 0:
            return 0.0
        return 1.0 - (self.filtered_size / self.original_size)
