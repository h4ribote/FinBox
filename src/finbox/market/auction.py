"""Single-price call auction / itayose (doc 09 9.3).

Deterministic clearing: maximize volume, then minimize imbalance, then nearest
to reference price, then a price-pressure tiebreak. Short side fills fully; the
long side is allocated by price -> time priority (doc 09 9.6.2).
"""
from __future__ import annotations
from collections.abc import Sequence

from ..core.enums import OrderType, Side
from .types import ClearResult, Fill, Order


def _demand(buys: Sequence[Order], p: int) -> int:
    return sum(o.qty for o in buys if o.order_type is OrderType.MARKET or o.limit_price >= p)


def _supply(sells: Sequence[Order], p: int) -> int:
    return sum(o.qty for o in sells if o.order_type is OrderType.MARKET or o.limit_price <= p)


def _allocate_long(long_orders: Sequence[Order], total: int, side: Side) -> dict[str, int]:
    """Allocate ``total`` over the long side by price -> time priority (doc 09 9.6.2).

    Most aggressive first: MARKET, then (BUY) higher limit / (SELL) lower limit;
    same price breaks by submit_seq ascending (time priority).
    """
    def rank(o: Order) -> tuple:
        if o.order_type is OrderType.MARKET:
            price_key = (0,)            # most aggressive
        elif side is Side.BUY:
            price_key = (1, -o.limit_price)   # higher limit first
        else:
            price_key = (1, o.limit_price)    # lower limit first
        return (price_key, o.submit_seq)

    out: dict[str, int] = {}
    remaining = total
    for o in sorted(long_orders, key=rank):
        if remaining <= 0:
            break
        f = min(remaining, o.qty)
        out[o.order_id] = f
        remaining -= f
    return out


def clear(pair_id: str, orders: Sequence[Order], p_ref: int) -> ClearResult:
    """Compute the single clearing price and fills for one pair (doc 09 9.3)."""
    buys = [o for o in orders if o.side is Side.BUY]
    sells = [o for o in orders if o.side is Side.SELL]

    candidates = {o.limit_price for o in orders if o.order_type is not OrderType.MARKET}
    candidates.add(p_ref)
    # price-pressure direction at the reference price (doc 09 9.3.3 step 4)
    buy_pressure = _demand(buys, p_ref) >= _supply(sells, p_ref)

    best_p: int | None = None
    best_key: tuple | None = None
    for p in sorted(candidates, reverse=True):
        d, s = _demand(buys, p), _supply(sells, p)
        v = min(d, s)
        key = (v, -abs(d - s), -abs(p - p_ref), p if buy_pressure else -p)
        if best_key is None or key > best_key:
            best_key, best_p = key, p
    assert best_p is not None
    p_star = best_p

    d_star, s_star = _demand(buys, p_star), _supply(sells, p_star)
    q_star = min(d_star, s_star)
    if q_star == 0:
        # no cross: keep last price (p_ref), no fills (doc 09 9.3.5)
        return ClearResult(pair_id, p_ref, 0, (), d_star - s_star)

    fill_buys = [o for o in buys if o.order_type is OrderType.MARKET or o.limit_price >= p_star]
    fill_sells = [o for o in sells if o.order_type is OrderType.MARKET or o.limit_price <= p_star]
    sum_b = sum(o.qty for o in fill_buys)
    sum_s = sum(o.qty for o in fill_sells)

    if sum_b <= sum_s:
        short, long_, short_side, long_side = fill_buys, fill_sells, Side.BUY, Side.SELL
    else:
        short, long_, short_side, long_side = fill_sells, fill_buys, Side.SELL, Side.BUY

    qty_by_order: dict[str, int] = {o.order_id: o.qty for o in short}      # short side fully filled
    qty_by_order.update(_allocate_long(long_, q_star, long_side))           # long side rationed

    by_id = {o.order_id: o for o in orders}
    fills = tuple(
        Fill(oid, by_id[oid].entity_id, by_id[oid].side, q)
        for oid, q in qty_by_order.items() if q > 0
    )
    return ClearResult(pair_id, p_star, q_star, fills, d_star - s_star)
