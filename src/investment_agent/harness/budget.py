from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    max_tokens: int
    max_usd: float
    parent: Budget | None = None
    used_tokens: int = 0
    used_usd: float = 0.0
    _lock: RLock = field(default_factory=RLock, repr=False)

    def child(self, token_fraction: float, usd_fraction: float) -> Budget:
        if not 0 < token_fraction <= 1 or not 0 < usd_fraction <= 1:
            raise ValueError("Child budget fractions must be in (0, 1]")
        return Budget(
            max_tokens=max(1, int(self.remaining_tokens * token_fraction)),
            max_usd=max(0.000001, self.remaining_usd * usd_fraction),
            parent=self,
            _lock=self._root_lock(),
        )

    def charge(self, tokens: int, usd: float) -> None:
        if tokens < 0 or usd < 0:
            raise ValueError("Budget charges cannot be negative")

        lineage = self._lineage()
        with self._root_lock():
            for budget in lineage:
                if budget.used_tokens + tokens > budget.max_tokens:
                    raise BudgetExceeded("Token budget exceeded")
                if budget.used_usd + usd > budget.max_usd:
                    raise BudgetExceeded("USD budget exceeded")
            for budget in lineage:
                budget.used_tokens += tokens
                budget.used_usd += usd

    @property
    def remaining_tokens(self) -> int:
        return self.max_tokens - self.used_tokens

    @property
    def remaining_usd(self) -> float:
        return self.max_usd - self.used_usd

    def _lineage(self) -> list[Budget]:
        lineage: list[Budget] = []
        current: Budget | None = self
        while current is not None:
            lineage.append(current)
            current = current.parent
        return lineage

    def _root_lock(self) -> RLock:
        current = self
        while current.parent is not None:
            current = current.parent
        return current._lock
