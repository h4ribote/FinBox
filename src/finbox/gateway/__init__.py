"""FastAPI client gateway: the sole client boundary (doc 02, doc 14).

Clients (players and agent runtimes) only read observations and submit actions;
the engine is the single writer. The submission buffer collects intents per
(entity, tick) with idempotent latest-wins and hands a frozen, deterministic
batch to the engine.
"""
from .buffer import SubmissionBuffer
from .server import Gateway, create_app

__all__ = ["SubmissionBuffer", "Gateway", "create_app"]
