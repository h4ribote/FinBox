"""Journal replay (doc 08 8.4.3): postings 0..N reconstruct current balances.

This is the basis of the determinism / replay harness: a snapshot plus the
posting journal (or the action log that produced it) must rebuild the same state.
"""
from __future__ import annotations
from collections.abc import Iterable

from .ledger import Ledger
from .types import Posting


def replay(postings: Iterable[Posting]) -> Ledger:
    """Return a fresh Ledger with the postings applied in order."""
    return Ledger.from_journal(postings)
