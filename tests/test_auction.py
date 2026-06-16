"""Call-auction tests (doc 09 9.3, incl. the 9.3.6 numeric example)."""
import random

from finbox.core.enums import OrderType, Side, TIF
from finbox.core.ids import EntityId
from finbox.market import clear
from finbox.market.types import Order

PAIR = "COMM:agri.grain/CUR:ALD"


def _o(seq, side, otype, price, qty):
    return Order(f"ORD:{seq:04d}", EntityId.agent(seq % 999 + 1), PAIR, side, otype, price, qty, seq, TIF.GFT)


def _doc_example_orders():
    o = []
    s = 0
    for price, q in [(35, 60), (36, 40), (37, 30), (38, 20)]:
        o.append(_o(s, Side.BUY, OrderType.LIMIT, price, q)); s += 1
    for price, q in [(39, 50), (38, 40), (37, 30), (36, 10)]:
        o.append(_o(s, Side.SELL, OrderType.LIMIT, price, q)); s += 1
    o.append(_o(s, Side.BUY, OrderType.MARKET, None, 10)); s += 1
    return o


def test_doc_936_example():
    res = clear(PAIR, _doc_example_orders(), p_ref=36)
    assert res.p_star == 37
    assert res.q_star == 40
    assert res.imbalance == 20  # D(37)=60, S(37)=40
    # short side (sells, total 40) fully filled; buys (total 70 eligible) get 40
    filled_sell = sum(f.qty for f in res.fills if f.side is Side.SELL)
    filled_buy = sum(f.qty for f in res.fills if f.side is Side.BUY)
    assert filled_sell == 40
    assert filled_buy == 40


def test_order_independence():
    base = clear(PAIR, _doc_example_orders(), p_ref=36)
    for seed in range(20):
        shuffled = _doc_example_orders()
        random.Random(seed).shuffle(shuffled)
        res = clear(PAIR, shuffled, p_ref=36)
        assert (res.p_star, res.q_star) == (base.p_star, base.q_star)


def test_no_cross_keeps_ref_price():
    orders = [_o(0, Side.BUY, OrderType.LIMIT, 10, 5), _o(1, Side.SELL, OrderType.LIMIT, 20, 5)]
    res = clear(PAIR, orders, p_ref=15)
    assert res.q_star == 0
    assert res.p_star == 15  # last price preserved


def test_empty_book():
    res = clear(PAIR, [], p_ref=42)
    assert res.q_star == 0 and res.p_star == 42 and res.fills == ()


def test_simple_cross():
    orders = [_o(0, Side.BUY, OrderType.LIMIT, 12, 5), _o(1, Side.SELL, OrderType.LIMIT, 8, 5)]
    res = clear(PAIR, orders, p_ref=10)
    assert res.q_star == 5
    assert 8 <= res.p_star <= 12
    assert sum(f.qty for f in res.fills if f.side is Side.BUY) == 5


def test_price_time_priority_on_long_side():
    # two sellers tie price; buyer takes 5 -> earlier submit_seq filled first
    orders = [
        _o(0, Side.BUY, OrderType.LIMIT, 10, 5),
        _o(1, Side.SELL, OrderType.LIMIT, 10, 4),   # earlier
        _o(2, Side.SELL, OrderType.LIMIT, 10, 4),   # later
    ]
    res = clear(PAIR, orders, p_ref=10)
    assert res.q_star == 5
    fills = {f.order_id: f.qty for f in res.fills}
    assert fills.get("ORD:0001") == 4   # earlier seller fully filled
    assert fills.get("ORD:0002") == 1   # later seller gets the remainder
