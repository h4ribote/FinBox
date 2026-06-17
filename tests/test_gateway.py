"""M7 gateway: submission buffer, players, role-gating (doc 02, doc 13, doc 14)."""
from types import SimpleNamespace

import pytest

from finbox.gateway import Gateway
from finbox.gateway.server import Forbidden, NotFound, Unauthenticated
from finbox.init import SkeletonConfig, genesis


def _order(pair, side, qty, price=None, order_type="LIMIT"):
    return SimpleNamespace(pair=pair, side=side, qty=qty, price=price, order_type=order_type)


def _food_pair(store) -> str:
    return f"{store.food}/{store.cur}"


def make_gateway():
    c = SkeletonConfig()
    return Gateway(genesis(c), c)


def test_register_player_endows_cash():
    gw = make_gateway()
    ent, token = gw.register_player("Hina")
    assert str(ent).startswith("PLAYER:")
    assert gw.store.cash(ent) == gw.config.investor_start_cash


def test_auth_required():
    gw = make_gateway()
    with pytest.raises(Unauthenticated):
        gw.portfolio("bad-token")
    with pytest.raises(Unauthenticated):
        gw.submit_orders(None, [])


def test_player_can_trade_via_buffer_and_step():
    gw = make_gateway()
    ent, token = gw.register_player("Hina")
    price = gw.store.last_price[_food_pair(gw.store)]
    # at tick 0 agents are not hungry, so only the player bids for the firm's food
    gw.submit_orders(token, [_order(_food_pair(gw.store), "BUY", 1, price)])
    assert gw.buffer.pending(0) == 1
    gw.step()
    assert gw.store.food_qty(ent) == 1            # player received food
    assert gw.store.cash(ent) < gw.config.investor_start_cash  # paid for it


def test_submission_is_idempotent_latest_wins():
    gw = make_gateway()
    ent, token = gw.register_player("Hina")
    p = _food_pair(gw.store)
    px = gw.store.last_price[p]
    gw.submit_orders(token, [_order(p, "BUY", 1, px)])
    gw.submit_orders(token, [_order(p, "BUY", 3, px)])   # overwrites
    gw.step()
    assert gw.store.food_qty(ent) == 3


def test_role_gating_blocks_player_from_voting():
    gw = make_gateway()
    _, token = gw.register_player("Hina")          # INVESTOR only
    with pytest.raises(Forbidden):
        gw.vote(token)


def test_unknown_pair_rejected():
    gw = make_gateway()
    _, token = gw.register_player("Hina")
    with pytest.raises(NotFound):
        gw.submit_orders(token, [_order("COMM:bogus.thing/CUR:ALD", "BUY", 1, 100)])


def test_currency_conserved_after_player_join():
    gw = make_gateway()
    total0 = gw.store.ledger.total_supply(gw.store.cur)
    _, token = gw.register_player("Hina")
    # registration mints the player's endowment (a genesis mint point)
    total1 = gw.store.ledger.total_supply(gw.store.cur)
    assert total1 == total0 + gw.config.investor_start_cash
    for _ in range(10):
        gw.step()
        assert gw.store.ledger.total_supply(gw.store.cur) == total1  # conserved thereafter


def test_fastapi_app_http_flow():
    httpx = pytest.importorskip("httpx")  # starlette TestClient needs httpx
    from fastapi.testclient import TestClient
    from finbox.gateway import create_app

    gw = make_gateway()
    client = TestClient(create_app(gw))
    r = client.post("/v1/players", json={"display_name": "Hina"})
    assert r.status_code == 201
    token = r.json()["api_key"]
    p = _food_pair(gw.store)
    px = gw.store.last_price[p]
    r = client.post("/v1/orders", headers={"x-api-key": token},
                    json={"orders": [{"pair": p, "side": "BUY", "qty": 1, "price": px}]})
    assert r.status_code == 202
    assert client.post("/v1/admin/step").json()["tick"] == 1
    pf = client.get("/v1/portfolio", headers={"x-api-key": token}).json()
    assert pf["balances"].get(str(gw.store.food)) == 1
    # unauthenticated is rejected
    assert client.get("/v1/portfolio").status_code == 401
