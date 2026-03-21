"""Configuration file loading."""

from __future__ import annotations

import json
from pathlib import Path

from skinnytools.config.defaults import CONFIG_DIR
from skinnytools.models.config import PipelineConfig, SkinnyConfig


CONFIG_FILE = CONFIG_DIR / "config.json"


class ConfigError(Exception):
    """Configuration loading error."""


def load_config(path: Path | None = None) -> SkinnyConfig:
    """Load config from file, falling back to defaults."""
    config_path = path or CONFIG_FILE
    if not config_path.exists():
        return SkinnyConfig()

    try:
        data = json.loads(config_path.read_text())
        return SkinnyConfig.model_validate(data)
    except (json.JSONDecodeError, ValueError) as e:
        raise ConfigError(f"Invalid config at {config_path}: {e}") from e


def save_default_config(path: Path | None = None) -> Path:
    """Write default config to file."""
    config_path = path or CONFIG_FILE
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = SkinnyConfig()
    config_path.write_text(
        json.dumps(config.model_dump(), indent=2) + "\n"
    )
    return config_path


def merge_cli_overrides(
    config: PipelineConfig,
    *,
    max_size: int | None = None,
    budget: int | None = None,
    disable: tuple[str, ...] = (),
    verbose: bool = False,
) -> PipelineConfig:
    """Create new config with CLI flag overrides applied."""
    filter_config = config.filter_config
    if max_size is not None:
        filter_config = filter_config.model_copy(
            update={"max_size": max_size}
        )

    enabled = tuple(
        f for f in config.enabled_filters if f not in disable
    )

    return config.model_copy(
        update={
            "filter_config": filter_config,
            "token_budget": budget or config.token_budget,
            "enabled_filters": enabled,
            "verbose": verbose or config.verbose,
        }
    )
