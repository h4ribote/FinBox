"""Deterministic scripted policy for the walking skeleton (doc 07 stub).

The producer firm offers its food inventory; hungry agents bid for food. Both
quote at the last clearing price, so the auction clears at that price with
quantity = min(supply, demand). Output is unvalidated intent (P1); the engine
clamps it in P2.
"""
from __future__ import annotations
from dataclasses import dataclass

from ..core.enums import OrderType, Side
from ..core.ids import EntityId


@dataclass(frozen=True, slots=True)
class ProtoOrder:
    entity: EntityId
    side: Side
    order_type: OrderType
    limit_price: int | None
    qty: int


def generate_orders(store, config) -> list[ProtoOrder]:
    out: list[ProtoOrder] = []
    price = store.last_price[store.pair.pair_id]

    # firm sells its current food inventory at the last price
    fq = store.food_qty(store.firm)
    if fq > 0:
        out.append(ProtoOrder(store.firm, Side.SELL, OrderType.LIMIT, price, fq))

    # hungry agents bid for enough food to refill satiety
    for a in store.agents:
        if store.satiety[a] < config.satiety_buy_threshold and store.cash(a) > 0:
            deficit = 100 - store.satiety[a]
            need = (deficit + config.satiety_per_food - 1) // config.satiety_per_food
            if need > 0:
                out.append(ProtoOrder(a, Side.BUY, OrderType.LIMIT, price, need))
    return out
