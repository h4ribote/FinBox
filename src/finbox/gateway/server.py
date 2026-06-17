"""Client gateway: player registration, observation reads, order submission,
role-gating, and a turn-step trigger (doc 02, doc 13, doc 14).

The Gateway class holds the engine + submission buffer and is independently
unit-testable; create_app() wraps it in a FastAPI app. Players are clients on
the same ledger/markets as agents (doc 13 13.1), gated only by role.

(No ``from __future__ import annotations`` here: FastAPI must resolve the
request-model annotations on the route handlers at runtime.)
"""
from typing import Any

from ..agents.scripted import ProtoOrder
from ..core.enums import Cause, OrderType, Side, TurnPhase
from ..core.ids import EntityId
from ..engine.skeleton import SkeletonEngine
from ..ledger import LedgerLine
from ..state import StateStore, state_hash
from .buffer import SubmissionBuffer


class Unauthenticated(Exception):
    pass


class Forbidden(Exception):
    pass


class NotFound(Exception):
    pass


class Gateway:
    """Server-authoritative boundary around a StateStore + engine."""

    def __init__(self, store: StateStore, config: Any) -> None:
        self.store = store
        self.config = config
        self.engine = SkeletonEngine(store, config)
        self.buffer = SubmissionBuffer()
        self.tokens: dict[str, dict] = {}
        self._next_player = 1

    # ---- onboarding (doc 13 13.3) ----
    def register_player(self, display_name: str, roles: tuple[str, ...] = ("INVESTOR",)) -> tuple[EntityId, str]:
        ent = EntityId.player(self._next_player)
        self._next_player += 1
        token = f"tok-{ent}"
        # equal initial capital, minted as a genesis-style endowment (doc 13 13.3.4)
        self.store.ledger.post(self.store.tick, TurnPhase.INIT, Cause.GENESIS,
                               [LedgerLine(ent, self.store.cur, self.config.investor_start_cash)])
        self.tokens[token] = {"entity": ent, "roles": set(roles), "display_name": display_name}
        return ent, token

    def _auth(self, token: str | None) -> dict:
        info = self.tokens.get(token or "")
        if info is None:
            raise Unauthenticated("unauthenticated")
        return info

    # ---- write (doc 14 14.5) ----
    def submit_orders(self, token: str | None, reqs: list[Any]) -> int:
        info = self._auth(token)
        if "INVESTOR" not in info["roles"]:
            raise Forbidden("role_not_permitted")
        ent = info["entity"]
        protos: list[ProtoOrder] = []
        for r in reqs:
            pair = self.store.pairs.get(r.pair)
            if pair is None:
                raise NotFound("unknown pair")
            price = getattr(r, "price", None)
            protos.append(ProtoOrder(ent, pair, Side(r.side),
                                     OrderType(getattr(r, "order_type", "LIMIT")), price, r.qty))
        self.buffer.submit(self.store.tick, ent, protos)   # idempotent latest-wins
        return len(protos)

    def vote(self, token: str | None, payload: Any = None) -> dict:
        info = self._auth(token)
        if "POLITICIAN" not in info["roles"]:
            raise Forbidden("role_not_permitted")
        return {"accepted": True}

    # ---- read (doc 14 14.4) ----
    def public_state(self) -> dict:
        return {
            "tick": self.store.tick,
            "prices": dict(self.store.last_price),
            "macro": dict(self.store.macro),
            "state_hash": state_hash(self.store),
        }

    def portfolio(self, token: str | None) -> dict:
        info = self._auth(token)
        ent = info["entity"]
        bals = self.store.ledger.balances().get(ent, {})
        return {
            "entity_id": ent,
            "roles": sorted(info["roles"]),
            "balances": {str(a): q for a, q in bals.items()},
            "net_worth": self.store.net_worth(ent),
        }

    # ---- engine step (P1 deadline -> P2..P9) ----
    def step(self) -> int:
        external = self.buffer.freeze(self.store.tick)
        self.engine.run_turn(external)
        return self.store.tick


def create_app(gateway: Gateway):
    """Wrap a Gateway in a FastAPI app (doc 14)."""
    from fastapi import FastAPI, Header, HTTPException
    from pydantic import BaseModel

    app = FastAPI(title="FinBox", version="0.0.1")

    class PlayerReq(BaseModel):
        display_name: str

    class OrderReq(BaseModel):
        pair: str
        side: str
        qty: int
        order_type: str = "LIMIT"
        price: int | None = None

    class OrdersReq(BaseModel):
        orders: list[OrderReq]

    @app.post("/v1/players", status_code=201)
    def register(body: PlayerReq):
        ent, token = gateway.register_player(body.display_name)
        return {"entity_id": ent, "api_key": token, "roles": ["INVESTOR"]}

    @app.get("/v1/state")
    def state():
        return gateway.public_state()

    @app.get("/v1/portfolio")
    def portfolio(x_api_key: str = Header(None)):
        try:
            return gateway.portfolio(x_api_key)
        except Unauthenticated:
            raise HTTPException(401, "unauthenticated")

    @app.post("/v1/orders", status_code=202)
    def orders(body: OrdersReq, x_api_key: str = Header(None)):
        try:
            n = gateway.submit_orders(x_api_key, body.orders)
            return {"accepted": n, "tick": gateway.store.tick}
        except Unauthenticated:
            raise HTTPException(401, "unauthenticated")
        except Forbidden:
            raise HTTPException(403, "role_not_permitted")
        except NotFound:
            raise HTTPException(404, "not_found")

    @app.post("/v1/governments/{cc}/vote")
    def vote(cc: str, x_api_key: str = Header(None)):
        try:
            return gateway.vote(x_api_key)
        except Unauthenticated:
            raise HTTPException(401, "unauthenticated")
        except Forbidden:
            raise HTTPException(403, "role_not_permitted")

    @app.post("/v1/admin/step")
    def step():
        return {"tick": gateway.step()}

    return app
