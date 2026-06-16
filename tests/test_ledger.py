"""Integer double-entry ledger tests (doc 08, doc 15 15.6)."""
import pytest

from finbox.core.enums import Cause, TurnPhase
from finbox.core.errors import ConservationError, NonNegativeError, ValidationError
from finbox.core.ids import AssetId, EntityId
from finbox.ledger import Ledger, LedgerLine, replay

CUR = AssetId.cur("ALD")
GRAIN = AssetId.comm("agri", "grain")
FLOUR = AssetId.comm("mat", "flour")
E = EntityId.agent(1)
GOV = EntityId.gov("ALD")
CB = EntityId.cb("ALD")
FIRM = EntityId.firm(1)


def L(entity, asset, delta):
    return LedgerLine(entity, asset, delta)


def fresh_with_cash(amount=1000):
    led = Ledger()
    led.post(0, TurnPhase.INIT, Cause.GENESIS, [L(E, CUR, amount)])
    return led


def test_genesis_mint_and_total_supply():
    led = fresh_with_cash(1000)
    assert led.get(E, CUR) == 1000
    assert led.total_supply(CUR) == 1000


def test_conserving_transfer_preserves_total():
    led = fresh_with_cash(1000)
    led.post(7, TurnPhase.P7, Cause.TAX, [L(E, CUR, -150), L(GOV, CUR, +150)])
    assert led.get(E, CUR) == 850
    assert led.get(GOV, CUR) == 150
    assert led.total_supply(CUR) == 1000  # conserved


def test_non_negative_atomic_reject():
    led = fresh_with_cash(100)
    # one line ok, one line drives E negative -> whole posting rejected, no partial apply
    with pytest.raises(NonNegativeError):
        led.post(7, TurnPhase.P7, Cause.TAX, [L(GOV, CUR, +150), L(E, CUR, -150)])
    assert led.get(E, CUR) == 100
    assert led.get(GOV, CUR) == 0


def test_conservation_requires_offset_for_conserving_cause():
    led = fresh_with_cash(1000)
    with pytest.raises(ConservationError):
        led.post(7, TurnPhase.P7, Cause.TAX, [L(E, CUR, -150)])  # net != 0 under TAX


def test_currency_supply_only_via_cb_or_genesis():
    led = Ledger()
    with pytest.raises(ConservationError):
        led.post(5, TurnPhase.P5, Cause.PRODUCTION, [L(E, CUR, +100)])  # CUR mint via PRODUCTION
    # CB mint is allowed
    led.post(7, TurnPhase.P7, Cause.MINT, [L(CB, CUR, +100)])
    assert led.get(CB, CUR) == 100
    led.post(7, TurnPhase.P7, Cause.BURN, [L(CB, CUR, -40)])
    assert led.get(CB, CUR) == 60


def test_production_mint_burn():
    led = Ledger()
    led.post(0, TurnPhase.INIT, Cause.GENESIS, [L(FIRM, GRAIN, 16)])
    # produce flour: burn 8 grain, mint 10 flour (PRODUCTION net != 0 allowed)
    led.post(5, TurnPhase.P5, Cause.PRODUCTION, [L(FIRM, GRAIN, -8), L(FIRM, FLOUR, +10)])
    assert led.get(FIRM, GRAIN) == 8
    assert led.get(FIRM, FLOUR) == 10
    assert led.total_supply(GRAIN) == 8
    assert led.total_supply(FLOUR) == 10


def test_zero_delta_line_rejected():
    with pytest.raises(ValidationError):
        LedgerLine(E, CUR, 0)


def test_journal_replay_reconstructs_balances():
    led = fresh_with_cash(1000)
    led.post(7, TurnPhase.P7, Cause.TAX, [L(E, CUR, -150), L(GOV, CUR, +150)])
    led.post(0, TurnPhase.INIT, Cause.GENESIS, [L(FIRM, GRAIN, 16)])
    led.post(5, TurnPhase.P5, Cause.PRODUCTION, [L(FIRM, GRAIN, -8), L(FIRM, FLOUR, +10)])
    rebuilt = replay(led.journal)
    assert rebuilt.balances() == led.balances()
    assert rebuilt.next_posting_id == led.next_posting_id


def test_balances_snapshot_is_sparse_and_nonzero():
    led = fresh_with_cash(1000)
    led.post(7, TurnPhase.P7, Cause.TAX, [L(E, CUR, -1000), L(GOV, CUR, +1000)])
    # E now zero -> should not appear in sparse balances
    bal = led.balances()
    assert E not in bal
    assert bal[GOV][CUR] == 1000
