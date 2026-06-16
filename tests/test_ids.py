"""ID grammar tests (doc 00 0.3-0.5)."""
import pytest

from finbox.core.enums import AssetClass, CommNamespace, CountryCode, EntityKind
from finbox.core.errors import IdFormatError
from finbox.core.ids import AssetId, EntityId


def test_entity_constructors_and_kind():
    assert EntityId.agent(123) == "AGENT:000123"
    assert EntityId.firm(42) == "FIRM:000042"
    assert EntityId.player(7) == "PLAYER:000007"
    assert EntityId.gov("ALD") == "GOV:ALD"
    assert EntityId.cb(CountryCode.BOR) == "CB:BOR"
    assert EntityId.exch() == "EXCH"
    assert EntityId.agent(1).kind is EntityKind.AGENT
    assert EntityId.exch().kind is EntityKind.EXCHANGE
    assert EntityId.gov("CYR").country is CountryCode.CYR
    assert EntityId.agent(1).country is None


def test_entity_invalid():
    for bad in ["AGENT:123", "AGENT:0000001", "GOV:XYZ", "GOV:ald", "FOO:1", "EXCHANGE", "agent:000001"]:
        with pytest.raises(IdFormatError):
            EntityId(bad)


def test_asset_constructors_and_class():
    assert AssetId.cur("ALD") == "CUR:ALD"
    assert AssetId.comm("agri", "grain") == "COMM:agri.grain"
    assert AssetId.eq_firm(42) == "EQ:firm.000042"
    assert AssetId.bond_gov("ALD", 2031, 1) == "BOND:gov.ALD.2031Q1"
    assert AssetId.bill_gov("BOR", 2030, 4) == "BILL:gov.BOR.2030Q4"
    assert AssetId.bond_corp(42, 2032, 3) == "BOND:corp.000042.2032Q3"
    assert AssetId.cur("ALD").asset_class is AssetClass.CUR
    assert AssetId("BOND:gov.ALD.2031Q1").asset_class is AssetClass.BOND
    assert AssetId.comm("mat", "flour").namespace is CommNamespace.MAT
    assert AssetId("COMM:good.food#drink").namespace is CommNamespace.GOOD


def test_asset_invalid():
    for bad in ["COMM:xyz.foo", "CUR:ald", "CUR:ALDX", "EQ:firm.42", "BOND:gov.ALD.2031Q5", "good.food"]:
        with pytest.raises(IdFormatError):
            AssetId(bad)


def test_lexicographic_order():
    # AGENT < FIRM < GOV < PLAYER by prefix; zero-pad keeps numeric order
    ids = [EntityId.firm(2), EntityId.agent(10), EntityId.agent(1), EntityId.gov("ALD")]
    assert sorted(ids) == [EntityId.agent(1), EntityId.agent(10), EntityId.firm(2), EntityId.gov("ALD")]
