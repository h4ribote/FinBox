"""Integer double-entry ledger (doc 08, doc 15 15.6).

balance[entity_id][asset_id] = non-negative integer (minor units). Every change
is a Posting of LedgerLines whose per-asset net delta is zero (conservation)
except at the defined mint/burn points (doc 00 0.10/0.17). Postings are atomic:
if any resulting balance would go negative, the whole posting is rejected.
"""
from .types import LedgerLine, Posting
from .conservation import ConservationGuard
from .ledger import Ledger
from .journal import replay

__all__ = ["LedgerLine", "Posting", "ConservationGuard", "Ledger", "replay"]
