"""StateStore: the single authoritative world state (doc 02 2.2).

M4 slice: a one-country multi-firm supply chain (manufacturing -> agriculture,
plus construction supplying capital) with capacity, several labor types, and a
market pair per traded asset. Mutated only by the engine; serialized for replay.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from ..core.enums import MarketKind
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
    region_cap: dict = field(default_factory=dict)   # region_cap[asset_id][region_id] (doc 04 4.3.1)
    last_price: dict[str, int] = field(default_factory=dict)
    # agent need states (doc 05 5.2), held as fixed-point x1000 (0..100000); engine-only
    satiety: dict[EntityId, int] = field(default_factory=dict)
    health: dict[EntityId, int] = field(default_factory=dict)
    stamina: dict[EntityId, int] = field(default_factory=dict)
    rest: dict[EntityId, int] = field(default_factory=dict)
    stress: dict[EntityId, int] = field(default_factory=dict)
    happiness: dict[EntityId, int] = field(default_factory=dict)
    skill: dict = field(default_factory=dict)             # entity -> {labor_kind: skill x1000}
    age: dict[EntityId, int] = field(default_factory=dict)         # ticks lived
    starve_streak: dict[EntityId, int] = field(default_factory=dict)
    deceased: set = field(default_factory=set)            # DECEASED agents (doc 05 5.4)
    labored: set = field(default_factory=set)             # transient: agents who supplied labor this turn
    # physical world (doc 04): 9216 cells + agent residency
    cells: dict = field(default_factory=dict)             # CellId -> Cell (doc 04 4.2)
    home_cell: dict = field(default_factory=dict)         # agent -> CellId (doc 05 5.1)
    # deterministic display names (doc 16 16.14); flavor only, never affects logic
    names: dict = field(default_factory=dict)             # "COUNTRY:ALD"/"CUR:ALD"/entity_id -> name
    macro: dict[str, int] = field(default_factory=dict)
    # finance (M5)
    investors: tuple[EntityId, ...] = ()
    bonds: tuple[Bond, ...] = ()
    equities: tuple[Equity, ...] = ()
    cb_policy_rate_bps: int = 0
    paid_in_capital: dict = field(default_factory=dict)   # firm -> paid-in capital (doc 11 11.6.2)
    # politics (M6)
    politicians: tuple[EntityId, ...] = ()
    policy: dict[str, int] = field(default_factory=dict)   # e.g. tax_bps, welfare_bps, min_wage
    # resting GTC/GTT order book carried across turns (doc 09 9.4.2); empty for GFT-only flows
    resting_orders: list = field(default_factory=list)
    # per-tick Action Log of collected pre-validation intents (doc 02 2.6.1/2.6.2)
    action_log: list = field(default_factory=list)
    # submitted politician votes pending P3 GOVERN aggregation: {country: {lever: [(kind, payload)]}}
    pending_votes: dict = field(default_factory=dict)
    # ML control (M9): agents whose consumption order is supplied externally (RL policy),
    # not by the scripted policy. Control metadata only; not part of the serialized state.
    rl_agents: set = field(default_factory=set)

    def qty(self, e: EntityId, a: AssetId) -> int:
        return self.ledger.get(e, a)

    def cash(self, e: EntityId) -> int:
        return self.ledger.get(e, self.cur)

    def food_qty(self, e: EntityId) -> int:
        return self.ledger.get(e, self.food)

    def labor_assets(self) -> set[AssetId]:
        return set(self.agent_labor.values())

    def region_cap_for(self, asset: AssetId, region: str) -> int:
        """Per-region extraction cap region_cap[asset_id][region_id] (doc 04 4.3.1)."""
        return self.region_cap.get(asset, {}).get(region, 0)

    def sorted_pairs(self) -> list[TradingPair]:
        """Pairs in canonical (pair_id lexicographic) clearing order (doc 03 3.7)."""
        return [self.pairs[k] for k in sorted(self.pairs)]

    def net_worth(self, e: EntityId) -> int:
        """NAV (doc 08 8.8.1 / doc 11 11.9.2): mark every position at the last board-clearing
        price (face/par only as the genesis fallback before any trade).

        Single-currency slice: WUI == CUR:ALD, so no FX conversion is needed.
        """
        nw = self.cash(e)
        for b in self.bonds:
            pid = f"{b.asset_id}/{self.cur}"
            nw += self.ledger.get(e, b.asset_id) * self.last_price.get(pid, b.face)
        for q in self.equities:
            pid = f"{q.asset_id}/{self.cur}"
            nw += self.ledger.get(e, q.asset_id) * self.last_price.get(pid, q.par)
        for pair in self.pairs.values():
            if pair.kind in (MarketKind.BOND, MarketKind.EQUITY):
                continue   # bonds/equities already marked above (avoid double counting)
            if pair.base != self.cur:
                nw += self.ledger.get(e, pair.base) * self.last_price.get(pair.pair_id, 0)
        return nw

    def distributable_profit(self, firm: EntityId) -> int:
        """Retained earnings backed by cash = cash above paid-in capital (doc 11 11.6.2)."""
        return max(0, self.cash(firm) - self.paid_in_capital.get(firm, 0))
