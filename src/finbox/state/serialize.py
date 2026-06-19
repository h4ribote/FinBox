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

    # agent need states (doc 05 5.2), all engine-authoritative and part of the snapshot
    for name, d in (("sat", store.satiety), ("hp", store.health), ("stm", store.stamina),
                    ("rst", store.rest), ("str", store.stress), ("hap", store.happiness),
                    ("age", store.age), ("strk", store.starve_streak)):
        for entity in sorted(d):
            parts.append(f"{name}|{entity}|{d[entity]}")
    for entity in sorted(store.skill):
        for k in sorted(store.skill[entity]):
            parts.append(f"skill|{entity}|{k}|{store.skill[entity][k]}")
    for entity in sorted(store.deceased, key=str):
        parts.append(f"dead|{entity}")

    # authoritative per-entity roles (doc 00 0.14, doc 06 6.1): part of the snapshot
    for entity in sorted(store.roles, key=str):
        rs = ",".join(sorted(r.value for r in store.roles[entity]))
        parts.append(f"role|{entity}|{rs}")

    for firm in sorted(store.firms):
        parts.append(f"cap|{firm}|{store.firms[firm].capacity}|{store.firms[firm].state.value}")

    for key in sorted(store.macro):
        parts.append(f"macro|{key}|{store.macro[key]}")

    for key in sorted(store.policy):
        parts.append(f"policy|{key}|{store.policy[key]}")

    # margin trading state (doc 09 信用取引, doc 15 15.6): positions, lending pools, AMM pools.
    # Underlying assets are in the ledger balances above; here we hash the bookkeeping records.
    parts.append(f"posseq|{store.position_seq}")
    parts.append(f"liqseq|{store.liq_seq}")
    for p in sorted(store.positions, key=lambda r: r.position_id):
        parts.append(f"pos|{p.position_id}|{p.entity}|{p.pair_id}|{p.side.value}|{p.qty}|"
                     f"{p.entry_price}|{p.borrowed_asset}|{p.borrowed_qty}|{p.collateral_asset}|"
                     f"{p.collateral_qty}|{p.accrued_interest}|{p.open_tick}")
    for asset in sorted(store.lending_pools):
        pool = store.lending_pools[asset]
        parts.append(f"lpool|{asset}|{pool.supplied}|{pool.borrowed}|{pool.total_shares}")
        for e in sorted(pool.shares, key=str):
            if pool.shares[e]:
                parts.append(f"lshare|{asset}|{e}|{pool.shares[e]}")
    for pid in sorted(store.amm_pools):
        a = store.amm_pools[pid]
        parts.append(f"amm|{pid}|{a.r_base}|{a.r_quote}|{a.total_shares}|{a.spread_bps}|{a.invariant.value}")
        for e in sorted(a.shares, key=str):
            if a.shares[e]:
                parts.append(f"ammshare|{pid}|{e}|{a.shares[e]}")

    # resting GTC/GTT order book (doc 02 2.6.1 full snapshot, doc 09 9.4.2)
    for o in sorted(store.resting_orders, key=lambda r: r.order_id):
        parts.append(f"rest|{o.order_id}|{o.pair_id}|{o.side.value}|{o.order_type.value}|"
                     f"{o.limit_price}|{o.qty}|{o.submit_seq}|{o.tif.value}|{o.expires_tick}")

    # world: digest of mutable cell state (population/owner/forest) + agent residency (doc 04)
    if store.cells:
        cell_parts = [
            f"{cid}|{store.cells[cid].base_population}|{store.cells[cid].owner}|{store.cells[cid].forest_stock}"
            for cid in sorted(store.cells)
        ]
        parts.append("world|" + hashlib.sha256("\n".join(cell_parts).encode("utf-8")).hexdigest())
        for a in sorted(store.home_cell, key=str):
            parts.append(f"home|{a}|{store.home_cell[a]}")

    # display names (doc 16 16.14.3): part of the snapshot hash, never affects logic
    for key in sorted(store.names):
        parts.append(f"name|{key}|{store.names[key]}")

    return "\n".join(parts).encode("utf-8")


def state_hash(store: StateStore) -> str:
    """SHA-256 hex digest of the canonical serialization."""
    return hashlib.sha256(canonical_bytes(store)).hexdigest()
