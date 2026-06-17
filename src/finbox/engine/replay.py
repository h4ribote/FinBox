"""Determinism / replay harness (doc 02 2.6.2).

The walking-skeleton acceptance criterion: the same (master_seed, config) yields
byte-identical per-tick state hashes, and replaying the ledger journal rebuilds
the same balances.
"""
from __future__ import annotations

from ..init.config import SkeletonConfig
from ..init.genesis import genesis
from ..ledger import replay as ledger_replay
from ..state import StateStore
from .skeleton import SkeletonEngine, run_skeleton


def run_hashes(config: SkeletonConfig, n_turns: int) -> list[str]:
    _, hashes = run_skeleton(config, n_turns)
    return hashes


def record_run(config: SkeletonConfig, n_turns: int) -> tuple[list, list[str]]:
    """Run the authoritative sim and capture (action_log, per-tick state hashes) (doc 02 2.6.1)."""
    store = genesis(config)
    engine = SkeletonEngine(store, config)
    hashes = [engine._step_hash() for _ in range(n_turns)]
    return list(store.action_log), hashes


def verify_replay(config: SkeletonConfig, action_log: list, recorded_hashes: list[str]) -> bool:
    """Re-simulate from (master_seed, genesis_config, action_log) and check each tick's snapshot
    hash matches the original execution (doc 02 2.6.2)."""
    store = genesis(config)
    engine = SkeletonEngine(store, config)
    for h in recorded_hashes:
        if engine._step_hash() != h:
            return False
    return store.action_log == action_log     # the recorded pre-validation intents are reproduced


def verify_determinism(config: SkeletonConfig, n_turns: int) -> bool:
    """True iff two independent runs produce identical per-tick hash sequences."""
    return run_hashes(config, n_turns) == run_hashes(config, n_turns)


def verify_journal_replay(store: StateStore) -> bool:
    """True iff replaying the ledger journal reconstructs the current balances."""
    return ledger_replay(store.ledger.journal).balances() == store.ledger.balances()
