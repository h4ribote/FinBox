"""Financial instrument records (doc 11)."""
from __future__ import annotations
from dataclasses import dataclass

from ..core.ids import AssetId, EntityId


@dataclass(frozen=True, slots=True)
class Bond:
    """A coupon bond / bill (doc 11 11.4). Coupons are paid quarterly, floored."""
    asset: AssetId
    issuer: EntityId
    face: int
    coupon_bps: int          # annual, in bps
    maturity_tick: int


@dataclass(frozen=True, slots=True)
class Equity:
    """A firm's equity (doc 11 11.6). Dividends paid quarterly from firm cash."""
    asset: AssetId
    firm: EntityId
    par: int
    dividend_bps: int        # annual, in bps
