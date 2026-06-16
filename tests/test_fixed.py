"""Canonical rounding tests (doc 00 0.20)."""
from finbox.core import fixed


def test_fee_ceil():
    # doc 08 8.6.1 example: cash=50, fee_rate 1% (100 bps) -> fee = 1
    assert fixed.fee(50, 100) == 1
    assert fixed.fee(0, 5) == 0
    assert fixed.fee(100, 5) == 1          # ceil(0.05) = 1
    assert fixed.fee(20000, 5) == 10       # ceil(10.0) = 10


def test_apply_bps_floor():
    assert fixed.apply_bps_floor(1000, 1500) == 150   # 15% of 1000
    assert fixed.apply_bps_floor(999, 1500) == 149     # floor(149.85)
    assert fixed.apply_bps_floor(0, 9999) == 0


def test_coupon_quarterly():
    # doc 11 11.4.3 / checks.py: q=100, face=1000, 350 bps -> 875/quarter
    assert fixed.coupon_quarterly(100, 1000, 350) == 875
    assert fixed.coupon_quarterly(1, 1000, 350) == 8     # floor(8.75)
    assert fixed.coupon_quarterly(0, 1000, 350) == 0


def test_interest_per_turn():
    # 4.8%/yr (480 bps) on 100000 over 48 turns -> 100/turn
    assert fixed.interest_per_turn(100000, 480, 48) == 100


def test_round_half_up_div():
    assert fixed.round_half_up_div(5, 2) == 3      # 2.5 -> 3
    assert fixed.round_half_up_div(4, 2) == 2
    assert fixed.round_half_up_div(-5, 2) == -2    # -2.5 -> -2 (toward +inf)
    assert fixed.round_half_up_div(7, 3) == 2      # 2.33 -> 2


def test_round_to_tick():
    assert fixed.round_to_tick(175, 25) == 175
    assert fixed.round_to_tick(187, 25) == 175     # 7.48 -> 7
    assert fixed.round_to_tick(188, 25) == 200     # 7.52 -> 8
    assert fixed.round_to_tick(-100, 25) == -100


def test_largest_remainder_sum_and_tiebreak():
    r = fixed.largest_remainder(100, [1, 1, 1])
    assert sum(r) == 100
    assert r == [34, 33, 33]                        # tie -> index 0 first
    assert fixed.largest_remainder(100, [2, 1, 1]) == [50, 25, 25]  # doc 12 example
    assert fixed.largest_remainder(0, [1, 2]) == [0, 0]
    assert fixed.largest_remainder(10, [0, 0]) == [0, 0]


def test_clamp():
    assert fixed.clamp(5, 0, 100) == 5
    assert fixed.clamp(-1, 0, 100) == 0
    assert fixed.clamp(150, 0, 100) == 100
