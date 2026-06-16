"""Walking-skeleton turn pipeline: one full P0..P9 turn, deterministically.

A minimal but closed economy: agents buy food (P4) and consume it (P6); the
firm produces food (P5); cash recirculates via consumption tax and firm wages
(P7). Every state change is a ledger posting, so conservation and replay hold.
Most phases that the full spec defines (GOVERN/MILITARY/SNAPSHOT) are no-ops in
this slice. RNG is unused here (the scripted policy is a pure function of state),
so runs are fully deterministic.
"""
from __future__ import annotations

from ..agents.scripted import ProtoOrder, generate_orders
from ..core import fixed
from ..core.enums import Cause, OrderType, Side, TurnPhase
from ..core.fixed import largest_remainder
from ..init.config import SkeletonConfig
from ..init.genesis import genesis
from ..ledger import LedgerLine
from ..market import clear
from ..market.types import Order
from ..state import StateStore, state_hash


class SkeletonEngine:
    def __init__(self, store: StateStore, config: SkeletonConfig) -> None:
        self.s = store
        self.c = config

    # ---- one full turn (P0..P9) ----
    def run_turn(self) -> None:
        s = self.s
        tick = s.tick
        pid = s.pair.pair_id

        # P0 SNAPSHOT: observation is read-only; the scripted policy reads state directly.
        # P1 SUBMIT + P2 VALIDATE: collect intents, assign deterministic submit_seq, clamp.
        protos = generate_orders(s, self.c)
        protos.sort(key=lambda p: (str(p.entity), p.side.value))
        orders: list[Order] = []
        seq = 0
        for p in protos:
            q = self._clamp_qty(p)
            if q <= 0:
                continue
            orders.append(Order(
                order_id=f"ORD:{tick}:{seq:04d}", entity_id=p.entity, pair_id=pid,
                side=p.side, order_type=p.order_type, limit_price=p.limit_price,
                qty=q, submit_seq=seq))
            seq += 1

        # P3 GOVERN: no-op (fixed policy in this slice)
        # P4 CLEAR + settle
        turnover, spend = self._clear_and_settle(orders)
        # P5 PRODUCE
        self._produce()
        # P6 CONSUME
        self._consume()
        # P7 FISCAL (consumption tax -> GOV, wages firm -> agents)
        self._fiscal(spend)
        # P8 MILITARY: no-op
        # P9 ADVANCE
        s.macro["gdp"] = turnover
        s.macro["last_price"] = s.last_price[pid]
        s.tick += 1

    def run(self, n_turns: int) -> list[str]:
        """Run n turns; return the state hash after each turn (replay oracle)."""
        return [self._step_hash() for _ in range(n_turns)]

    def _step_hash(self) -> str:
        self.run_turn()
        return state_hash(self.s)

    # ---- phase helpers ----
    def _clamp_qty(self, p: ProtoOrder) -> int:
        s, c = self.s, self.c
        price = p.limit_price or 0
        if p.side is Side.BUY:
            if price <= 0:
                return 0
            cash = s.cash(p.entity)
            q = min(p.qty, cash // price)
            while q > 0 and price * q + fixed.fee(price * q, c.fee_rate_bps) > cash:
                q -= 1
            return q
        return min(p.qty, s.food_qty(p.entity))

    def _clear_and_settle(self, orders: list[Order]) -> tuple[int, dict]:
        s, c = self.s, self.c
        pid = s.pair.pair_id
        res = clear(pid, orders, s.last_price[pid])
        if res.q_star == 0:
            return 0, {}
        p = res.p_star
        lines: list[LedgerLine] = []
        total_fee = 0
        spend: dict = {}
        for f in res.fills:
            cash_amt = p * f.qty
            fee_amt = fixed.fee(cash_amt, c.fee_rate_bps)
            total_fee += fee_amt
            if f.side is Side.BUY:
                lines.append(LedgerLine(f.entity_id, s.food, f.qty))
                lines.append(LedgerLine(f.entity_id, s.cur, -(cash_amt + fee_amt)))
                spend[f.entity_id] = spend.get(f.entity_id, 0) + cash_amt
            else:
                lines.append(LedgerLine(f.entity_id, s.food, -f.qty))
                lines.append(LedgerLine(f.entity_id, s.cur, cash_amt - fee_amt))
        if total_fee > 0:
            lines.append(LedgerLine(s.exch, s.cur, total_fee))
        s.ledger.post(s.tick, TurnPhase.P4, Cause.TRADE, lines)
        s.last_price[pid] = p
        return p * res.q_star, spend

    def _produce(self) -> None:
        s, c = self.s, self.c
        make = max(0, c.firm_capacity_food - s.food_qty(s.firm))
        if make > 0:
            s.ledger.post(s.tick, TurnPhase.P5, Cause.PRODUCTION,
                          [LedgerLine(s.firm, s.food, make)])

    def _consume(self) -> None:
        s, c = self.s, self.c
        lines: list[LedgerLine] = []
        for a in s.agents:
            have = s.food_qty(a)
            sat = s.satiety[a]
            deficit = 100 - sat
            need = (deficit + c.satiety_per_food - 1) // c.satiety_per_food if deficit > 0 else 0
            eat = min(have, need)
            if eat > 0:
                lines.append(LedgerLine(a, s.food, -eat))
                sat = fixed.clamp(sat + eat * c.satiety_per_food, 0, 100)
            s.satiety[a] = fixed.clamp(sat - c.satiety_decay, 0, 100)
        if lines:
            s.ledger.post(s.tick, TurnPhase.P6, Cause.CONSUMPTION, lines)

    def _fiscal(self, spend: dict) -> None:
        s, c = self.s, self.c
        # consumption tax: buyers -> GOV (conserving)
        tlines: list[LedgerLine] = []
        for a in sorted(spend, key=str):
            tax = min(fixed.apply_bps_floor(spend[a], c.consumption_tax_bps), s.cash(a))
            if tax > 0:
                tlines.append(LedgerLine(a, s.cur, -tax))
                tlines.append(LedgerLine(s.gov, s.cur, tax))
        if tlines:
            s.ledger.post(s.tick, TurnPhase.P7, Cause.TAX, tlines)
        # wages: firm -> agents (conserving), clamped to firm cash
        total = min(c.wage_per_turn * len(s.agents), s.cash(s.firm))
        if total > 0:
            shares = largest_remainder(total, [1] * len(s.agents))
            wlines = [LedgerLine(s.firm, s.cur, -total)]
            wlines += [LedgerLine(a, s.cur, w) for a, w in zip(s.agents, shares) if w > 0]
            s.ledger.post(s.tick, TurnPhase.P7, Cause.FISCAL, wlines)


def run_skeleton(config: SkeletonConfig, n_turns: int) -> tuple[StateStore, list[str]]:
    """Genesis + run n turns; return (final store, per-turn state hashes)."""
    store = genesis(config)
    engine = SkeletonEngine(store, config)
    hashes = engine.run(n_turns)
    return store, hashes
