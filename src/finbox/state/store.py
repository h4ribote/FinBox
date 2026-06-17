"""StateStore: the single authoritative world state (doc 02 2.2).

M3 slice: a one-country economy with a food market and a labor market, a single
regional output cap, and per-agent satiety. All evolving state lives here; it is
mutated only by the engine (single writer) and serialized for replay hashing.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from ..core.ids import AssetId, EntityId
from ..ledger import Ledger
from ..market.types import TradingPair


@dataclass
class StateStore:
    ledger: Ledger
    tick: int
    master_seed: int
    cur: AssetId                       # CUR:ALD
    food: AssetId                      # COMM:good.food
    labor: AssetId                     # COMM:labor.unskilled
    pair: TradingPair                  # food / CUR:ALD
    labor_pair: TradingPair            # labor / CUR:ALD
    agents: tuple[EntityId, ...]
    firm: EntityId
    gov: EntityId
    cb: EntityId
    exch: EntityId
    region_cap: dict[AssetId, int] = field(default_factory=dict)
    last_price: dict[str, int] = field(default_factory=dict)
    satiety: dict[EntityId, int] = field(default_factory=dict)
    macro: dict[str, int] = field(default_factory=dict)

    def qty(self, e: EntityId, a: AssetId) -> int:
        return self.ledger.get(e, a)

    def cash(self, e: EntityId) -> int:
        return self.ledger.get(e, self.cur)

    def food_qty(self, e: EntityId) -> int:
        return self.ledger.get(e, self.food)

    def pairs(self) -> list[TradingPair]:
        """All trading pairs in canonical (pair_id lexicographic) clearing order (doc 03 3.7)."""
        return sorted([self.pair, self.labor_pair], key=lambda p: p.pair_id)
