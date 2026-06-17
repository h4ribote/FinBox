"""M5 finance: bonds (coupon/redeem), dividends, NAV (doc 11)."""
from finbox.engine import SkeletonEngine
from finbox.init import SkeletonConfig, genesis


def _run(n: int):
    c = SkeletonConfig()
    s = genesis(c)
    e = SkeletonEngine(s, c)
    for _ in range(n):
        e.run_turn()
    return c, s


def test_investor_receives_coupons_and_dividends():
    c, s = _run(12)  # first quarter end is tick 11
    inv = s.investors[0]
    # investor only receives protocol transfers (no spending), so cash strictly grew
    assert s.cash(inv) > c.investor_start_cash


def test_bond_supply_constant_until_maturity_then_burned():
    c = SkeletonConfig()
    s = genesis(c)
    e = SkeletonEngine(s, c)
    bond = s.bonds[0]
    for _ in range(c.bond_maturity_tick):           # ticks 0..maturity-1
        e.run_turn()
        assert s.ledger.total_supply(bond.asset_id) == c.bond_qty
    e.run_turn()                                     # processes maturity tick -> redeem+burn
    assert s.ledger.total_supply(bond.asset_id) == 0


def test_redemption_pays_face_value():
    c = SkeletonConfig()
    s = genesis(c)
    e = SkeletonEngine(s, c)
    inv = s.investors[0]
    before = None
    for _ in range(c.bond_maturity_tick):
        e.run_turn()
    before = s.cash(inv)
    e.run_turn()  # maturity tick: redemption (+ final coupon/dividend, also a quarter end)
    assert s.cash(inv) >= before + c.bond_qty * c.bond_face   # at least the face value
    assert s.ledger.total_supply(s.bonds[0].asset_id) == 0       # bond burned on redemption


def test_currency_conserved_with_finance():
    c = SkeletonConfig()
    s = genesis(c)
    e = SkeletonEngine(s, c)
    total = s.ledger.total_supply(s.cur)
    for _ in range(60):
        e.run_turn()
        assert s.ledger.total_supply(s.cur) == total  # coupons/dividends/redeem all conserve CUR


def test_nav_is_tracked():
    c, s = _run(24)
    assert s.macro["investor_nav"] > 0


def test_liquidation_distributes_residual_then_burns_equity():
    from finbox.core.enums import FirmLifecycle
    c = SkeletonConfig()
    s = genesis(c)
    e = SkeletonEngine(s, c)
    fid = sorted(s.firms)[0]
    eq = next(x for x in s.equities if x.firm_id == fid)
    inv = s.investors[0]                       # sole shareholder (genesis)
    cur_total = s.ledger.total_supply(s.cur)
    inv_cash0 = s.cash(inv)
    firm_cash = s.cash(fid)
    e._liquidate(fid)
    assert s.firms[fid].state is FirmLifecycle.LIQUIDATING
    assert s.ledger.total_supply(eq.asset_id) == 0        # equity burned (doc 10.8.5 / 00 0.5.1)
    assert s.ledger.total_supply(s.cur) == cur_total      # currency conserved
    assert s.cash(inv) == inv_cash0 + firm_cash           # residual distributed to shareholder
    assert s.cash(fid) == 0


def test_insolvent_firm_is_liquidated():
    from finbox.core.enums import Cause, FirmLifecycle, TurnPhase
    from finbox.ledger import LedgerLine
    c = SkeletonConfig()
    s = genesis(c)
    e = SkeletonEngine(s, c)
    fid = sorted(s.firms)[1]
    eq = next(x for x in s.equities if x.firm_id == fid)
    cur_total = s.ledger.total_supply(s.cur)
    cash = s.cash(fid)                          # force insolvency: drain cash, zero capacity
    s.ledger.post(s.tick, TurnPhase.P7, Cause.FISCAL,
                  [LedgerLine(fid, s.cur, -cash), LedgerLine(s.gov, s.cur, cash)])
    s.firms[fid].capacity = 0
    e._liquidate_insolvent()
    assert s.firms[fid].state is FirmLifecycle.LIQUIDATING
    assert s.ledger.total_supply(eq.asset_id) == 0
    assert s.ledger.total_supply(s.cur) == cur_total
