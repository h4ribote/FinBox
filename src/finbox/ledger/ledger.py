"""The authoritative integer double-entry ledger (doc 08, doc 15 15.6)."""
from __future__ import annotations
from collections import defaultdict
from collections.abc import Iterable, Sequence

from ..core.enums import Cause, TurnPhase
from ..core.errors import NonNegativeError
from ..core.ids import AssetId, EntityId
from .conservation import ConservationGuard
from .types import LedgerLine, Posting


class Ledger:
    """balance[entity_id][asset_id] sparse non-negative integer store."""

    def __init__(self) -> None:
        self._bal: dict[EntityId, dict[AssetId, int]] = {}
        self._journal: list[Posting] = []
        self._next_id = 0
        self._guard = ConservationGuard()

    # ---- reads
    def get(self, entity_id: EntityId, asset_id: AssetId) -> int:
        return self._bal.get(entity_id, {}).get(asset_id, 0)

    def total_supply(self, asset_id: AssetId) -> int:
        return sum(row.get(asset_id, 0) for row in self._bal.values())

    def balances(self) -> dict[EntityId, dict[AssetId, int]]:
        """Deep-ish copy of non-zero balances (for snapshots / comparison)."""
        return {e: dict(row) for e, row in self._bal.items() if row}

    @property
    def journal(self) -> tuple[Posting, ...]:
        return tuple(self._journal)

    @property
    def next_posting_id(self) -> int:
        return self._next_id

    # ---- writes
    def _apply(self, posting: Posting) -> None:
        """Validate (conservation + non-negative final state) then mutate atomically."""
        self._guard.check(posting)
        deltas: dict[tuple[EntityId, AssetId], int] = defaultdict(int)
        for ln in posting.lines:
            deltas[(ln.entity_id, ln.asset_id)] += ln.delta
        # atomic non-negative check against final state BEFORE any mutation (doc 00 0.9)
        for (e, a), d in deltas.items():
            if self.get(e, a) + d < 0:
                raise NonNegativeError(
                    f"posting {posting.posting_id} would make balance[{e}][{a}] negative "
                    f"({self.get(e, a)} + {d})")
        for (e, a), d in deltas.items():
            row = self._bal.setdefault(e, {})
            nv = row.get(a, 0) + d
            if nv == 0:
                row.pop(a, None)
            else:
                row[a] = nv
            if not row:
                self._bal.pop(e, None)

    def post(
        self,
        tick: int,
        phase: TurnPhase,
        cause: Cause,
        lines: Sequence[LedgerLine],
        cause_ref: str | None = None,
    ) -> Posting:
        """Build, validate, apply and journal a posting; returns it. Raises on violation."""
        posting = Posting(self._next_id, tick, phase, cause, cause_ref, tuple(lines))
        self._apply(posting)
        self._next_id += 1
        self._journal.append(posting)
        return posting

    # ---- replay
    @classmethod
    def from_journal(cls, postings: Iterable[Posting]) -> "Ledger":
        """Reconstruct a ledger by replaying postings in their given order (doc 08 8.4.3)."""
        led = cls()
        for p in postings:
            led._apply(p)
            led._journal.append(p)
            led._next_id = max(led._next_id, p.posting_id + 1)
        return led
