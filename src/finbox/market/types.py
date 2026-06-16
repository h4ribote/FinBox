"""Market value types (doc 09, doc 15 15.7)."""
from __future__ import annotations
from dataclasses import dataclass

from ..core.enums import MarketKind, OrderType, Side, TIF
from ..core.errors import ValidationError
from ..core.ids import AssetId, EntityId


@dataclass(frozen=True, slots=True)
class TradingPair:
    """A market pair base/quote (doc 09 9.2). quote must be a currency."""
    base: AssetId
    quote: AssetId
    kind: MarketKind
    tick_size: int = 1
    lot_size: int = 1

    @property
    def pair_id(self) -> str:
        return f"{self.base}/{self.quote}"


@dataclass(frozen=True, slots=True)
class Order:
    """A validated order entering the auction (doc 09 9.3.1, doc 15 15.7)."""
    order_id: str
    entity_id: EntityId
    pair_id: str
    side: Side
    order_type: OrderType
    limit_price: int | None   # None for MARKET
    qty: int
    submit_seq: int           # deterministic time priority key (doc 09 9.6.3)
    tif: TIF = TIF.GFT

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValidationError("order qty must be > 0")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValidationError("LIMIT order requires limit_price")
        if self.order_type is OrderType.MARKET and self.limit_price is not None:
            raise ValidationError("MARKET order must not carry a limit_price")


@dataclass(frozen=True, slots=True)
class Fill:
    order_id: str
    entity_id: EntityId
    side: Side
    qty: int


@dataclass(frozen=True, slots=True)
class ClearResult:
    """Outcome of one pair's call auction (doc 09 9.3)."""
    pair_id: str
    p_star: int
    q_star: int
    fills: tuple[Fill, ...]
    imbalance: int  # D(p*) - S(p*)
