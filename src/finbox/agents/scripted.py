"""Deterministic scripted policy for the M3 economy (doc 07 stub).

Workers supply labor and bid for food when hungry; the firm offers its food
inventory and bids for labor to refill toward its production target. Everyone
quotes at the last clearing price, so each market clears at that price with
quantity = min(supply, demand). Output is unvalidated intent (P1).
"""
from __future__ import annotations
from dataclasses import dataclass

from ..core.enums import OrderType, Side
from ..core.ids import EntityId
from ..market.types import TradingPair


@dataclass(frozen=True, slots=True)
class ProtoOrder:
    entity: EntityId
    pair: TradingPair
    side: Side
    order_type: OrderType
    limit_price: int | None
    qty: int


def generate_orders(store, config) -> list[ProtoOrder]:
    out: list[ProtoOrder] = []
    food_px = store.last_price[store.pair.pair_id]
    wage = store.last_price[store.labor_pair.pair_id]

    # firm: sell food inventory; buy labor to refill toward the production target
    fq = store.food_qty(store.firm)
    if fq > 0:
        out.append(ProtoOrder(store.firm, store.pair, Side.SELL, OrderType.LIMIT, food_px, fq))
    deficit = max(0, config.firm_food_target - fq)
    fpl = config.food_per_labor
    labor_need = min((deficit + fpl - 1) // fpl,
                     (config.region_cap_food + fpl - 1) // fpl)
    if labor_need > 0:
        out.append(ProtoOrder(store.firm, store.labor_pair, Side.BUY, OrderType.LIMIT, wage, labor_need))

    # workers: sell the labor they produced this turn; buy food when hungry
    for a in store.agents:
        lq = store.qty(a, store.labor)
        if lq > 0:
            out.append(ProtoOrder(a, store.labor_pair, Side.SELL, OrderType.LIMIT, wage, lq))
        if store.satiety[a] < config.satiety_buy_threshold and store.cash(a) > 0:
            need = (100 - store.satiety[a] + config.satiety_per_food - 1) // config.satiety_per_food
            if need > 0:
                out.append(ProtoOrder(a, store.pair, Side.BUY, OrderType.LIMIT, food_px, need))
    return out
