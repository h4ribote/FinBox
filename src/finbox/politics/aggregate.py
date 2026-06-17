"""Political decision aggregation rules (doc 00 0.12, doc 12 12.2).

Deterministic, integer, order-independent aggregation of per-politician
proposals into a confirmed policy value. Each politician carries a weight
(default 1). Used in P3 GOVERN.
"""
from __future__ import annotations
from collections.abc import Mapping, Sequence

from ..core.fixed import clamp, largest_remainder, round_half_up_div, round_to_tick


def aggregate_scalar(values: Sequence[int], weights: Sequence[int],
                     lo: int, hi: int, tick: int) -> int:
    """Weighted mean, then clamp to [lo, hi], then round to tick (half-up) (doc 12 12.2.1)."""
    den = sum(weights)
    if den == 0:
        return round_to_tick(clamp((lo + hi) // 2, lo, hi), tick)
    num = sum(w * v for w, v in zip(weights, values))
    mean = round_half_up_div(num, den)
    return round_to_tick(clamp(mean, lo, hi), tick)


def aggregate_binary(values: Sequence[int], weights: Sequence[int], scale: int = 10000) -> bool:
    """Yes iff the weighted mean confidence is >= 0.5 (doc 12 12.2.2).

    Confidence values are in [0, scale]; the 0.5 boundary counts as Yes.
    """
    den = sum(weights)
    if den == 0:
        return False
    num = sum(w * v for w, v in zip(weights, values))
    return 2 * num >= scale * den


def aggregate_categorical(scores: Sequence[Mapping[str, int]], weights: Sequence[int],
                          options: Sequence[str]) -> str:
    """Option with the greatest weighted total score; ties -> earliest option (doc 12 12.2.3)."""
    best: str | None = None
    best_total: int | None = None
    for opt in options:
        total = sum(w * sc.get(opt, 0) for w, sc in zip(weights, scores))
        if best_total is None or total > best_total:
            best_total, best = total, opt
    assert best is not None
    return best


def aggregate_allocation(vectors: Sequence[Sequence[int]], weights: Sequence[int],
                         total: int) -> list[int]:
    """L1-normalize each proposal, take the weighted mean, integerize to ``total``.

    Returns an integer vector summing exactly to ``total`` (largest-remainder,
    ties by dimension index) (doc 12 12.2.4).
    """
    k = len(vectors[0])
    den = sum(weights)
    if den == 0:
        return largest_remainder(total, [1] * k)
    acc = [0] * k
    for w, vec in zip(weights, vectors):
        s = sum(vec)
        norm = largest_remainder(10000, list(vec)) if s > 0 else largest_remainder(10000, [1] * k)
        for i in range(k):
            acc[i] += w * norm[i]
    mean_bps = [a // den for a in acc]
    return largest_remainder(total, mean_bps)
