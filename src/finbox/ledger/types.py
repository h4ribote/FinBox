"""Ledger value types (doc 15 15.6)."""
from __future__ import annotations
from dataclasses import dataclass

from ..core.enums import Cause, TurnPhase
from ..core.errors import ValidationError
from ..core.ids import AssetId, EntityId


@dataclass(frozen=True, slots=True)
class LedgerLine:
    """One journal line: signed change to balance[entity_id][asset_id] (doc 15 15.6)."""
    entity_id: EntityId
    asset_id: AssetId
    delta: int  # != 0; + receipt, - payout

    def __post_init__(self) -> None:
        if self.delta == 0:
            raise ValidationError("LedgerLine.delta must be non-zero")


@dataclass(frozen=True, slots=True)
class Posting:
    """An atomic, audited transfer; per-asset debit==credit except at mint/burn (doc 08 8.4)."""
    posting_id: int     # monotonic, replay order
    tick: int
    phase: TurnPhase
    cause: Cause
    cause_ref: str | None
    lines: tuple[LedgerLine, ...]

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValidationError("Posting must have at least one line")
