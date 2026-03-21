"""Configuration models for skinnytools."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FilterConfig(BaseModel):
    """Per-filter configuration."""

    model_config = ConfigDict(frozen=True)

    max_size: int = 50_000
    redirect_threshold: int = 100_000
    min_match_size: int = 1024
    strip_metadata_keys: tuple[str, ...] = (
        "_links",
        "_meta",
        "_embedded",
        "xmlns",
        "$schema",
    )
    max_log_lines: int = 50
    base64_preview_len: int = 200


class PipelineConfig(BaseModel):
    """Pipeline-level configuration."""

    model_config = ConfigDict(frozen=True)

    enabled_filters: tuple[str, ...] = (
        "recursive",
        "content_aware",
        "json_compactor",
        "truncator",
        "file_redirect",
    )
    filter_config: FilterConfig = FilterConfig()
    token_budget: int = 500_000
    verbose: bool = False


class SkinnyConfig(BaseModel):
    """Top-level configuration."""

    model_config = ConfigDict(frozen=True)

    pipeline: PipelineConfig = PipelineConfig()
    stats_dir: str = ""
    redirect_dir: str = ""
