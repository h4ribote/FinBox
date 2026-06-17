"""Submission buffer (doc 02 2.4, doc 14 14.7).

Collects order intents per (entity, tick). Re-submission by the same entity in
the same tick overwrites (idempotent latest-wins). At the deadline, freeze()
returns a deterministic batch ordered by entity_id.
"""
from __future__ import annotations
from collections import defaultdict

from ..agents.scripted import ProtoOrder
from ..core.ids import EntityId


class SubmissionBuffer:
    def __init__(self) -> None:
        self._by_tick: dict[int, dict[EntityId, list[ProtoOrder]]] = defaultdict(dict)

    def submit(self, tick: int, entity: EntityId, protos: list[ProtoOrder]) -> None:
        """Register (or overwrite) an entity's intent for a tick (latest-wins)."""
        self._by_tick[tick][entity] = list(protos)

    def freeze(self, tick: int) -> list[ProtoOrder]:
        """Return the deterministic frozen batch for a tick and clear it."""
        submitted = self._by_tick.pop(tick, {})
        out: list[ProtoOrder] = []
        for entity in sorted(submitted, key=str):
            out.extend(submitted[entity])
        return out

    def pending(self, tick: int) -> int:
        return sum(len(v) for v in self._by_tick.get(tick, {}).values())
