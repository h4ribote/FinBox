"""Deterministic scripted policy for the M4 supply-chain economy (doc 07 stub).

Each firm offers its output inventory, bids for the inputs its capacity needs,
and (if it expands) buys construction labor. Workers supply their labor kind and
bid for food when hungry. Everyone quotes the last clearing price.
"""
from __future__ import annotations
from dataclasses import dataclass

from ..core.enums import OrderType, Side, TIF
from ..core.ids import AssetId, EntityId
from ..domain.needs import SCALE as NEED_SCALE
from ..market.types import TradingPair


@dataclass(frozen=True, slots=True)
class ProtoOrder:
    entity: EntityId
    pair: TradingPair
    side: Side
    order_type: OrderType
    limit_price: int | None
    qty: int
    tif: TIF = TIF.GFT
    expires_tick: int | None = None     # GTT failure tick (doc 09 9.4.2)
    qty_visible: int | None = None      # iceberg visible slice (doc 09 9.4.4)


def _pair(store, base: AssetId) -> TradingPair:
    return store.pairs[f"{base}/{store.cur}"]


def generate_orders(store, config) -> list[ProtoOrder]:
    out: list[ProtoOrder] = []
    scale = config.recipe_yield_scale
    buf = config.target_output_stock

    for fid in sorted(store.firms):
        fs = store.firms[fid]
        if getattr(fs, "state", None) is not None and fs.state.value == "LIQUIDATING":
            continue                                 # liquidated firms no longer trade (doc 10.8.5)
        r = fs.recipe
        for outp in r.outputs:                       # sell finished inventory
            held = store.qty(fid, outp)
            if held > 0:
                p = _pair(store, outp)
                out.append(ProtoOrder(fid, p, Side.SELL, OrderType.LIMIT, store.last_price[p.pair_id], held))
        # target run count: capacity, region cap (extractive), and an output-inventory buffer so a
        # firm throttles production toward sellable demand instead of overproducing into bankruptcy
        run_target = fs.capacity // r.capacity_cost
        if r.region_capped_output is not None:
            opr = r.outputs[r.region_capped_output] * scale
            cap = store.region_cap_for(r.region_capped_output, fs.region_id)
            run_target = min(run_target, cap // opr if opr else run_target)
        for outp, q in r.outputs.items():            # keep each output's stock near the buffer
            per_run = q * scale
            headroom = max(0, buf - store.qty(fid, outp))
            if per_run > 0:
                run_target = min(run_target, -(-headroom // per_run))   # ceil division
        run_target = max(0, run_target)
        for inp, q in r.inputs.items():              # buy inputs for the target run count
            need = run_target * q - store.qty(fid, inp)
            if need > 0:
                p = _pair(store, inp)
                out.append(ProtoOrder(fid, p, Side.BUY, OrderType.LIMIT, store.last_price[p.pair_id], need))
        # buy construction labor to offset depreciation and grow toward the cap, while cash is healthy
        # (a firm maintains its capital stock but does not expand into insolvency)
        if (fs.expands and fs.capacity < config.capacity_max_for(fs.industry)
                and store.cash(fid) > config.firm_expand_min_cash):
            p = _pair(store, store.build)
            out.append(ProtoOrder(fid, p, Side.BUY, OrderType.LIMIT, store.last_price[p.pair_id], config.firm_expand_buy))

    for a in store.agents:
        if a in store.deceased:
            continue
        la = store.agent_labor[a]
        lq = store.qty(a, la)
        if lq > 0:
            p = _pair(store, la)
            out.append(ProtoOrder(a, p, Side.SELL, OrderType.LIMIT, store.last_price[p.pair_id], lq))
        # RL-controlled agents get their food order from the policy (injected externally)
        if a in store.rl_agents:
            continue
        sat_pct = store.satiety[a] // NEED_SCALE                       # needs held x1000 (doc 05 5.2)
        if sat_pct < config.satiety_buy_threshold and store.cash(a) > 0:
            need = (100 - sat_pct + config.satiety_per_food - 1) // config.satiety_per_food
            if need > 0:
                p = _pair(store, store.food)
                out.append(ProtoOrder(a, p, Side.BUY, OrderType.LIMIT, store.last_price[p.pair_id], need))
    return out

