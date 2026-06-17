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
        assert s.ledger.total_supply(bond.asset) == c.bond_qty
    e.run_turn()                                     # processes maturity tick -> redeem+burn
    assert s.ledger.total_supply(bond.asset) == 0


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
    assert s.ledger.total_supply(s.bonds[0].asset) == 0       # bond burned on redemption


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
