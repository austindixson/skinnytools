"""Compression statistics models."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, computed_field


class StageStats(BaseModel):
    """Stats for a single filter stage."""

    model_config = ConfigDict(frozen=True)

    filter_name: str
    input_size: int
    output_size: int
    items_stripped: int = 0
    duration_ms: float = 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def compression_ratio(self) -> float:
        if self.input_size == 0:
            return 0.0
        return 1.0 - (self.output_size / self.input_size)


class CompressionStats(BaseModel):
    """Aggregate stats across all filter stages."""

    model_config = ConfigDict(frozen=True)

    input_size: int
    output_size: int
    stages: tuple[StageStats, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_compression_ratio(self) -> float:
        if self.input_size == 0:
            return 0.0
        return 1.0 - (self.output_size / self.input_size)

    def to_summary(self) -> str:
        lines = [
            f"Input:  {self.input_size:>12,} chars",
            f"Output: {self.output_size:>12,} chars",
            f"Saved:  {self.input_size - self.output_size:>12,} chars "
            f"({self.total_compression_ratio:.1%})",
            "",
            "Per-filter breakdown:",
        ]
        for stage in self.stages:
            saved = stage.input_size - stage.output_size
            if saved > 0:
                lines.append(
                    f"  {stage.filter_name:<20} "
                    f"{saved:>10,} chars saved "
                    f"({stage.compression_ratio:.1%}) "
                    f"[{stage.duration_ms:.0f}ms]"
                )
            else:
                lines.append(
                    f"  {stage.filter_name:<20} (no change) "
                    f"[{stage.duration_ms:.0f}ms]"
                )
        return "\n".join(lines)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(self.model_dump_json(indent=2))
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> CompressionStats:
        data = json.loads(path.read_text())
        return cls.model_validate(data)
