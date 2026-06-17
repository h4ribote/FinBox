"""Engine-level market behaviors: resting GTC book, market buys, FX fee (doc 09)."""
from finbox.agents.scripted import ProtoOrder
from finbox.core.enums import MarketKind, OrderType, Side, TIF
from finbox.core.ids import AssetId
from finbox.engine import SkeletonEngine
from finbox.init import SkeletonConfig, genesis
from finbox.market.types import TradingPair


def _setup():
    c = SkeletonConfig()
    s = genesis(c)
    return c, s, SkeletonEngine(s, c)


def test_gtc_order_rests_across_turns():
    c, s, e = _setup()
    inv = s.investors[0]
    food_pair = s.pairs[f"{s.food}/{s.cur}"]
    # a GTC limit buy far below market never fills -> rests and re-participates
    gtc = ProtoOrder(inv, food_pair, Side.BUY, OrderType.LIMIT, 1, 3, tif=TIF.GTC)
    e.run_turn([gtc])
    assert len(s.resting_orders) == 1
    rid = s.resting_orders[0].order_id
    e.run_turn([])                       # no new external orders
    assert len(s.resting_orders) == 1
    assert s.resting_orders[0].order_id == rid   # same order carried, submit_seq preserved


def test_gft_order_does_not_rest():
    c, s, e = _setup()
    inv = s.investors[0]
    food_pair = s.pairs[f"{s.food}/{s.cur}"]
    gft = ProtoOrder(inv, food_pair, Side.BUY, OrderType.LIMIT, 1, 3, tif=TIF.GFT)
    e.run_turn([gft])
    assert s.resting_orders == []        # GFT never rests


def test_market_buy_clears_and_is_cash_bounded():
    c, s, e = _setup()
    inv = s.investors[0]
    food_pair = s.pairs[f"{s.food}/{s.cur}"]
    cash0, food0 = s.cash(inv), s.food_qty(inv)
    e.run_turn([ProtoOrder(inv, food_pair, Side.BUY, OrderType.MARKET, None, 2)])
    assert s.food_qty(inv) - food0 == 2
    assert 0 < cash0 - s.cash(inv)       # spent some cash
    assert s.cash(inv) >= 0              # never negative


def test_fx_pair_uses_lower_fee():
    c, s, e = _setup()
    goods = s.pairs[f"{s.food}/{s.cur}"]
    fx = TradingPair(s.cur, AssetId.cur("BOR"), MarketKind.FX)
    assert e._fee_bps(goods) == c.fee_rate_bps
    assert e._fee_bps(fx) == c.fx_fee_rate_bps
    assert e._band_bps(fx) == c.price_band_fx_bps


def test_currency_conserved_with_market_and_resting():
    c, s, e = _setup()
    inv = s.investors[0]
    food_pair = s.pairs[f"{s.food}/{s.cur}"]
    total = s.ledger.total_supply(s.cur)
    e.run_turn([ProtoOrder(inv, food_pair, Side.BUY, OrderType.LIMIT, 1, 3, tif=TIF.GTC)])
    e.run_turn([ProtoOrder(inv, food_pair, Side.BUY, OrderType.MARKET, None, 2)])
    assert s.ledger.total_supply(s.cur) == total
