"""Engine error hierarchy."""
from __future__ import annotations


class FinBoxError(Exception):
    """Base class for all engine errors."""


class IdFormatError(FinBoxError):
    """An entity_id / asset_id does not match its canonical grammar (doc 00 0.3-0.5)."""


class ValidationError(FinBoxError):
    """A submitted action / posting failed validation (P2, doc 02 2.5)."""


class ConservationError(FinBoxError):
    """A posting would violate a conservation law / mint-burn rule (doc 00 0.17, doc 08 8.7)."""


class NonNegativeError(FinBoxError):
    """A posting would drive a physical balance below zero (doc 00 0.9)."""
