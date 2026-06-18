"""Single-price call auction / itayose (doc 09 9.3).

Deterministic clearing: maximize volume, then minimize imbalance, then nearest to
reference price, then a price-pressure tiebreak (9.3.3). For labor pairs the result
is floored at min_wage (9.3.7); there is no price-band / circuit-breaker clamp — the
clearing price is the volume-maximizing value with no bound on its distance from the
reference (doc 09, "値幅制限の撤廃"). The short side fills fully; the long side is
allocated by price -> time priority, with pro-rata (largest-remainder) at the single
boundary level (9.6.2). FOK orders never move p* and are judged after it is fixed (9.4.3).
"""
from __future__ import annotations
from collections.abc import Sequence
from itertools import groupby

from ..core.enums import OrderType, Side
from ..core.fixed import largest_remainder
from .types import ClearResult, Fill, Order


def _eq(o: Order) -> int:
    """Quantity participating in the auction (iceberg shows only qty_visible)."""
    return o.visible_qty


def _demand(buys: Sequence[Order], p: int) -> int:
    # limit_price is None => unconditional (MARKET, or market-like IOC/FOK)
    return sum(_eq(o) for o in buys if o.limit_price is None or o.limit_price >= p)


def _supply(sells: Sequence[Order], p: int) -> int:
    return sum(_eq(o) for o in sells if o.limit_price is None or o.limit_price <= p)


def _price_key(o: Order, side: Side) -> tuple:
    """Most-aggressive-first key: unconditional (no limit), then better limit (BUY high / SELL low)."""
    if o.limit_price is None:
        return (0,)
    return (1, -o.limit_price) if side is Side.BUY else (1, o.limit_price)


def _allocate_long(long_orders: Sequence[Order], total: int, side: Side,
                   cap: dict[str, int] | None = None) -> dict[str, int]:
    """Allocate ``total`` over the long side by price -> time -> pro-rata (doc 09 9.6.2).

    Complete price levels (by aggressiveness) fill fully; the single boundary level
    that does not fit is split pro-rata by quantity via largest-remainder, ties by
    submit_seq ascending. ``cap`` overrides the per-order fillable quantity
    (used for iceberg visible size and FOK counter-residuals).
    """
    def fillable(o: Order) -> int:
        return cap[o.order_id] if cap is not None else _eq(o)

    out: dict[str, int] = {}
    remaining = total
    ordered = sorted(long_orders, key=lambda o: (_price_key(o, side), o.submit_seq))
    for _, grp in groupby(ordered, key=lambda o: _price_key(o, side)):
        if remaining <= 0:
            break
        level = [o for o in grp if fillable(o) > 0]
        level_total = sum(fillable(o) for o in level)
        if level_total <= remaining:
            for o in level:
                out[o.order_id] = fillable(o)
            remaining -= level_total
        else:
            # boundary level: pro-rata by quantity, remainder ties by submit_seq asc (9.6.2)
            level.sort(key=lambda o: o.submit_seq)
            alloc = largest_remainder(remaining, [fillable(o) for o in level])
            for o, q in zip(level, alloc):
                if q > 0:
                    out[o.order_id] = q
            remaining = 0
            break
    return out


def _judge_fok(foks: Sequence[Order], p_star: int, buys: Sequence[Order],
               sells: Sequence[Order], fills: dict[str, int]) -> None:
    """Fill-or-kill judgment after p* is fixed by the other orders (doc 09 9.4.3).

    Each FOK (in submit_seq order) fills fully iff the residual counter-side capacity
    at p* covers its qty; otherwise it is killed. FOK never moves p*.
    """
    for o in sorted(foks, key=lambda x: x.submit_seq):
        price_ok = o.order_type is OrderType.MARKET or (
            o.limit_price is not None
            and (o.limit_price >= p_star if o.side is Side.BUY else o.limit_price <= p_star))
        if not price_ok:
            continue
        counter = sells if o.side is Side.BUY else buys
        elig = [c for c in counter
                if c.limit_price is None
                or (o.side is Side.BUY and c.limit_price <= p_star)
                or (o.side is Side.SELL and c.limit_price >= p_star)]
        residual = {c.order_id: _eq(c) - fills.get(c.order_id, 0) for c in elig}
        if sum(max(0, v) for v in residual.values()) < o.qty:
            continue  # cannot fill in full -> kill
        fills[o.order_id] = fills.get(o.order_id, 0) + o.qty
        cap = {oid: v for oid, v in residual.items() if v > 0}
        for oid, q in _allocate_long([c for c in elig if residual[c.order_id] > 0],
                                     o.qty, Side.SELL if o.side is Side.BUY else Side.BUY,
                                     cap=cap).items():
            fills[oid] = fills.get(oid, 0) + q


def clear(pair_id: str, orders: Sequence[Order], p_ref: int,
          min_wage: int = 0) -> ClearResult:
    """Compute the single clearing price and fills for one pair (doc 09 9.3/9.3.7)."""
    # FOK orders do not participate in price formation (doc 09 9.4.3)
    price_orders = [o for o in orders if o.order_type is not OrderType.FOK]
    fok_orders = [o for o in orders if o.order_type is OrderType.FOK]
    buys = [o for o in price_orders if o.side is Side.BUY]
    sells = [o for o in price_orders if o.side is Side.SELL]

    candidates = {o.limit_price for o in price_orders
                  if o.order_type is not OrderType.MARKET and o.limit_price is not None}
    candidates.add(p_ref)
    buy_pressure = _demand(buys, p_ref) >= _supply(sells, p_ref)

    best_p: int | None = None
    best_key: tuple | None = None
    for p in sorted(candidates, reverse=True):
        d, s = _demand(buys, p), _supply(sells, p)
        v = min(d, s)
        key = (v, -abs(d - s), -abs(p - p_ref), p if buy_pressure else -p)
        if best_key is None or key > best_key:
            best_key, best_p = key, p
    p_star = best_p if best_p is not None else p_ref

    # labor min_wage floor (doc 09 9.3.7): a political lower bound on the wage, not a
    # price-band clamp. Excess supply above the floor goes unfilled (= unemployment).
    if min_wage > 0 and p_star < min_wage:
        p_star = min_wage

    d_star, s_star = _demand(buys, p_star), _supply(sells, p_star)
    q_star = min(d_star, s_star)

    fills_map: dict[str, int] = {}
    if q_star > 0:
        fill_buys = [o for o in buys if o.limit_price is None or o.limit_price >= p_star]
        fill_sells = [o for o in sells if o.limit_price is None or o.limit_price <= p_star]
        sum_b = sum(_eq(o) for o in fill_buys)
        sum_s = sum(_eq(o) for o in fill_sells)
        if sum_b <= sum_s:
            short, long_, long_side = fill_buys, fill_sells, Side.SELL
        else:
            short, long_, long_side = fill_sells, fill_buys, Side.BUY
        for o in short:                       # short side fully filled
            fills_map[o.order_id] = _eq(o)
        fills_map.update(_allocate_long(long_, q_star, long_side))   # long side rationed

    _judge_fok(fok_orders, p_star, buys, sells, fills_map)           # FOK after p* fixed

    by_id = {o.order_id: o for o in orders}
    fills = tuple(
        Fill(oid, by_id[oid].entity_id, by_id[oid].side, q)
        for oid, q in fills_map.items() if q > 0
    )
    if not fills:
        # no cross: keep last price (p_ref), no fills (doc 09 9.3.5)
        return ClearResult(pair_id, p_ref, 0, (), d_star - s_star)
    matched = sum(q for oid, q in fills_map.items() if by_id[oid].side is Side.BUY)
    return ClearResult(pair_id, p_star, matched, fills, d_star - s_star)
