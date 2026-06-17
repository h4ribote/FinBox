"""Financial instrument records (doc 11, canonical schema doc 15 15.8)."""
from __future__ import annotations
from dataclasses import dataclass

from ..core.ids import AssetId, EntityId


@dataclass(frozen=True, slots=True)
class Bond:
    """A coupon bond / discount bill (doc 11 11.4, doc 15 15.8).

    Coupons are paid quarterly (floored). ``BILL:*`` is the discount form with
    ``coupon_bps == 0``; BOND vs BILL is identified by the ``asset_id`` prefix.
    """
    asset_id: AssetId
    issuer: EntityId
    currency: AssetId        # denomination currency (asset_class == CUR), doc 15.8
    face: int                # redemption amount per unit
    coupon_bps: int          # annual coupon, in bps; BILL == 0
    issue_tick: int
    maturity_tick: int
    outstanding: int         # issued quantity (== sum of holdings while live), doc 15.8


@dataclass(frozen=True, slots=True)
class Equity:
    """A firm's equity (doc 11 11.6, doc 15 15.8). Dividends are paid quarterly from firm profit."""
    asset_id: AssetId
    firm_id: EntityId
    par: int                     # clearing / dividend reference
    dividend_policy_bps: int     # profit payout ratio in bps (doc 11 11.6.2 payout_ratio)
    shares_outstanding: int      # issued shares (== sum of holdings), doc 15.8
    listed: bool = True          # tradable on the equity market
