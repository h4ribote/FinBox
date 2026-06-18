"""M7+ gateway: two-layer auth, orders/votes, role-gating, error model (doc 02, doc 13, doc 14)."""
from types import SimpleNamespace

import pytest

from finbox.gateway import Gateway
from finbox.gateway.server import Forbidden, NotCancellable, NotFound, Unauthenticated
from finbox.init import SkeletonConfig, genesis


def _order(pair, side, qty, price=None, order_type="LIMIT", client_ref=None):
    return SimpleNamespace(pair=pair, side=side, quantity=qty, price=price,
                           order_type=order_type, client_ref=client_ref)


def _vote(lever, value, kind="SCALAR"):
    return SimpleNamespace(lever=lever, kind=kind, value=value, scores=None, weights=None)


def _food_pair(store) -> str:
    return f"{store.food}/{store.cur}"


def make_gateway(**cfg):
    c = SkeletonConfig(**cfg)
    return Gateway(genesis(c), c)


def _session(gw, roles=("INVESTOR",)):
    ent, key = gw.register_player("Hina", requested_roles=roles)
    return ent, gw.create_session(key)["token"]


def test_register_player_numbered_from_zero_and_endowed():
    gw = make_gateway()
    ent, key = gw.register_player("Hina")
    assert str(ent) == "PLAYER:000000"                 # doc 13 13.3.2 (0-based)
    assert gw.store.cash(ent) == gw.config.investor_start_cash


def test_two_layer_auth_session_required():
    gw = make_gateway()
    with pytest.raises(Unauthenticated):
        gw.portfolio("not-a-jwt")
    with pytest.raises(Unauthenticated):
        gw.submit_orders(None, [])
    # a forged token (right shape, wrong signature) is rejected
    with pytest.raises(Unauthenticated):
        gw.portfolio("aaa.bbb.ccc")


def test_session_issue_refresh_revoke():
    gw = make_gateway()
    _, key = gw.register_player("Hina")
    sess = gw.create_session(key)
    assert sess["token_type"] == "Bearer" and "trade" in sess["scope"]
    token = sess["token"]
    gw.portfolio(token)                                # valid
    gw.revoke_session(token)
    with pytest.raises(Unauthenticated):
        gw.portfolio(token)                            # revoked


def test_player_can_trade_via_buffer_and_step():
    gw = make_gateway()
    ent, token = _session(gw)
    price = gw.store.last_price[_food_pair(gw.store)]
    res = gw.submit_orders(token, [_order(_food_pair(gw.store), "BUY", 1, price, client_ref="a1")])
    assert res["accepted"][0]["status"] == "QUEUED" and res["accepted"][0]["client_ref"] == "a1"
    assert gw.buffer.pending(0) == 1
    gw.step()
    assert gw.store.food_qty(ent) == 1
    assert gw.store.cash(ent) < gw.config.investor_start_cash


def test_cancel_order():
    gw = make_gateway()
    _, token = _session(gw)
    p = _food_pair(gw.store)
    res = gw.submit_orders(token, [_order(p, "BUY", 1, gw.store.last_price[p])])
    oid = res["accepted"][0]["order_id"]
    assert gw.cancel_order(token, oid)["status"] == "CANCELLED"
    assert gw.buffer.pending(0) == 0
    with pytest.raises(NotCancellable):
        gw.cancel_order(token, oid)                    # already cancelled


def test_financial_instrument_gating():
    gw = make_gateway()
    _, token = _session(gw, roles=("INVESTOR",))       # INVESTOR is a capital role -> allowed
    eq = next(iter(p for p in gw.store.pairs if p.startswith("EQ:")))
    res = gw.submit_orders(token, [_order(eq, "BUY", 1, 1000, client_ref="e1")])
    assert res["accepted"] and not res["rejected"]     # capital role may trade equities


def test_insufficient_balance_preflight_rejects():
    gw = make_gateway()
    _, token = _session(gw)
    eq = next(iter(p for p in gw.store.pairs if p.startswith("EQ:")))
    res = gw.submit_orders(token, [_order(eq, "SELL", 5, 1000, client_ref="s1")])
    assert res["rejected"][0]["code"] == "insufficient_balance"   # holds 0 of that equity


def _eq(store):
    return next(iter(p for p in store.pairs if p.startswith("EQ:")))


def test_margin_order_accepted_for_investor():
    gw = make_gateway()
    _, token = _session(gw)                            # INVESTOR is margin-capable, allow_margin default
    eq = _eq(gw.store)
    o = _order(eq, "BUY", 5, gw.store.last_price[eq])
    o.trade_mode, o.position_side, o.intent, o.position_id = "MARGIN", "LONG", "OPEN", None
    res = gw.submit_orders(token, [o])
    assert res["accepted"] and not res["rejected"]


def test_margin_rejected_when_disabled():
    gw = make_gateway(allow_margin=False)
    _, token = _session(gw)
    eq = _eq(gw.store)
    o = _order(eq, "BUY", 5, gw.store.last_price[eq])
    o.trade_mode, o.position_side, o.intent, o.position_id = "MARGIN", "LONG", "OPEN", None
    res = gw.submit_orders(token, [o])
    assert res["rejected"][0]["code"] == "role_not_permitted"


def test_margin_rejected_on_ineligible_pair():
    gw = make_gateway()
    _, token = _session(gw)
    bond = next(iter(p for p in gw.store.pairs if p.startswith("BOND:")))
    o = _order(bond, "BUY", 1, gw.store.last_price[bond])
    o.trade_mode, o.position_side, o.intent, o.position_id = "MARGIN", "LONG", "OPEN", None
    res = gw.submit_orders(token, [o])
    assert res["rejected"][0]["code"] == "validation_failed"   # bonds are spot-only


def test_lending_deposit_queues_and_applies():
    gw = make_gateway()
    ent, token = _session(gw)
    cur = str(gw.store.cur)
    pool = gw.store.lending_pools[cur]
    supplied0 = pool.supplied
    gw.lending_op(token, "SUPPLY", cur, 100000)
    assert gw.store.pending_pool_ops and gw.store.cash(ent) == gw.config.investor_start_cash
    gw.step()                                          # P4-pre applies the deposit
    assert pool.supplied == supplied0 + 100000
    assert pool.shares.get(ent, 0) > 0
    assert not gw.store.pending_pool_ops


def test_portfolio_exposes_positions_and_lending_state():
    gw = make_gateway()
    _, token = _session(gw)
    pf = gw.portfolio(token)
    assert "positions" in pf and pf["positions"] == []   # no margin positions yet
    st = gw.public_state()
    assert "lending_pools" in st and "insurance" in st and "amm_pools" in st
    assert any(p["asset_id"] == str(gw.store.cur) for p in st["lending_pools"])


def test_role_gating_blocks_player_from_voting():
    gw = make_gateway()
    _, token = _session(gw)                            # INVESTOR: no govern scope
    with pytest.raises(Forbidden):
        gw.vote(token, "ALD", [_vote("tax_consumption", 1000)])


def test_politician_votes_drive_p3_govern():
    gw = make_gateway(allow_public_roles=True)
    _, token = _session(gw, roles=("POLITICIAN",))
    gw.vote(token, "ALD", [_vote("tax_consumption", 1500)])
    gw.step()
    assert gw.store.policy["tax_bps"] == 1500          # submitted vote confirmed at P3 GOVERN


def test_unknown_pair_and_country():
    gw = make_gateway(allow_public_roles=True)
    _, token = _session(gw, roles=("POLITICIAN",))
    with pytest.raises(NotFound):
        gw.submit_orders(token, [_order("COMM:bogus.thing/CUR:ALD", "BUY", 1, 100)])
    with pytest.raises(NotFound):
        gw.vote(token, "ZZZ", [_vote("tax_consumption", 1000)])


def test_state_snapshot_schema():
    gw = make_gateway()
    st = gw.public_state()
    for k in ("tick", "clock", "year", "month", "turn_in_month", "phase", "submit_open", "macro"):
        assert k in st                                  # doc 14 14.4.1 StateSnapshot
    assert st["clock"].startswith("Y") and st["submit_open"] is True


def test_currency_conserved_after_player_join():
    gw = make_gateway()
    total0 = gw.store.ledger.total_supply(gw.store.cur)
    _, key = gw.register_player("Hina")
    assert gw.store.ledger.total_supply(gw.store.cur) == total0 + gw.config.investor_start_cash
    for _ in range(10):
        gw.step()
        assert gw.store.ledger.total_supply(gw.store.cur) == total0 + gw.config.investor_start_cash


def test_fastapi_app_http_flow():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from finbox.gateway import create_app

    gw = make_gateway()
    client = TestClient(create_app(gw))
    r = client.post("/v1/players", json={"display_name": "Hina"})
    assert r.status_code == 201
    assert r.json()["entity_id"] == "PLAYER:000000"
    assert r.json()["starting_capital_str"] == str(gw.config.investor_start_cash)
    api_key = r.json()["api_key"]
    # exchange the api key for a Bearer session token (doc 14 14.2)
    tok = client.post("/v1/session", headers={"x-api-key": api_key}).json()["token"]
    auth = {"authorization": f"Bearer {tok}"}
    p = _food_pair(gw.store)
    r = client.post("/v1/orders", headers=auth,
                    json={"orders": [{"pair": p, "side": "BUY", "quantity": 1, "price": gw.store.last_price[p]}]})
    assert r.status_code == 202
    assert r.headers["X-FinBox-Api"] == "v1" and "X-FinBox-Tick" in r.headers
    assert client.post("/v1/admin/step").json()["tick"] == 1
    pf = client.get("/v1/portfolio", headers=auth).json()
    assert any(b["asset_id"] == str(gw.store.food) and b["amount_str"] == "1" for b in pf["balances"])
    # unauthenticated -> 401 with the unified error envelope
    r401 = client.get("/v1/portfolio")
    assert r401.status_code == 401 and r401.json()["error"]["code"] == "unauthenticated"
