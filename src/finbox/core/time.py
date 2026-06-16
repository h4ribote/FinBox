"""Calendar / tick model (doc 00 0.7, doc 03 3.1).

tick is the 0-based global turn serial. The calendar is derived from tick via
pure integer arithmetic; boundary predicates drive periodic events (doc 03 3.5).
"""
from __future__ import annotations
from dataclasses import dataclass

MONTHS_PER_YEAR = 12  # fixed (doc 00 0.7)
DEFAULT_TURNS_PER_MONTH = 4


@dataclass(frozen=True, slots=True)
class Calendar:
    """Time model with a configurable ``turns_per_month`` (doc 00 0.7)."""
    turns_per_month: int = DEFAULT_TURNS_PER_MONTH

    @property
    def turns_per_year(self) -> int:
        return self.turns_per_month * MONTHS_PER_YEAR

    def month_index(self, tick: int) -> int:
        return tick // self.turns_per_month

    def year_index(self, tick: int) -> int:
        return self.month_index(tick) // MONTHS_PER_YEAR

    def decompose(self, tick: int) -> tuple[int, int, int]:
        """Return 1-based (Y, M, T) for a tick (doc 03 3.1.1)."""
        if tick < 0:
            raise ValueError("tick must be >= 0")
        mi = tick // self.turns_per_month
        turn_in_month = tick % self.turns_per_month
        return (mi // MONTHS_PER_YEAR + 1, mi % MONTHS_PER_YEAR + 1, turn_in_month + 1)

    def to_tick(self, year: int, month: int, turn: int) -> int:
        """Compose a tick from 1-based (Y, M, T) (doc 03 3.1.1)."""
        if not (1 <= month <= MONTHS_PER_YEAR):
            raise ValueError("month out of range")
        if not (1 <= turn <= self.turns_per_month):
            raise ValueError("turn out of range")
        return ((year - 1) * MONTHS_PER_YEAR + (month - 1)) * self.turns_per_month + (turn - 1)

    def label(self, tick: int) -> str:
        """`Y{year}-M{month:02d}-T{turn}` (doc 00 0.3)."""
        y, m, t = self.decompose(tick)
        return f"Y{y}-M{m:02d}-T{t}"

    def is_month_end(self, tick: int) -> bool:
        return tick % self.turns_per_month == self.turns_per_month - 1

    def is_quarter_end(self, tick: int) -> bool:
        return self.is_month_end(tick) and self.month_index(tick) % 3 == 2

    def is_year_end(self, tick: int) -> bool:
        return self.is_month_end(tick) and self.month_index(tick) % MONTHS_PER_YEAR == MONTHS_PER_YEAR - 1


DEFAULT_CALENDAR = Calendar()
