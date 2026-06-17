"""Political decision aggregation and fiscal policy (doc 12, doc 00 0.12)."""
from .aggregate import (
    aggregate_allocation,
    aggregate_binary,
    aggregate_categorical,
    aggregate_scalar,
)

__all__ = [
    "aggregate_scalar", "aggregate_binary", "aggregate_categorical", "aggregate_allocation",
]
