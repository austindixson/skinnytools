"""Filter pipeline orchestrator."""

from __future__ import annotations

import time

from skinnytools.core.budget import BudgetTracker
from skinnytools.filters.registry import build_pipeline
from skinnytools.models.config import PipelineConfig
from skinnytools.models.stats import CompressionStats, StageStats


def process(
    content: str,
    config: PipelineConfig,
    budget: BudgetTracker | None = None,
) -> tuple[str, CompressionStats]:
    """Run content through the filter pipeline.

    Returns (filtered_content, compression_stats).
    """
    input_size = len(content)
    filters = build_pipeline(config.enabled_filters)
    stages: list[StageStats] = []
    current = content

    # Adjust max_size based on budget pressure
    filter_config = config.filter_config
    if budget is not None:
        adjusted = budget.adjusted_max_size(filter_config.max_size)
        if adjusted != filter_config.max_size:
            filter_config = filter_config.model_copy(
                update={"max_size": adjusted}
            )

    for f in filters:
        stage_input_size = len(current)
        start = time.monotonic()

        result = f.apply(current, filter_config)

        elapsed = (time.monotonic() - start) * 1000  # ms
        current = result.content

        stages.append(
            StageStats(
                filter_name=result.filter_name,
                input_size=stage_input_size,
                output_size=result.filtered_size,
                items_stripped=result.metadata.get("items_stripped", 0),
                duration_ms=round(elapsed, 1),
            )
        )

    stats = CompressionStats(
        input_size=input_size,
        output_size=len(current),
        stages=tuple(stages),
    )

    return current, stats
