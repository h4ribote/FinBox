"""StateStore: the single authoritative world state (doc 02 2.2).

M4 slice: a one-country multi-firm supply chain (manufacturing -> agriculture,
plus construction supplying capital) with capacity, several labor types, and a
market pair per traded asset. Mutated only by the engine; serialized for replay.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from ..core.ids import AssetId, EntityId
from ..domain.finance import Bond, Equity
from ..domain.production import FirmState
from ..ledger import Ledger
from ..market.types import TradingPair


@dataclass
class StateStore:
    ledger: Ledger
    tick: int
    master_seed: int
    cur: AssetId                                  # CUR:ALD
    food: AssetId                                 # the consumer good (COMM:good.food)
    build: AssetId                                # COMM:build.construction_labor (capital good)
    pairs: dict[str, TradingPair]                 # pair_id -> pair (all traded assets)
    agents: tuple[EntityId, ...]
    agent_labor: dict[EntityId, AssetId]          # each worker's labor asset
    firms: dict[EntityId, FirmState]
    gov: EntityId
    cb: EntityId
    exch: EntityId
    region_cap: dict[AssetId, int] = field(default_factory=dict)
    last_price: dict[str, int] = field(default_factory=dict)
    satiety: dict[EntityId, int] = field(default_factory=dict)
    macro: dict[str, int] = field(default_factory=dict)
    # finance (M5)
    investors: tuple[EntityId, ...] = ()
    bonds: tuple[Bond, ...] = ()
    equities: tuple[Equity, ...] = ()
    cb_policy_rate_bps: int = 0
    # politics (M6)
    politicians: tuple[EntityId, ...] = ()
    policy: dict[str, int] = field(default_factory=dict)   # e.g. tax_bps, welfare_bps

    def qty(self, e: EntityId, a: AssetId) -> int:
        return self.ledger.get(e, a)

    def cash(self, e: EntityId) -> int:
        return self.ledger.get(e, self.cur)

    def food_qty(self, e: EntityId) -> int:
        return self.ledger.get(e, self.food)

    def labor_assets(self) -> set[AssetId]:
        return set(self.agent_labor.values())

    def sorted_pairs(self) -> list[TradingPair]:
        """Pairs in canonical (pair_id lexicographic) clearing order (doc 03 3.7)."""
        return [self.pairs[k] for k in sorted(self.pairs)]

    def net_worth(self, e: EntityId) -> int:
        """NAV (doc 08 8.8): cash + bonds at face + equity at par + goods at last price.

        Single-currency slice: WUI == CUR:ALD, so no FX conversion is needed.
        """
        nw = self.cash(e)
        for b in self.bonds:
            nw += self.ledger.get(e, b.asset) * b.face
        for q in self.equities:
            nw += self.ledger.get(e, q.asset) * q.par
        for pair in self.pairs.values():
            if pair.base != self.cur:
                nw += self.ledger.get(e, pair.base) * self.last_price.get(pair.pair_id, 0)
        return nw
