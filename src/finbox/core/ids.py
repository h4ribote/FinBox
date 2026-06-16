"""Canonical identifier grammar (doc 00 0.3-0.5).

EntityId and AssetId are ``str`` subclasses, so the canonical scan order
(doc 03 3.7) and canonical serialization order are just lexicographic string
comparison. Construction validates the grammar; malformed ids raise IdFormatError.
"""
from __future__ import annotations
import re

from .enums import AssetClass, CommNamespace, CountryCode, EntityKind
from .errors import IdFormatError

_CC = "(?P<cc>[A-Z]{3})"
_SIX = r"(?P<n>\d{6})"
_MATURITY = r"\d{4}Q[1-4]"
_NS = "|".join(ns.value for ns in CommNamespace)

_ENTITY_PATTERNS: dict[EntityKind, re.Pattern[str]] = {
    EntityKind.AGENT: re.compile(rf"^AGENT:{_SIX}$"),
    EntityKind.FIRM: re.compile(rf"^FIRM:{_SIX}$"),
    EntityKind.PLAYER: re.compile(rf"^PLAYER:{_SIX}$"),
    EntityKind.GOVERNMENT: re.compile(rf"^GOV:{_CC}$"),
    EntityKind.CENTRAL_BANK: re.compile(rf"^CB:{_CC}$"),
    EntityKind.EXCHANGE: re.compile(r"^EXCH$"),
}

_ASSET_PATTERNS: dict[AssetClass, re.Pattern[str]] = {
    AssetClass.CUR: re.compile(rf"^CUR:{_CC}$"),
    AssetClass.COMM: re.compile(rf"^COMM:(?P<ns>{_NS})\.(?P<name>[a-z0-9_#]+)$"),
    AssetClass.BOND: re.compile(
        rf"^BOND:(?:gov\.{_CC}|corp\.{_SIX})\.{_MATURITY}$"),
    AssetClass.BILL: re.compile(rf"^BILL:gov\.{_CC}\.{_MATURITY}$"),
    AssetClass.EQ: re.compile(rf"^EQ:firm\.{_SIX}$"),
    AssetClass.FUT: re.compile(rf"^FUT:.+\.{_MATURITY}$"),
}


def _valid_cc(cc: str) -> bool:
    return cc in CountryCode.__members__


class EntityId(str):
    """A balance-holding entity id (doc 00 0.4)."""

    __slots__ = ()

    def __new__(cls, value: str) -> "EntityId":
        kind = cls._classify(value)
        if kind is None:
            raise IdFormatError(f"invalid entity_id: {value!r}")
        return super().__new__(cls, value)

    @staticmethod
    def _classify(value: str) -> EntityKind | None:
        for kind, pat in _ENTITY_PATTERNS.items():
            m = pat.match(value)
            if not m:
                continue
            if "cc" in m.groupdict() and not _valid_cc(m.group("cc")):
                return None
            return kind
        return None

    @property
    def kind(self) -> EntityKind:
        k = self._classify(self)
        assert k is not None
        return k

    @property
    def country(self) -> CountryCode | None:
        """Country for GOV/CB ids, else None."""
        if self.kind in (EntityKind.GOVERNMENT, EntityKind.CENTRAL_BANK):
            return CountryCode(self.split(":", 1)[1])
        return None

    # constructors
    @classmethod
    def agent(cls, n: int) -> "EntityId":
        return cls(f"AGENT:{n:06d}")

    @classmethod
    def firm(cls, n: int) -> "EntityId":
        return cls(f"FIRM:{n:06d}")

    @classmethod
    def player(cls, n: int) -> "EntityId":
        return cls(f"PLAYER:{n:06d}")

    @classmethod
    def gov(cls, cc: CountryCode | str) -> "EntityId":
        return cls(f"GOV:{CountryCode(cc).value}")

    @classmethod
    def cb(cls, cc: CountryCode | str) -> "EntityId":
        return cls(f"CB:{CountryCode(cc).value}")

    @classmethod
    def exch(cls) -> "EntityId":
        return cls("EXCH")


class AssetId(str):
    """A Tradable Asset id (doc 00 0.5)."""

    __slots__ = ()

    def __new__(cls, value: str) -> "AssetId":
        if cls._classify(value) is None:
            raise IdFormatError(f"invalid asset_id: {value!r}")
        return super().__new__(cls, value)

    @staticmethod
    def _classify(value: str) -> AssetClass | None:
        for cls_, pat in _ASSET_PATTERNS.items():
            m = pat.match(value)
            if not m:
                continue
            gd = m.groupdict()
            if "cc" in gd and gd["cc"] is not None and not _valid_cc(gd["cc"]):
                return None
            return cls_
        return None

    @property
    def asset_class(self) -> AssetClass:
        c = self._classify(self)
        assert c is not None
        return c

    @property
    def namespace(self) -> CommNamespace | None:
        """COMM namespace, else None."""
        if self.asset_class is AssetClass.COMM:
            path = self.split(":", 1)[1]
            return CommNamespace(path.split(".", 1)[0])
        return None

    # constructors
    @classmethod
    def cur(cls, cc: CountryCode | str) -> "AssetId":
        return cls(f"CUR:{CountryCode(cc).value}")

    @classmethod
    def comm(cls, ns: CommNamespace | str, name: str) -> "AssetId":
        return cls(f"COMM:{CommNamespace(ns).value}.{name}")

    @classmethod
    def eq_firm(cls, n: int) -> "AssetId":
        return cls(f"EQ:firm.{n:06d}")

    @classmethod
    def bond_gov(cls, cc: CountryCode | str, year: int, quarter: int) -> "AssetId":
        return cls(f"BOND:gov.{CountryCode(cc).value}.{year:04d}Q{quarter}")

    @classmethod
    def bill_gov(cls, cc: CountryCode | str, year: int, quarter: int) -> "AssetId":
        return cls(f"BILL:gov.{CountryCode(cc).value}.{year:04d}Q{quarter}")

    @classmethod
    def bond_corp(cls, firm_n: int, year: int, quarter: int) -> "AssetId":
        return cls(f"BOND:corp.{firm_n:06d}.{year:04d}Q{quarter}")
