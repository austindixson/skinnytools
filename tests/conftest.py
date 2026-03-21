"""Shared test fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skinnytools.models.config import FilterConfig, PipelineConfig

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def default_filter_config() -> FilterConfig:
    return FilterConfig()


@pytest.fixture
def default_pipeline_config() -> PipelineConfig:
    return PipelineConfig()


@pytest.fixture
def sample_recursive_session() -> str:
    """A session JSON with recursively embedded conversation."""
    inner_conversation = json.dumps([
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Hi there! " + "x" * 2000},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "abc123",
                    "content": "some tool output " + "y" * 2000,
                }
            ],
        },
    ])

    # Simulate the recursive embedding: tool result contains the session
    outer = {
        "messages": [
            {"role": "user", "content": "check services"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool1",
                        "name": "exec",
                        "input": {"command": "status"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool1",
                        "content": inner_conversation,  # RECURSIVE!
                    }
                ],
            },
        ],
    }
    return json.dumps(outer)


@pytest.fixture
def large_json_with_nulls() -> str:
    """A large JSON response with many null/empty values."""
    items = []
    for i in range(100):
        items.append({
            "id": i,
            "name": f"item_{i}",
            "description": None,
            "tags": [],
            "metadata": {},
            "created_at": "2024-01-01T00:00:00Z",
            "_links": {"self": f"/items/{i}"},
            "_meta": {"version": 1},
            "nested": {
                "field1": "value",
                "field2": None,
                "field3": "",
                "deep": {
                    "a": None,
                    "b": [],
                    "c": "data",
                },
            },
        })
    return json.dumps(items, indent=2)


@pytest.fixture
def sample_log_output() -> str:
    """Simulated log output with repeated lines."""
    lines = []
    for i in range(200):
        if i % 5 == 0:
            lines.append(
                f"2024-01-01T00:00:{i:02d}Z ERROR Connection refused to db:5432"
            )
        elif i % 3 == 0:
            lines.append(
                f"2024-01-01T00:00:{i:02d}Z WARN Retry attempt {i}"
            )
        else:
            lines.append(
                f"2024-01-01T00:00:{i:02d}Z INFO Processing request {i}"
            )
    return "\n".join(lines)


@pytest.fixture
def sample_thinking_block() -> str:
    """Content with embedded thinking blocks."""
    return json.dumps({
        "result": "The answer is 42",
        "thinking": "Let me think about this... " + "reasoning " * 500,
        "metadata": {
            "type": "thinking",
            "thinking": "More internal reasoning " + "deep thought " * 300,
        },
    })
