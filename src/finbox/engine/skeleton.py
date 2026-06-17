"""M3 turn pipeline: labor market + Leontief production + region cap + needs.

One full P0..P9 turn, deterministically:
  P1  workers produce (mint) their perishable labor, then everyone submits intent
  P2  validate/clamp orders to balances
  P4  clear every market pair (food, labor) and settle double-entry
  P5  the firm consumes labor to produce food, bounded by region_cap (Leontief)
  P6  agents consume food to restore satiety (which decays)
  P7  consumption tax on food purchases (buyers -> GOV)
  P9  expire unused perishable labor, finalize macro, advance the clock
Wages are now market-determined (labor pair), not a fixed transfer. RNG is
unused, so runs are fully deterministic.
"""
from __future__ import annotations
from collections import defaultdict

from ..agents.scripted import ProtoOrder, generate_orders
from ..core import fixed
from ..core.enums import Cause, Side, TurnPhase
from ..init.config import SkeletonConfig
from ..init.genesis import genesis
from ..ledger import LedgerLine
from ..market import clear
from ..market.types import Order, TradingPair
from ..state import StateStore, state_hash


class SkeletonEngine:
    def __init__(self, store: StateStore, config: SkeletonConfig) -> None:
        self.s = store
        self.c = config

    def run_turn(self) -> None:
        s, c = self.s, self.c
        tick = s.tick

        # P1 SUBMIT: workers produce (mint) this turn's perishable labor supply
        if c.q_labor_per_worker > 0:
            s.ledger.post(tick, TurnPhase.P1, Cause.PRODUCTION,
                          [LedgerLine(a, s.labor, c.q_labor_per_worker) for a in s.agents])

        # P1/P2: collect intent, deterministic submit_seq, clamp to balances
        protos = generate_orders(s, c)
        protos.sort(key=lambda p: (str(p.entity), p.pair.pair_id, p.side.value))
        orders_by_pair: dict[str, list[Order]] = defaultdict(list)
        seq = 0
        for p in protos:
            q = self._clamp_qty(p)
            if q <= 0:
                continue
            orders_by_pair[p.pair.pair_id].append(Order(
                order_id=f"ORD:{tick}:{seq:04d}", entity_id=p.entity, pair_id=p.pair.pair_id,
                side=p.side, order_type=p.order_type, limit_price=p.limit_price,
                qty=q, submit_seq=seq))
            seq += 1

        # P3 GOVERN: no-op (fixed policy in this slice)
        # P4 CLEAR + settle, every pair in canonical order
        turnover = 0
        food_spend: dict = {}
        for pair in s.pairs():
            t, spend = self._clear_and_settle(pair, orders_by_pair.get(pair.pair_id, []))
            turnover += t
            if pair.pair_id == s.pair.pair_id:
                food_spend = spend

        self._produce()          # P5
        self._consume()          # P6
        self._tax(food_spend)    # P7 (military P8 = no-op)
        self._expire_perishables()  # P9 part 1
        s.macro["gdp"] = turnover
        s.macro["food_price"] = s.last_price[s.pair.pair_id]
        s.macro["wage"] = s.last_price[s.labor_pair.pair_id]
        s.tick += 1

    def run(self, n_turns: int) -> list[str]:
        return [self._step_hash() for _ in range(n_turns)]

    def _step_hash(self) -> str:
        self.run_turn()
        return state_hash(self.s)

    # ---- phase helpers ----
    def _clamp_qty(self, p: ProtoOrder) -> int:
        s, c = self.s, self.c
        if p.side is Side.BUY:
            price = p.limit_price or 0
            if price <= 0:
                return 0
            cash = s.ledger.get(p.entity, p.pair.quote)
            q = min(p.qty, cash // price)
            while q > 0 and price * q + fixed.fee(price * q, c.fee_rate_bps) > cash:
                q -= 1
            return q
        return min(p.qty, s.ledger.get(p.entity, p.pair.base))

    def _clear_and_settle(self, pair: TradingPair, orders: list[Order]) -> tuple[int, dict]:
        s, c = self.s, self.c
        res = clear(pair.pair_id, orders, s.last_price[pair.pair_id])
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
                lines.append(LedgerLine(f.entity_id, pair.base, f.qty))
                lines.append(LedgerLine(f.entity_id, pair.quote, -(cash_amt + fee_amt)))
                spend[f.entity_id] = spend.get(f.entity_id, 0) + cash_amt
            else:
                lines.append(LedgerLine(f.entity_id, pair.base, -f.qty))
                lines.append(LedgerLine(f.entity_id, pair.quote, cash_amt - fee_amt))
        if total_fee > 0:
            lines.append(LedgerLine(s.exch, pair.quote, total_fee))
        s.ledger.post(s.tick, TurnPhase.P4, Cause.TRADE, lines)
        s.last_price[pair.pair_id] = p
        return p * res.q_star, spend

    def _produce(self) -> None:
        s, c = self.s, self.c
        held = s.ledger.get(s.firm, s.labor)
        cap = s.region_cap.get(s.food, 0)
        food_out = min(held * c.food_per_labor, cap)
        if food_out <= 0:
            return
        labor_used = min(held, (food_out + c.food_per_labor - 1) // c.food_per_labor)
        s.ledger.post(s.tick, TurnPhase.P5, Cause.PRODUCTION,
                      [LedgerLine(s.firm, s.labor, -labor_used), LedgerLine(s.firm, s.food, food_out)])

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

    def _tax(self, spend: dict) -> None:
        s, c = self.s, self.c
        tlines: list[LedgerLine] = []
        for a in sorted(spend, key=str):
            tax = min(fixed.apply_bps_floor(spend[a], c.consumption_tax_bps), s.cash(a))
            if tax > 0:
                tlines.append(LedgerLine(a, s.cur, -tax))
                tlines.append(LedgerLine(s.gov, s.cur, tax))
        if tlines:
            s.ledger.post(s.tick, TurnPhase.P7, Cause.TAX, tlines)

    def _expire_perishables(self) -> None:
        """Burn all unused perishable labor at P9 (doc 08 8.9.4)."""
        s = self.s
        lines = [LedgerLine(e, s.labor, -row[s.labor])
                 for e, row in s.ledger.balances().items()
                 if row.get(s.labor, 0) > 0]
        if lines:
            s.ledger.post(s.tick, TurnPhase.P9, Cause.EXPIRE, lines)


def run_skeleton(config: SkeletonConfig, n_turns: int) -> tuple[StateStore, list[str]]:
    """Genesis + run n turns; return (final store, per-turn state hashes)."""
    store = genesis(config)
    engine = SkeletonEngine(store, config)
    return store, engine.run(n_turns)
