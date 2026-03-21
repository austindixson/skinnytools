"""Tests for the budget tracker."""

from __future__ import annotations

from skinnytools.core.budget import BudgetTracker


def test_initial_state():
    b = BudgetTracker(total_budget=500_000)
    assert b.pressure == 0.0
    assert b.remaining == 500_000


def test_consumption():
    b = BudgetTracker(total_budget=500_000)
    b2 = b.with_consumption(200_000)  # 50K tokens
    assert b2.consumed == 50_000
    assert b2.pressure == 0.1
    # Original unchanged (immutable)
    assert b.consumed == 0


def test_pressure_levels():
    base = 50_000
    # Low pressure
    b = BudgetTracker(total_budget=100_000, consumed=10_000)
    assert b.adjusted_max_size(base) == base

    # Medium pressure (50-75%)
    b = BudgetTracker(total_budget=100_000, consumed=60_000)
    assert b.adjusted_max_size(base) == int(base * 0.75)

    # High pressure (75-90%)
    b = BudgetTracker(total_budget=100_000, consumed=80_000)
    assert b.adjusted_max_size(base) == int(base * 0.5)

    # Critical pressure (>90%)
    b = BudgetTracker(total_budget=100_000, consumed=95_000)
    assert b.adjusted_max_size(base) == int(base * 0.25)


def test_zero_budget():
    b = BudgetTracker(total_budget=0)
    assert b.pressure == 1.0
    assert b.remaining == 0
    assert b.adjusted_max_size(50_000) == 12_500


def test_over_budget():
    b = BudgetTracker(total_budget=100, consumed=200)
    assert b.pressure == 1.0
    assert b.remaining == 0
