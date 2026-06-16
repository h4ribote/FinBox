"""Canonical serialization + state hash (doc 02 2.6.2, doc 15 15.15).

Determinism oracle: the snapshot is serialized in a fixed, integer-only,
ID-lexicographic order so that the same world always hashes identically across
runs and platforms. Sparse balances (qty == 0) are omitted.
"""
from __future__ import annotations
import hashlib

from .store import StateStore


def canonical_bytes(store: StateStore) -> bytes:
    """Deterministic byte representation of the evolving state (integers only)."""
    parts: list[str] = [f"tick={store.tick}", f"seed={store.master_seed}"]

    balances = store.ledger.balances()  # {entity: {asset: qty}}, only non-zero
    for entity in sorted(balances):
        for asset in sorted(balances[entity]):
            parts.append(f"bal|{entity}|{asset}|{balances[entity][asset]}")

    for pair_id in sorted(store.last_price):
        parts.append(f"px|{pair_id}|{store.last_price[pair_id]}")

    for entity in sorted(store.satiety):
        parts.append(f"sat|{entity}|{store.satiety[entity]}")

    for key in sorted(store.macro):
        parts.append(f"macro|{key}|{store.macro[key]}")

    return "\n".join(parts).encode("utf-8")


def state_hash(store: StateStore) -> str:
    """SHA-256 hex digest of the canonical serialization."""
    return hashlib.sha256(canonical_bytes(store)).hexdigest()
