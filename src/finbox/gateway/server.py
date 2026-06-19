"""Client gateway: two-layer auth, observation reads, order/vote submission, role-gating
(doc 02, doc 13, doc 14).

The Gateway holds the engine + submission buffer and is independently unit-testable;
create_app() wraps it in a FastAPI app. Authentication is two-layer (doc 14.2): a long-lived
API key is exchanged at POST /v1/session for a short-lived Bearer JWT; all other requests carry
the Bearer token. Players are clients on the same ledger/markets as agents, gated only by role.

(No ``from __future__ import annotations`` here: FastAPI must resolve the request-model
annotations on the route handlers at runtime.)
"""
import base64
import hashlib
import hmac
import json
from typing import Any

from ..agents.scripted import ProtoOrder
from ..core.enums import (
    CountryCode, OrderType, PositionSide, Side, TradeMode, is_margin_eligible_base)
from ..core.ids import AssetId, EntityId
from ..engine.skeleton import SkeletonEngine
from ..state import StateStore, state_hash
from .buffer import SubmissionBuffer

# INVESTOR and its derived specializations may trade financial instruments (doc 06 6.6/6.9)
CAPITAL_ROLES = {"ENTREPRENEUR", "INVESTOR", "MARKET_MAKER",
                 "YIELD_INVESTOR", "ARBITRAGEUR", "AMM"}
# roles allowed to open MARGIN (信用取引) positions (doc 06 6.5/6.6)
MARGIN_ROLES = {"INVESTOR", "YIELD_INVESTOR", "ARBITRAGEUR", "MARKET_MAKER"}
GOVERN_ROLES = {"POLITICIAN", "CENTRAL_BANKER", "BUREAUCRAT", "GENERAL", "DIPLOMAT"}
VOTE_LEVERS = {"policy_rate", "tax_income", "tax_corporate", "tax_consumption", "gov_spending",
               "welfare_level", "bond_issuance_cap", "subsidy_focus", "subsidy_rate",
               "military_budget", "military_targets", "min_wage", "immigration_openness"}


class Unauthenticated(Exception):
    pass


class Forbidden(Exception):
    pass


class NotFound(Exception):
    pass


class SubmitClosed(Exception):
    pass


class NotCancellable(Exception):
    pass


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


class Gateway:
    """Server-authoritative boundary around a StateStore + engine (doc 02 2.1)."""

    def __init__(self, store: StateStore, config: Any) -> None:
        self.store = store
        self.config = config
        self.engine = SkeletonEngine(store, config)
        self.buffer = SubmissionBuffer()
        self.api_keys: dict[str, dict] = {}        # api_key -> {entity, roles, country, base_currency, ...}
        self.revoked: set = set()                  # revoked session token jtis
        self._orders: dict = {}                    # order_id -> {entity, tick, proto} (for cancellation)
        self._order_seq = 0
        self.submit_open = True                    # P1 SUBMIT window state (doc 14 14.7)

    # ---- onboarding (doc 13 13.3, doc 14 14.2.2) ----
    def register_player(self, display_name: str, country: str = "ALD", base_currency: str | None = None,
                        endowment_basis: str | None = None, requested_roles=("INVESTOR",)) -> tuple[EntityId, str]:
        roles = self._grant_roles(requested_roles)
        ent = self.engine.onboard_player(self.config.investor_start_cash)   # engine is the sole writer (doc 02 2.1)
        api_key = f"key-{ent}"
        self.api_keys[api_key] = {
            "entity": ent, "roles": set(roles), "display_name": display_name, "country": country,
            "base_currency": base_currency or str(self.store.cur),
            "endowment_basis": endowment_basis or self.config.endowment_basis,
        }
        return ent, api_key

    def _grant_roles(self, requested) -> list[str]:
        c = self.config
        granted: list[str] = []
        for r in requested:
            if r in ("INVESTOR", "YIELD_INVESTOR", "ARBITRAGEUR") \
                    or (r == "ENTREPRENEUR" and c.allow_entrepreneur) \
                    or (r == "MARKET_MAKER" and c.allow_market_maker) \
                    or (r == "AMM" and c.allow_amm) \
                    or (r in GOVERN_ROLES and c.allow_public_roles):
                granted.append(r)
            else:
                raise Forbidden("role_not_permitted")
        return granted or ["INVESTOR"]

    # ---- two-layer auth (doc 14 14.2) ----
    @staticmethod
    def _scope_for(roles: set) -> list[str]:
        scope = ["read", "trade", "act"]
        if roles & GOVERN_ROLES:
            scope.append("govern")
        return scope

    def _sign(self, payload: dict) -> str:
        header = _b64(b'{"alg":"HS256","typ":"JWT"}')
        body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        sig = hmac.new(self.config.jwt_secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
        return f"{header}.{body}.{_b64(sig)}"

    def create_session(self, api_key: str | None, requested_scope=None) -> dict:
        info = self.api_keys.get(api_key or "")
        if info is None:
            raise Unauthenticated("unauthenticated")
        scope = self._scope_for(info["roles"])
        if requested_scope:
            scope = [s for s in scope if s in set(requested_scope)]
        expires_tick = self.store.tick + self.config.session_ttl_turns
        jti = f"{info['entity']}:{self.store.tick}:{len(self.revoked)}:{id(info) & 0xffff}"
        payload = {"sub": str(info["entity"]), "roles": sorted(info["roles"]),
                   "scope": scope, "exp_tick": expires_tick, "jti": jti}
        return {"token": self._sign(payload), "token_type": "Bearer", "entity_id": str(info["entity"]),
                "roles": sorted(info["roles"]), "expires_tick": expires_tick,
                "expires_at": self.engine.cal.label(expires_tick), "scope": scope}

    def refresh_session(self, token: str | None) -> dict:
        claims = self._auth(token)
        info = next((v for v in self.api_keys.values() if str(v["entity"]) == claims["sub"]), None)
        if info is None:
            raise Unauthenticated("unauthenticated")
        self.revoked.add(claims["jti"])                         # rotate: invalidate the old token
        return self.create_session(next(k for k, v in self.api_keys.items() if v is info))

    def revoke_session(self, token: str | None) -> dict:
        claims = self._auth(token)
        self.revoked.add(claims["jti"])
        return {"revoked": True}

    def _auth(self, token: str | None) -> dict:
        if not token:
            raise Unauthenticated("unauthenticated")
        try:
            header, body, sig = token.split(".")
            expect = hmac.new(self.config.jwt_secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
            if not hmac.compare_digest(_b64(expect), sig):
                raise Unauthenticated("unauthenticated")
            pad = body + "=" * (-len(body) % 4)
            claims = json.loads(base64.urlsafe_b64decode(pad))
        except Unauthenticated:
            raise
        except Exception:
            raise Unauthenticated("unauthenticated")
        if claims.get("jti") in self.revoked or claims.get("exp_tick", -1) < self.store.tick:
            raise Unauthenticated("unauthenticated")
        return claims

    # ---- write (doc 14 14.5) ----
    def _classify_financial(self, pair) -> bool:
        """Financial-instrument trade (FX / BOND / BILL / EQ) vs spot goods (doc 06 6.9)."""
        base = str(pair.base)
        return (base.startswith(("EQ:", "BOND:", "BILL:", "FUT:"))
                or base.startswith("CUR:"))                    # CUR base => FX pair

    def submit_orders(self, token: str | None, reqs: list[Any]) -> dict:
        claims = self._auth(token)
        if "trade" not in claims["scope"]:                      # all roles hold trade scope (doc 14 14.5)
            raise Forbidden("role_not_permitted")
        if not self.submit_open:
            raise SubmitClosed("submit_closed")
        if len(reqs) > self.config.max_orders_per_turn:         # per-turn cap (doc 13 13.6)
            raise Forbidden("rate_limited")
        ent = EntityId(claims["sub"])
        roles = set(claims["roles"])
        accepted, rejected, protos = [], [], []
        for r in reqs:
            cref = getattr(r, "client_ref", None)
            pair = self.store.pairs.get(r.pair)
            if pair is None:
                raise NotFound("unknown pair")
            if self._classify_financial(pair) and not (roles & CAPITAL_ROLES):
                rejected.append({"client_ref": cref, "code": "role_not_permitted",
                                 "message": f"financial-instrument trade requires {sorted(CAPITAL_ROLES)}"})
                continue
            qty = getattr(r, "quantity", None)
            qty = getattr(r, "qty", qty) if qty is None else qty   # accept canonical 'quantity'
            price = getattr(r, "price", None)
            mode = TradeMode(getattr(r, "trade_mode", "SPOT") or "SPOT")
            pside = getattr(r, "position_side", None)
            intent = getattr(r, "intent", "OPEN") or "OPEN"
            position_id = getattr(r, "position_id", None)
            if mode is TradeMode.MARGIN:
                if not self.config.allow_margin or not (roles & MARGIN_ROLES):
                    rejected.append({"client_ref": cref, "code": "role_not_permitted",
                                     "message": f"margin trading requires {sorted(MARGIN_ROLES)}"})
                    continue
                if not is_margin_eligible_base(str(pair.base)) or str(pair.quote) != str(self.store.cur):
                    rejected.append({"client_ref": cref, "code": "validation_failed",
                                     "message": "pair not margin-eligible (CUR/CUR, EQ/CUR, storable COMM/CUR)"})
                    continue
            elif Side(r.side) is Side.SELL and self.store.ledger.get(ent, pair.base) < (qty or 0):
                # SPOT SELL needs base inventory (no naked spot short, doc 09 9.5)
                rejected.append({"client_ref": cref, "code": "insufficient_balance",
                                 "message": f"{pair.base} balance {self.store.ledger.get(ent, pair.base)} < {qty}"})
                continue
            proto = ProtoOrder(ent, pair, Side(r.side), OrderType(getattr(r, "order_type", "LIMIT")),
                               price, qty, trade_mode=mode,
                               position_side=PositionSide(pside) if pside else None,
                               intent=intent, position_id=position_id)
            self._order_seq += 1
            oid = f"ORD:{self.store.tick:06d}:{self._order_seq:04d}"
            self._orders[oid] = {"entity": ent, "tick": self.store.tick, "proto": proto}
            protos.append(proto)
            accepted.append({"client_ref": cref, "order_id": oid, "status": "QUEUED"})
        self.buffer.submit(self.store.tick, ent, protos)        # idempotent latest-wins
        return {"tick": self.store.tick, "accepted": accepted, "rejected": rejected}

    def lending_op(self, token: str | None, kind: str, asset_id: str, amount: int) -> dict:
        """Queue a lending-pool deposit (SUPPLY) or redemption (WITHDRAW); applied at next P4 start.

        Pool operations are confirmed before board-clearing (doc 09 §プール操作の順序).
        """
        claims = self._auth(token)
        # lending.supply/withdraw is a capital-role action (doc 06 §6.9 matrix): only ENTREPRENEUR /
        # INVESTOR / MARKET_MAKER / YIELD_INVESTOR / ARBITRAGEUR / AMM may supply or redeem pool shares.
        if not (set(claims["roles"]) & CAPITAL_ROLES):
            raise Forbidden("role_not_permitted")
        if asset_id not in self.store.lending_pools:
            raise NotFound("unknown pool")
        ent = EntityId(claims["sub"])
        self.store.pending_pool_ops.append(
            {"kind": kind, "entity": ent, "asset": AssetId(asset_id), "qty": int(amount)})
        return {"queued": True, "kind": kind, "asset_id": asset_id, "amount": int(amount),
                "tick": self.store.tick}

    def cancel_order(self, token: str | None, order_id: str) -> dict:
        claims = self._auth(token)
        rec = self._orders.get(order_id)
        if rec is None or str(rec["entity"]) != claims["sub"] or rec["tick"] != self.store.tick:
            raise NotCancellable("order_not_cancellable")
        del self._orders[order_id]
        ent = rec["entity"]
        remaining = [v["proto"] for v in self._orders.values() if v["entity"] == ent and v["tick"] == self.store.tick]
        self.buffer.submit(self.store.tick, ent, remaining)     # re-submit without the cancelled order
        return {"order_id": order_id, "status": "CANCELLED"}

    def vote(self, token: str | None, country: str | None = None, votes=None) -> dict:
        claims = self._auth(token)
        if "govern" not in claims["scope"]:                     # POLITICIAN-style govern scope (doc 14 14.5.6)
            raise Forbidden("role_not_permitted")
        if country is not None and country not in CountryCode.__members__:
            raise NotFound("unknown country")
        cc = country or (self.store.gov.country.value if self.store.gov.country else None)
        per_lever = self.store.pending_votes.setdefault(cc, {})
        for v in (votes or []):
            lever = getattr(v, "lever", None) if not isinstance(v, dict) else v.get("lever")
            kind = getattr(v, "kind", None) if not isinstance(v, dict) else v.get("kind")
            value = getattr(v, "value", None) if not isinstance(v, dict) else v.get("value")
            if lever not in VOTE_LEVERS:
                raise Forbidden("validation_failed")
            if kind == "SCALAR" and value is not None:
                per_lever.setdefault(lever, []).append(int(value))
        return {"accepted": True}

    # ---- read (doc 14 14.4) ----
    def _lending_view(self) -> list[dict]:
        """Per-pool observation: utilization, borrow/supply rates, available (doc 09 §貸借プール)."""
        s, m = self.store, self.engine.margin
        c = self.config
        out = []
        for asset in sorted(s.lending_pools):
            pool = s.lending_pools[asset]
            base_rate = m._base_rate(pool)
            out.append({
                "asset_id": asset, "supplied": pool.supplied, "borrowed": pool.borrowed,
                "available": s.ledger.get(pool.entity_id, pool.asset),
                "utilization_bps": pool.utilization_bps(),
                "borrow_rate_bps": pool.borrow_rate(base_rate, c.lending_slope1_bps,
                                                    c.lending_slope2_bps, c.lending_u_kink_bps),
                "supply_rate_bps": pool.supply_rate(base_rate, c.lending_slope1_bps, c.lending_slope2_bps,
                                                    c.lending_u_kink_bps, c.lending_reserve_factor_bps),
            })
        return out

    def public_state(self) -> dict:
        s = self.store
        cal = self.engine.cal
        y, m, t = cal.decompose(s.tick)
        return {
            "tick": s.tick, "clock": cal.label(s.tick), "year": y, "month": m, "turn_in_month": t,
            "phase": "P0", "submit_open": self.submit_open,
            "wui_level": s.macro.get("investor_nav", 0),
            "prices": dict(s.last_price),
            "macro": {k: v for k, v in s.macro.items()},
            # margin facilities (doc 09 信用取引): lending pools, insurance buffer, AMM reserves
            "lending_pools": self._lending_view(),
            "insurance": {a: s.ledger.get(e, s.cur) for a, e in s.insurance.items()},
            "amm_pools": [{"pair": a.pair_id, "r_base": a.r_base, "r_quote": a.r_quote,
                           "spread_bps": a.spread_bps, "invariant": a.invariant.value}
                          for a in s.amm_pools.values()],
            "state_hash": state_hash(s),
        }

    def portfolio(self, token: str | None) -> dict:
        claims = self._auth(token)
        ent = EntityId(claims["sub"])
        bals = self.store.ledger.balances().get(ent, {})
        open_orders = [
            {"order_id": oid, "pair": v["proto"].pair.pair_id, "side": v["proto"].side.value,
             "order_type": v["proto"].order_type.value, "price": v["proto"].limit_price,
             "quantity": v["proto"].qty}
            for oid, v in self._orders.items()
            if v["entity"] == ent and v["tick"] == self.store.tick
        ]
        s = self.store
        positions = []
        for pos in s.positions:
            if pos.entity != ent:
                continue
            base = pos.pair_id.split("/", 1)[0]
            mark = s.mark_price(base)
            positions.append({
                "position_id": pos.position_id, "pair": pos.pair_id, "side": pos.side.value,
                "qty": pos.qty, "entry_price": pos.entry_price,
                "borrowed_asset": str(pos.borrowed_asset), "borrowed_qty": pos.borrowed_qty,
                "collateral_asset": str(pos.collateral_asset), "collateral_qty": pos.collateral_qty,
                "accrued_interest": pos.accrued_interest,
                "equity_str": str(pos.equity(mark)), "margin_ratio_bps": pos.margin_ratio_bps(mark),
            })
        return {
            "entity_id": str(ent),
            "tick": s.tick,
            "balances": [{"asset_id": str(a), "amount_str": str(q)} for a, q in bals.items()],
            "open_orders": open_orders,
            "net_worth_wui_str": str(s.net_worth(ent)),
            "positions": positions,   # margin (信用) positions with mark-to-market equity / margin ratio
        }

    # ---- engine step (P1 deadline -> P2..P9) ----
    def step(self) -> int:
        self.submit_open = False
        external = self.buffer.freeze(self.store.tick)
        self.engine.run_turn(external)
        self._orders = {}                 # the window for the old tick is closed; clear ack registry
        self.submit_open = True
        return self.store.tick


def create_app(gateway: Gateway):
    """Wrap a Gateway in a FastAPI app (doc 14)."""
    from fastapi import FastAPI, Header, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel

    app = FastAPI(title="FinBox", version="0.0.1")

    _MSG = {"unauthenticated": "missing or invalid token", "role_not_permitted": "role/scope not permitted",
            "not_found": "resource not found", "submit_closed": "submission window is closed",
            "order_not_cancellable": "order not cancellable", "validation_failed": "invalid request",
            "rate_limited": "too many orders this turn"}
    _STATUS = {"unauthenticated": 401, "role_not_permitted": 403, "not_found": 404,
               "submit_closed": 409, "order_not_cancellable": 409, "validation_failed": 400,
               "rate_limited": 429}

    def err(code: str):
        return JSONResponse(status_code=_STATUS.get(code, 400), content={"error": {
            "code": code, "message": _MSG.get(code, code), "tick": gateway.store.tick, "details": {}}})

    @app.middleware("http")
    async def finbox_headers(request: Request, call_next):    # doc 14 14.3 / 14.1
        try:
            response = await call_next(request)
        except _AppError as e:
            response = err(e.code)
        response.headers["X-FinBox-Api"] = "v1"
        response.headers["X-FinBox-Tick"] = str(gateway.store.tick)
        response.headers["X-FinBox-Phase"] = "P0" if gateway.submit_open else "P2"
        response.headers["X-FinBox-Submit-Open"] = "1" if gateway.submit_open else "0"
        return response

    def bearer(authorization: str | None) -> str | None:
        if authorization and authorization.lower().startswith("bearer "):
            return authorization[7:]
        return authorization

    class PlayerReq(BaseModel):
        display_name: str
        country: str = "ALD"
        base_currency: str | None = None
        endowment_basis: str | None = None    # None -> fall back to config.endowment_basis (doc 16 §16.7.4)
        requested_roles: list[str] = ["INVESTOR"]

    class SessionReq(BaseModel):
        requested_scope: list[str] | None = None
        client: str | None = None

    class OrderReq(BaseModel):
        pair: str
        side: str
        quantity: int
        order_type: str = "LIMIT"
        price: int | None = None
        client_ref: str | None = None
        tif: str = "GFT"
        expires_tick: int | None = None
        # margin (信用取引, doc 09 / doc 14 14.6.1): SPOT board orders ignore these
        trade_mode: str = "SPOT"             # SPOT | MARGIN
        position_side: str | None = None     # LONG | SHORT (MARGIN only)
        intent: str = "OPEN"                 # OPEN | CLOSE
        position_id: str | None = None       # target position for intent=CLOSE

    class OrdersReq(BaseModel):
        orders: list[OrderReq]

    class LendingReq(BaseModel):
        asset_id: str
        amount: int                          # SUPPLY: asset units; WITHDRAW: pool shares

    class PolicyVote(BaseModel):
        lever: str
        kind: str
        value: int | None = None
        scores: dict | None = None
        weights: dict | None = None

    class VoteReq(BaseModel):
        votes: list[PolicyVote]

    @app.post("/v1/players", status_code=201)
    def register(body: PlayerReq):
        try:
            ent, key = gateway.register_player(body.display_name, body.country, body.base_currency,
                                               body.endowment_basis, tuple(body.requested_roles))
        except Forbidden:
            return err("role_not_permitted")
        info = gateway.api_keys[key]
        return {"entity_id": str(ent), "api_key": key, "country": info["country"],
                "base_currency": info["base_currency"], "endowment_basis": info["endowment_basis"],
                "starting_capital_str": str(gateway.config.investor_start_cash),
                "roles": sorted(info["roles"])}

    @app.post("/v1/session")
    def session(body: SessionReq | None = None, x_api_key: str = Header(None)):
        try:
            return gateway.create_session(x_api_key, body.requested_scope if body else None)
        except Unauthenticated:
            return err("unauthenticated")

    @app.post("/v1/session/refresh")
    def session_refresh(authorization: str = Header(None)):
        try:
            return gateway.refresh_session(bearer(authorization))
        except Unauthenticated:
            return err("unauthenticated")

    @app.delete("/v1/session")
    def session_delete(authorization: str = Header(None)):
        try:
            return gateway.revoke_session(bearer(authorization))
        except Unauthenticated:
            return err("unauthenticated")

    @app.get("/v1/state")
    def state():
        return gateway.public_state()

    @app.get("/v1/portfolio")
    def portfolio(authorization: str = Header(None)):
        try:
            return gateway.portfolio(bearer(authorization))
        except Unauthenticated:
            return err("unauthenticated")

    @app.post("/v1/orders", status_code=202)
    def orders(body: OrdersReq, authorization: str = Header(None)):
        try:
            return gateway.submit_orders(bearer(authorization), body.orders)
        except Unauthenticated:
            return err("unauthenticated")
        except Forbidden as e:
            return err(str(e) or "role_not_permitted")
        except SubmitClosed:
            return err("submit_closed")
        except NotFound:
            return err("not_found")

    @app.delete("/v1/orders/{order_id}")
    def cancel(order_id: str, authorization: str = Header(None)):
        try:
            return gateway.cancel_order(bearer(authorization), order_id)
        except Unauthenticated:
            return err("unauthenticated")
        except NotCancellable:
            return err("order_not_cancellable")

    @app.post("/v1/lending/{asset_id}/deposit")
    def lending_deposit(asset_id: str, body: LendingReq, authorization: str = Header(None)):
        try:
            return gateway.lending_op(bearer(authorization), "SUPPLY", asset_id, body.amount)
        except Unauthenticated:
            return err("unauthenticated")
        except Forbidden as e:
            return err(str(e) or "role_not_permitted")
        except NotFound:
            return err("not_found")

    @app.post("/v1/lending/{asset_id}/withdraw")
    def lending_withdraw(asset_id: str, body: LendingReq, authorization: str = Header(None)):
        try:
            return gateway.lending_op(bearer(authorization), "WITHDRAW", asset_id, body.amount)
        except Unauthenticated:
            return err("unauthenticated")
        except Forbidden as e:
            return err(str(e) or "role_not_permitted")
        except NotFound:
            return err("not_found")

    @app.post("/v1/governments/{cc}/vote")
    def vote(cc: str, body: VoteReq, authorization: str = Header(None)):
        try:
            return gateway.vote(bearer(authorization), cc, body.votes)
        except Unauthenticated:
            return err("unauthenticated")
        except Forbidden as e:
            return err(str(e) or "role_not_permitted")
        except NotFound:
            return err("not_found")

    @app.post("/v1/admin/step")
    def step():
        return {"tick": gateway.step()}

    return app


class _AppError(Exception):
    def __init__(self, code: str):
        self.code = code
