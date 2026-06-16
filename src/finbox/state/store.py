"""StateStore: the single authoritative world state (doc 02 2.2).

For the walking skeleton this is a one-country (ALD) economy with a single
goods market. All evolving state lives here; it is mutated only by the engine
(single writer) and serialized deterministically for replay hashing.
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
    pair: TradingPair                  # food / CUR:ALD
    agents: tuple[EntityId, ...]
    firm: EntityId
    gov: EntityId
    cb: EntityId
    exch: EntityId
    last_price: dict[str, int] = field(default_factory=dict)
    satiety: dict[EntityId, int] = field(default_factory=dict)
    macro: dict[str, int] = field(default_factory=dict)

    def cash(self, e: EntityId) -> int:
        return self.ledger.get(e, self.cur)

    def food_qty(self, e: EntityId) -> int:
        return self.ledger.get(e, self.food)
