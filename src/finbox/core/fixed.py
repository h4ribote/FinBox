"""Canonical integer rounding (doc 00 0.20).

The single source of truth for how non-integer intermediate results become the
integers written to the ledger / state. All money/quantity is integer minor
units; floats never reach state. bps rates are applied as ``x * bps // 10000``.
"""
from __future__ import annotations
from collections.abc import Sequence

BPS_DEN = 10_000


def floordiv(a: int, b: int) -> int:
    """Floor division (toward -inf); Python ``//`` already does this for ints."""
    return a // b


def ceildiv(a: int, b: int) -> int:
    """Ceiling division for integer a and positive b (any sign of a)."""
    if b <= 0:
        raise ValueError("ceildiv requires b > 0")
    return -((-a) // b)


def round_half_up_div(n: int, d: int) -> int:
    """Round n/d to the nearest integer, ties going up (toward +inf).

    Equivalent to floor(n/d + 1/2); correct for negative n via floor division.
    """
    if d <= 0:
        raise ValueError("round_half_up_div requires d > 0")
    return (2 * n + d) // (2 * d)


def clamp(x: int, lo: int, hi: int) -> int:
    return lo if x < lo else hi if x > hi else x


def fee(cash: int, fee_rate_bps: int) -> int:
    """Trade fee = ceil(cash * fee_rate_bps / 10000) (doc 00 0.8/0.20). cash,bps >= 0."""
    if cash < 0 or fee_rate_bps < 0:
        raise ValueError("fee requires non-negative cash and bps")
    return ceildiv(cash * fee_rate_bps, BPS_DEN)


def apply_bps_floor(base: int, rate_bps: int) -> int:
    """floor(base * rate_bps / 10000): taxes, tariffs, subsidies, per-share dividend (doc 00 0.20)."""
    return (base * rate_bps) // BPS_DEN


def interest_per_turn(principal: int, r_annual_bps: int, turns_per_year: int) -> int:
    """Per-turn simple interest = floor(principal * r_annual_bps / 10000 / TURNS_PER_YEAR).

    Facility / borrow / penalty interest accrues every turn (doc 03 3.2.1, doc 11 11.7.1).
    """
    return (principal * r_annual_bps) // (BPS_DEN * turns_per_year)


def coupon_quarterly(qty: int, face: int, coupon_bps: int) -> int:
    """Quarterly bond coupon = floor(qty * face * coupon_bps / 10000 / 4) (doc 00 0.20, doc 11 11.4.3)."""
    return (qty * face * coupon_bps) // (BPS_DEN * 4)


def round_to_tick(value: int, tick: int) -> int:
    """Round value to the nearest multiple of tick, ties up (SCALAR aggregation, doc 00 0.20).

    Callers clamp to the policy range *before* calling this (clamp -> round_to_tick).
    """
    if tick <= 0:
        raise ValueError("round_to_tick requires tick > 0")
    return round_half_up_div(value, tick) * tick


def largest_remainder(total: int, weights: Sequence[int]) -> list[int]:
    """Integer allocation of ``total`` proportional to ``weights`` (Hamilton method).

    The sum of the result is exactly ``total``. Leftover units go to the largest
    fractional remainders; remainder ties break by ascending index (doc 00 0.20).
    """
    if total < 0:
        raise ValueError("largest_remainder requires total >= 0")
    n = len(weights)
    if n == 0:
        return []
    if any(w < 0 for w in weights):
        raise ValueError("weights must be non-negative")
    s = sum(weights)
    if s == 0:
        return [0] * n
    quotas = [total * w for w in weights]  # numerators over s
    base = [q // s for q in quotas]
    leftover = total - sum(base)
    # rank indices by remainder desc, then index asc
    order = sorted(range(n), key=lambda i: (-(quotas[i] % s), i))
    for k in range(leftover):
        base[order[k]] += 1
    return base
