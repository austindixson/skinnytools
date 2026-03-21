"""Token budget tracker with progressive compression."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, computed_field


class BudgetTracker(BaseModel):
    """Tracks cumulative token usage and adjusts compression pressure.

    Immutable — use with_consumption() to get updated tracker.
    """

    model_config = ConfigDict(frozen=True)

    total_budget: int
    consumed: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pressure(self) -> float:
        """How much of the budget has been consumed (0.0 to 1.0)."""
        if self.total_budget <= 0:
            return 1.0
        return min(self.consumed / self.total_budget, 1.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def remaining(self) -> int:
        return max(self.total_budget - self.consumed, 0)

    def with_consumption(self, chars: int) -> "BudgetTracker":
        """Return new tracker with additional consumption recorded."""
        tokens = chars // 4  # rough estimate
        return BudgetTracker(
            total_budget=self.total_budget,
            consumed=self.consumed + tokens,
        )

    def adjusted_max_size(self, base_max_size: int) -> int:
        """Reduce max_size based on budget pressure.

        - <50% pressure: full budget
        - 50-75%: reduce by 25%
        - 75-90%: reduce by 50%
        - >90%: reduce by 75%
        """
        if self.pressure < 0.5:
            return base_max_size
        if self.pressure < 0.75:
            return int(base_max_size * 0.75)
        if self.pressure < 0.9:
            return int(base_max_size * 0.5)
        return int(base_max_size * 0.25)
