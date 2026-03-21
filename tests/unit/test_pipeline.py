"""Tests for the filter pipeline."""

from __future__ import annotations

import json

from skinnytools.core.budget import BudgetTracker
from skinnytools.core.pipeline import process
from skinnytools.models.config import PipelineConfig


def test_full_pipeline_recursive_session(sample_recursive_session):
    """End-to-end: recursive session JSON should be heavily compressed."""
    config = PipelineConfig()
    filtered, stats = process(sample_recursive_session, config)

    assert stats.output_size < stats.input_size
    assert stats.total_compression_ratio > 0.1
    assert len(stats.stages) == 5  # all 5 filters ran


def test_pipeline_with_clean_small_content():
    """Small clean content should pass through unchanged."""
    content = "hello world"
    config = PipelineConfig()
    filtered, stats = process(content, config)
    # Content should be essentially unchanged (json_compactor won't touch it)
    assert "hello world" in filtered


def test_pipeline_respects_disabled_filters():
    """Disabled filters should be skipped."""
    config = PipelineConfig(
        enabled_filters=("truncator",),
    )
    content = "x" * 100_000
    filtered, stats = process(content, config)
    assert len(stats.stages) == 1
    assert stats.stages[0].filter_name == "truncator"


def test_pipeline_with_budget_pressure():
    """High budget pressure should reduce max_size."""
    content = json.dumps({"data": "x" * 80_000})
    config = PipelineConfig()
    # High pressure budget
    budget = BudgetTracker(total_budget=100_000, consumed=90_000)
    filtered, stats = process(content, config, budget)
    # With 90% pressure, max_size should be reduced by 75%
    assert stats.output_size < len(content)


def test_pipeline_stats_are_accurate(sample_recursive_session):
    config = PipelineConfig()
    filtered, stats = process(sample_recursive_session, config)

    assert stats.input_size == len(sample_recursive_session)
    assert stats.output_size == len(filtered)
    # Each stage's output should be next stage's input
    for i in range(len(stats.stages) - 1):
        assert stats.stages[i].output_size == stats.stages[i + 1].input_size


def test_pipeline_summary_output(sample_recursive_session):
    config = PipelineConfig()
    _, stats = process(sample_recursive_session, config)
    summary = stats.to_summary()
    assert "Input:" in summary
    assert "Output:" in summary
    assert "Saved:" in summary
