"""Margin trading (信用取引): lending pools, leverage, interest, forced liquidation, insurance.

These exercise the doc 09 §信用取引 machinery, which is inert in the default scripted economy
(no one opens margin positions) and so must be driven explicitly. The conservation law (doc 00
0.17) must hold throughout: lending/repay/interest/liquidation are all real-asset transfers.
"""
from finbox.agents.scripted import ProtoOrder
from finbox.core.enums import OrderType, PositionSide, Side, TradeMode
from finbox.engine import SkeletonEngine
from finbox.init import SkeletonConfig, genesis


def _setup():
    c = SkeletonConfig()
    s = genesis(c)
    return c, s, SkeletonEngine(s, c)


def _eq_pair(s):
    pid = next(p for p in s.pairs if p.startswith("EQ:firm.000001/"))
    return s.pairs[pid]


def test_genesis_seeds_currency_pool_and_insurance():
    c, s, e = _setup()
    pool = s.lending_pools[str(s.cur)]
    assert pool.supplied == c.lending_genesis_supply_cur
    assert s.ledger.get(pool.entity_id, s.cur) == c.lending_genesis_supply_cur
    insf = s.insurance[str(s.cur)]
    assert s.ledger.get(insf, s.cur) == c.insurance_genesis_seed
    # every margin-eligible asset has a pool object (CUR + 3 EQ + 3 storable COMM)
    assert str(s.cur) in s.lending_pools
    assert any(a.startswith("EQ:") for a in s.lending_pools)


def test_margin_long_equity_leverages_and_conserves():
    c, s, e = _setup()
    inv, trader = s.investors[0], s.agents[0]
    pair = _eq_pair(s)
    px = s.last_price[pair.pair_id]
    cur0, eq0 = s.ledger.total_supply(s.cur), s.ledger.total_supply(pair.base)
    sell = ProtoOrder(inv, pair, Side.SELL, OrderType.LIMIT, px, 20)
    longp = ProtoOrder(trader, pair, Side.BUY, OrderType.LIMIT, px, 20,
                       trade_mode=TradeMode.MARGIN, position_side=PositionSide.LONG)
    e.run_turn([sell, longp])
    pos = [p for p in s.positions if p.entity == trader]
    assert len(pos) == 1 and pos[0].side is PositionSide.LONG
    assert pos[0].qty == 20 and pos[0].borrowed_asset == s.cur
    # ~5x leverage: borrowed ≈ 80% of notional (initial margin 20%)
    notional = 20 * px
    assert notional * 7500 // 10000 <= pos[0].borrowed_qty <= notional * 8000 // 10000 + px
    # conservation: LOAN + TRADE are pure transfers
    assert s.ledger.total_supply(s.cur) == cur0
    assert s.ledger.total_supply(pair.base) == eq0
    # the lending pool actually lent currency out
    assert s.lending_pools[str(s.cur)].borrowed == pos[0].borrowed_qty


def test_margin_short_equity_borrows_and_conserves():
    c, s, e = _setup()
    inv, trader = s.investors[0], s.agents[0]
    pair = _eq_pair(s)
    px = s.last_price[pair.pair_id]
    e.margin.pool_supply(inv, pair.base, 50)            # investor lends EQ into the pool
    cur0, eq0 = s.ledger.total_supply(s.cur), s.ledger.total_supply(pair.base)
    buy = ProtoOrder(inv, pair, Side.BUY, OrderType.LIMIT, px, 20)
    shortp = ProtoOrder(trader, pair, Side.SELL, OrderType.LIMIT, px, 20,
                        trade_mode=TradeMode.MARGIN, position_side=PositionSide.SHORT)
    e.run_turn([buy, shortp])
    pos = [p for p in s.positions if p.entity == trader]
    assert len(pos) == 1 and pos[0].side is PositionSide.SHORT
    assert pos[0].borrowed_asset == pair.base and pos[0].borrowed_qty == 20
    assert s.ledger.total_supply(s.cur) == cur0
    assert s.ledger.total_supply(pair.base) == eq0


def test_pool_supply_and_withdraw_roundtrip():
    c, s, e = _setup()
    inv = s.investors[0]
    pair = _eq_pair(s)
    eq0 = s.ledger.get(inv, pair.base)
    shares = e.margin.pool_supply(inv, pair.base, 30)
    assert shares == 30 and s.ledger.get(inv, pair.base) == eq0 - 30
    pool = s.lending_pools[str(pair.base)]
    assert s.ledger.get(pool.entity_id, pair.base) == 30
    back = e.margin.pool_withdraw(inv, pair.base, shares)
    assert back == 30 and s.ledger.get(inv, pair.base) == eq0      # fully redeemed
    assert s.ledger.total_supply(pair.base) == eq0 + 0            # conserved (it never left the system)


def test_margin_interest_accrues_to_pool():
    c, s, e = _setup()
    inv, trader = s.investors[0], s.agents[0]
    pair = _eq_pair(s)
    px = s.last_price[pair.pair_id]
    pool = s.lending_pools[str(s.cur)]
    cur0 = s.ledger.total_supply(s.cur)
    e.run_turn([ProtoOrder(inv, pair, Side.SELL, OrderType.LIMIT, px, 20),
                ProtoOrder(trader, pair, Side.BUY, OrderType.LIMIT, px, 20,
                           trade_mode=TradeMode.MARGIN, position_side=PositionSide.LONG)])
    assert s.positions, "a margin position should be open"
    pool_cur_after_open = s.ledger.get(pool.entity_id, s.cur)
    insf = s.insurance[str(s.cur)]
    ins0 = s.ledger.get(insf, s.cur)
    trader_cash = s.cash(trader)
    e.run_turn([])                       # a full turn -> P7 interest accrues
    assert s.cash(trader) < trader_cash                       # borrower paid interest
    assert s.ledger.get(pool.entity_id, s.cur) + s.ledger.get(insf, s.cur) \
        > pool_cur_after_open + ins0                          # interest landed in pool + insurance
    assert s.ledger.total_supply(s.cur) == cur0               # interest is redistribution, conserves


def test_forced_liquidation_on_margin_breach():
    c, s, e = _setup()
    inv, trader = s.investors[0], s.agents[0]
    pair = _eq_pair(s)
    px = s.last_price[pair.pair_id]
    cur0, eq0 = s.ledger.total_supply(s.cur), s.ledger.total_supply(pair.base)
    e.run_turn([ProtoOrder(inv, pair, Side.SELL, OrderType.LIMIT, px, 20),
                ProtoOrder(trader, pair, Side.BUY, OrderType.LIMIT, px, 20,
                           trade_mode=TradeMode.MARGIN, position_side=PositionSide.LONG)])
    pos = [p for p in s.positions if p.entity == trader][0]
    qty0 = pos.qty
    # crash the mark below maintenance, and provide a deep bid for the liquidation SELL to hit
    s.last_price[pair.pair_id] = px * 85 // 100
    ins_before = s.ledger.get(s.insurance[str(s.cur)], s.cur)
    e.run_turn([ProtoOrder(inv, pair, Side.BUY, OrderType.LIMIT, px * 85 // 100, 50)])
    remaining = [p for p in s.positions if p.entity == trader]
    assert (not remaining) or remaining[0].qty < qty0          # position force-reduced/closed
    assert s.ledger.get(s.insurance[str(s.cur)], s.cur) >= ins_before   # penalty -> insurance
    assert s.ledger.total_supply(s.cur) == cur0                # liquidation conserves CUR
    assert s.ledger.total_supply(pair.base) == eq0


def test_amm_pool_seeded_when_enabled():
    c = SkeletonConfig(amm_enabled=True)
    s = genesis(c)
    pair = _eq_pair(s)
    amm = s.amm_pools[pair.pair_id]
    assert amm.r_quote == c.amm_genesis_seed and amm.r_base > 0
    assert s.ledger.get(amm.entity_id, s.cur) == c.amm_genesis_seed
    assert s.ledger.get(amm.entity_id, pair.base) == amm.r_base


def test_amm_provides_liquidity_and_conserves():
    # with the AMM enabled, a taker BUY fills against the AMM ladder; reserves shift, all conserved
    c = SkeletonConfig(amm_enabled=True)
    s = genesis(c)
    e = SkeletonEngine(s, c)
    inv = s.investors[0]
    pair = _eq_pair(s)
    amm = s.amm_pools[pair.pair_id]
    r_base0, r_quote0 = amm.r_base, amm.r_quote
    cur0, eq0 = s.ledger.total_supply(s.cur), s.ledger.total_supply(pair.base)
    # a generous taker BUY should lift base off the AMM ask ladder
    e.run_turn([ProtoOrder(inv, pair, Side.BUY, OrderType.LIMIT, s.last_price[pair.pair_id] * 2, 5)])
    assert amm.r_base < r_base0 and amm.r_quote > r_quote0     # AMM sold base, gained quote
    assert s.ledger.total_supply(s.cur) == cur0
    assert s.ledger.total_supply(pair.base) == eq0


def test_amm_invariant_shapes_the_ladder():
    """CONCENTRATED and CONST_PRODUCT quote different curves for the same spread (doc 09 9.7.7, #13)."""
    from finbox.core.enums import AMMInvariant
    c = SkeletonConfig(amm_enabled=True)
    s = genesis(c)
    e = SkeletonEngine(s, c)
    pair = _eq_pair(s)                                       # equity pool -> CONST_PRODUCT at genesis
    amm = s.amm_pools[pair.pair_id]

    def asks():
        return sorted(o.limit_price for o in e.margin.amm_orders(1)
                      if o.pair_id == pair.pair_id and o.side is Side.SELL)

    asks_cp = asks()
    amm.invariant = AMMInvariant.CONCENTRATED
    asks_conc = asks()
    assert asks_cp != asks_conc                              # the invariant actually changes the curve
    assert asks_cp[-1] > asks_conc[-1]                       # const-product widens out far more


def test_determinism_with_amm_enabled():
    from finbox.state import state_hash

    def run():
        c = SkeletonConfig(amm_enabled=True)
        s = genesis(c)
        e = SkeletonEngine(s, c)
        return [(_step(e, s)) for _ in range(12)]

    def _step(e, s):
        e.run_turn([])
        return state_hash(s)

    assert run() == run()
