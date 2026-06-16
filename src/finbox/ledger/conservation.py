"""Conservation guard: the single place that enforces mint/burn rules (doc 00 0.17, doc 08 8.7).

A posting whose per-asset net delta is non-zero changes that asset's total
supply; it is only permitted under a mint/burn cause. Currency is special:
its supply may change only via central-bank mint/burn or genesis.
"""
from __future__ import annotations

from ..core.enums import AssetClass, Cause, MINT_BURN_CAUSES
from ..core.errors import ConservationError
from ..core.ids import AssetId
from .types import Posting

_CUR_SUPPLY_CAUSES = frozenset({Cause.MINT, Cause.BURN, Cause.GENESIS})


class ConservationGuard:
    @staticmethod
    def net_by_asset(posting: Posting) -> dict[AssetId, int]:
        net: dict[AssetId, int] = {}
        for ln in posting.lines:
            net[ln.asset_id] = net.get(ln.asset_id, 0) + ln.delta
        return net

    def check(self, posting: Posting) -> None:
        for asset, net in self.net_by_asset(posting).items():
            if net == 0:
                continue  # conserving transfer: always allowed
            if posting.cause not in MINT_BURN_CAUSES:
                raise ConservationError(
                    f"non-zero net delta ({net}) for {asset} under conserving cause {posting.cause.value}")
            if asset.asset_class is AssetClass.CUR and posting.cause not in _CUR_SUPPLY_CAUSES:
                raise ConservationError(
                    f"CUR supply may change only via CB mint/burn or genesis, not {posting.cause.value}")
