"""Deterministic scripted policy for the M4 supply-chain economy (doc 07 stub).

Each firm offers its output inventory, bids for the inputs its capacity needs,
and (if it expands) buys construction labor. Workers supply their labor kind and
bid for food when hungry. Everyone quotes the last clearing price.
"""
from __future__ import annotations
from dataclasses import dataclass

from ..core.enums import OrderType, Side
from ..core.ids import AssetId, EntityId
from ..market.types import TradingPair


@dataclass(frozen=True, slots=True)
class ProtoOrder:
    entity: EntityId
    pair: TradingPair
    side: Side
    order_type: OrderType
    limit_price: int | None
    qty: int


def _pair(store, base: AssetId) -> TradingPair:
    return store.pairs[f"{base}/{store.cur}"]


def generate_orders(store, config) -> list[ProtoOrder]:
    out: list[ProtoOrder] = []

    for fid in sorted(store.firms):
        fs = store.firms[fid]
        r = fs.recipe
        for outp in r.outputs:                       # sell finished inventory
            held = store.qty(fid, outp)
            if held > 0:
                p = _pair(store, outp)
                out.append(ProtoOrder(fid, p, Side.SELL, OrderType.LIMIT, store.last_price[p.pair_id], held))
        for inp, q in r.inputs.items():              # buy inputs to run at capacity
            need = fs.capacity * q - store.qty(fid, inp)
            if need > 0:
                p = _pair(store, inp)
                out.append(ProtoOrder(fid, p, Side.BUY, OrderType.LIMIT, store.last_price[p.pair_id], need))
        if fs.expands and fs.capacity < config.capacity_max:   # buy capital good to grow
            p = _pair(store, store.build)
            out.append(ProtoOrder(fid, p, Side.BUY, OrderType.LIMIT, store.last_price[p.pair_id], config.firm_expand_buy))

    for a in store.agents:
        la = store.agent_labor[a]
        lq = store.qty(a, la)
        if lq > 0:
            p = _pair(store, la)
            out.append(ProtoOrder(a, p, Side.SELL, OrderType.LIMIT, store.last_price[p.pair_id], lq))
        # RL-controlled agents get their food order from the policy (injected externally)
        if a in store.rl_agents:
            continue
        if store.satiety[a] < config.satiety_buy_threshold and store.cash(a) > 0:
            need = (100 - store.satiety[a] + config.satiety_per_food - 1) // config.satiety_per_food
            if need > 0:
                p = _pair(store, store.food)
                out.append(ProtoOrder(a, p, Side.BUY, OrderType.LIMIT, store.last_price[p.pair_id], need))
    return out

