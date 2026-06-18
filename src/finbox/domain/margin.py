"""Margin trading records: positions, lending pools, AMM pools (doc 09 信用取引, doc 15 15.6).

All values are integer minor units (doc 00 0.8). These records hold the engine-authoritative
margin/lending state; the underlying assets live on the ledger under facility entity ids
(``POOL:<asset>`` / ``INSF:<cc>`` / ``AMM:<pair>``). Positions and pool shares net out in
net-worth valuation so the conservation law is never broken (doc 08 8.8, doc 00 0.17).
"""
from __future__ import annotations
from dataclasses import dataclass, field

from ..core.enums import AMMInvariant, PositionSide
from ..core.fixed import BPS_DEN, borrow_rate_bps, supply_rate_bps
from ..core.ids import AssetId, EntityId


@dataclass(slots=True)
class Position:
    """One margin (信用) position (doc 15 15.6, doc 09 §証拠金とポジション会計).

    LONG  (e.g. EQ/CUR buy): borrow ``quote`` (CUR) from the pool, combine with own margin to
          buy ``qty`` of ``base``; the held base is collateral, the borrowed quote is the liability.
    SHORT (e.g. EQ/CUR sell): borrow ``qty`` of ``base`` and sell it; the sale proceeds plus posted
          margin (quote) are collateral, the borrowed base is the liability.
    """
    position_id: str
    entity: EntityId
    pair_id: str
    side: PositionSide
    qty: int                  # base units in the position (notional basis)
    entry_price: int          # clearing price at open (quote per base unit)
    borrowed_asset: AssetId
    borrowed_qty: int
    collateral_asset: AssetId
    collateral_qty: int
    accrued_interest: int = 0     # unpaid interest, in quote (CUR) units
    open_tick: int = 0

    def notional(self, base_mark: int) -> int:
        """Position size in quote units at mark ``base_mark`` (doc 09 §証拠金)."""
        return self.qty * base_mark

    def borrowed_value(self, base_mark: int) -> int:
        """Liability in quote units: borrowed quote (LONG) or borrowed base × mark (SHORT)."""
        return self.borrowed_qty if self.side is PositionSide.LONG else self.borrowed_qty * base_mark

    def equity(self, base_mark: int) -> int:
        """Mark-to-market equity in quote units = collateral_value − borrowed_value − interest."""
        if self.side is PositionSide.LONG:
            collateral_value = self.collateral_qty * base_mark         # held base
        else:
            collateral_value = self.collateral_qty                     # quote cash
        return collateral_value - self.borrowed_value(base_mark) - self.accrued_interest

    def margin_ratio_bps(self, base_mark: int) -> int:
        """equity / notional in bps (doc 09 §証拠金). Below maintenance triggers forced liq."""
        notional = self.notional(base_mark)
        if notional <= 0:
            return 0
        return self.equity(base_mark) * BPS_DEN // notional


@dataclass(slots=True)
class LendingPool:
    """A per-asset lending pool (doc 09 §貸借プール, doc 15 LendingPool).

    The pool's spendable inventory (= ``supplied − borrowed`` plus retained interest) lives on
    the ledger under ``POOL:<asset>``. ``supplied`` is share-backed principal; ``borrowed`` is the
    principal currently lent. Suppliers hold ``shares``; their claim appreciates as retained
    interest accumulates in the pool.
    """
    asset: AssetId
    supplied: int = 0
    borrowed: int = 0
    total_shares: int = 0
    shares: dict = field(default_factory=dict)   # EntityId -> share units

    @property
    def entity_id(self) -> EntityId:
        return EntityId.lending_pool(self.asset)

    def utilization_bps(self) -> int:
        """U = borrowed / supplied in bps (doc 09 §利用率連動金利)."""
        if self.supplied <= 0:
            return 0
        return min(BPS_DEN, self.borrowed * BPS_DEN // self.supplied)

    def borrow_rate(self, base_rate_bps: int, slope1: int, slope2: int, u_kink: int) -> int:
        return borrow_rate_bps(self.utilization_bps(), base_rate_bps, slope1, slope2, u_kink)

    def supply_rate(self, base_rate_bps: int, slope1: int, slope2: int,
                    u_kink: int, reserve_factor: int) -> int:
        return supply_rate_bps(self.borrow_rate(base_rate_bps, slope1, slope2, u_kink),
                               self.utilization_bps(), reserve_factor)


@dataclass(slots=True)
class AMMPool:
    """A passive automated-market-maker pool for one pair (doc 09 9.7, doc 15 AMMPool).

    Holds reserves ``(r_base, r_quote)`` on the ledger under ``AMM:<pair>`` and quotes a ladder of
    LIMIT orders around the reserve-ratio mid with an embedded ``spread_bps`` (the "気配幅", not a
    fee). LPs hold ``shares`` proportional to the reserves they posted.
    """
    pair_id: str
    base: AssetId
    quote: AssetId
    invariant: AMMInvariant
    spread_bps: int
    r_base: int = 0
    r_quote: int = 0
    total_shares: int = 0
    shares: dict = field(default_factory=dict)   # EntityId -> LP share units

    @property
    def entity_id(self) -> EntityId:
        return EntityId.amm_pool(self.pair_id)

    def mid(self) -> int:
        """Reserve-ratio mid price r_quote / r_base (doc 09 9.7, integer floor)."""
        return self.r_quote // self.r_base if self.r_base > 0 else 0


def maintenance_margin_bps(base_asset: str, fx_bps: int, comm_bps: int, eq_bps: int) -> int:
    """Maintenance margin by asset class (doc 09 §証拠金, defaults FX 1000 / COMM 1200 / EQ 1500)."""
    if base_asset.startswith("CUR:"):
        return fx_bps
    if base_asset.startswith("EQ:"):
        return eq_bps
    return comm_bps      # storable COMM
