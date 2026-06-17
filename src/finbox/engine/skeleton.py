"""M4 turn pipeline: multi-firm supply chain with capacity (doc 10).

P1  workers mint perishable labor (by kind); everyone submits intent
P2  clamp orders to balances
P4  clear every market pair, settle double-entry
P5  per firm (entity order): expand capacity from construction labor, run the
    Leontief recipe (bounded by capacity, inputs, region cap), then depreciate
P6  agents consume food (satiety) ; P7 consumption tax ; P9 expire labor, advance
Fully deterministic (no RNG used in this slice).
"""
from __future__ import annotations
from collections import defaultdict

from ..agents.scripted import ProtoOrder, generate_orders
from ..core import fixed
from ..core.enums import Cause, Side, TurnPhase
from ..core.ids import AssetId, EntityId
from ..core.time import Calendar
from ..init.config import SkeletonConfig
from ..init.genesis import genesis
from ..ledger import LedgerLine
from ..market import clear
from ..market.types import Order, TradingPair
from ..politics import aggregate_scalar
from ..state import StateStore, state_hash


class SkeletonEngine:
    def __init__(self, store: StateStore, config: SkeletonConfig) -> None:
        self.s = store
        self.c = config
        self.cal = Calendar()

    def run_turn(self, external_protos=None) -> None:
        s, c = self.s, self.c
        tick = s.tick

        # P1: workers produce (mint) their perishable labor
        if c.q_labor_per_worker > 0:
            s.ledger.post(tick, TurnPhase.P1, Cause.PRODUCTION,
                          [LedgerLine(a, s.agent_labor[a], c.q_labor_per_worker) for a in s.agents])

        # P1/P2: collect scripted intent plus any externally submitted (player/agent) orders,
        # assign deterministic submit_seq, validate+clamp with per-entity cash/inventory
        # reservation so multiple orders cannot double-spend (doc 09 9.5)
        protos = generate_orders(s, c)
        if external_protos:
            protos = protos + list(external_protos)
        protos.sort(key=lambda p: (str(p.entity), p.pair.pair_id, p.side.value))
        orders_by_pair: dict[str, list[Order]] = defaultdict(list)
        reserved_cash: dict = defaultdict(int)
        reserved_sell: dict = defaultdict(int)
        seq = 0
        for p in protos:
            if p.side is Side.BUY:
                price = p.limit_price or 0
                if price <= 0:
                    continue
                avail = s.ledger.get(p.entity, p.pair.quote) - reserved_cash[p.entity]
                q = min(p.qty, avail // price)
                while q > 0 and price * q + fixed.fee(price * q, c.fee_rate_bps) > avail:
                    q -= 1
                if q <= 0:
                    continue
                reserved_cash[p.entity] += price * q + fixed.fee(price * q, c.fee_rate_bps)
            else:
                key = (p.entity, p.pair.base)
                q = min(p.qty, s.ledger.get(p.entity, p.pair.base) - reserved_sell[key])
                if q <= 0:
                    continue
                reserved_sell[key] += q
            orders_by_pair[p.pair.pair_id].append(Order(
                order_id=f"ORD:{tick}:{seq:04d}", entity_id=p.entity, pair_id=p.pair.pair_id,
                side=p.side, order_type=p.order_type, limit_price=p.limit_price, qty=q, submit_seq=seq))
            seq += 1

        self._govern()            # P3 GOVERN: aggregate politician proposals into policy

        # P4 CLEAR all pairs
        turnover = 0
        food_spend: dict = {}
        for pair in s.sorted_pairs():
            t, spend = self._clear_and_settle(pair, orders_by_pair.get(pair.pair_id, []))
            turnover += t
            if pair.base == s.food:
                food_spend = spend

        self._produce_all()       # P5
        self._consume()           # P6
        self._tax(food_spend)     # P7 taxation (policy-driven rate)
        self._welfare()           # P7 welfare transfers to low-cash agents
        self._finance()           # P7 coupons / dividends / redemptions
        expired = self._expire_perishables()  # P9
        self._finalize_macro(turnover, expired)
        s.tick += 1

    def _finalize_macro(self, turnover: int, expired_labor: int) -> None:
        """P9: confirm macro indicators / KPIs (doc 00 0.16)."""
        s, c = self.s, self.c
        s.macro["gdp"] = turnover
        s.macro["policy_rate"] = s.cb_policy_rate_bps
        if s.investors:
            s.macro["investor_nav"] = s.net_worth(s.investors[0])
        n = len(s.agents)
        s.macro["avg_satiety"] = sum(s.satiety.values()) // n if n else 0
        supplied = n * c.q_labor_per_worker
        s.macro["unemployment_bps"] = (expired_labor * 10000) // supplied if supplied else 0
        food_pid = f"{s.food}/{s.cur}"
        s.macro["cpi"] = s.last_price[food_pid] * 10000 // c.food_ref_price  # genesis = 10000

    def run(self, n_turns: int) -> list[str]:
        return [self._step_hash() for _ in range(n_turns)]

    def _step_hash(self) -> str:
        self.run_turn()
        return state_hash(self.s)

    # ---- phases ----
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

    def _produce_all(self) -> None:
        s, c = self.s, self.c
        for fid in sorted(s.firms):
            fs = s.firms[fid]
            r = fs.recipe
            # (1) capacity expansion: consume construction labor bought this turn
            if fs.expands and fs.capacity < c.capacity_max:
                bh = s.qty(fid, s.build)
                if bh > 0:
                    dcap = (c.expand_g * bh) // (1 + fs.capacity // c.expand_k)
                    s.ledger.post(s.tick, TurnPhase.P5, Cause.PRODUCTION, [LedgerLine(fid, s.build, -bh)])
                    fs.capacity = min(c.capacity_max, fs.capacity + dcap)
            # (2) production: runs bounded by capacity, inputs, region cap (Leontief)
            runs = fs.capacity
            for inp, q in r.inputs.items():
                runs = min(runs, s.qty(fid, inp) // q)
            if r.region_capped_output is not None:
                outq = r.outputs[r.region_capped_output]
                runs = min(runs, s.region_cap.get(r.region_capped_output, 0) // outq)
            if runs > 0:
                lines = [LedgerLine(fid, inp, -runs * q) for inp, q in r.inputs.items()]
                lines += [LedgerLine(fid, outp, runs * q) for outp, q in r.outputs.items()]
                s.ledger.post(s.tick, TurnPhase.P5, Cause.PRODUCTION, lines)
            # (3) depreciation
            fs.capacity = max(c.capacity_min, (fs.capacity * (10000 - c.depreciation_bps)) // 10000)

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

    def _govern(self) -> None:
        """P3 GOVERN: aggregate per-politician proposals into confirmed policy (doc 12 12.2).

        Proposals are deterministic and spread across politicians so the SCALAR
        aggregation (mean -> clamp -> tick) is exercised end to end.
        """
        s, c = self.s, self.c
        pols = s.politicians
        if not pols:
            return
        n = len(pols)
        w = [1] * n
        tax_vals = [c.consumption_tax_bps - 100 + 100 * i for i in range(n)]
        wel_vals = [2000 + 500 * i for i in range(n)]
        s.policy["tax_bps"] = aggregate_scalar(tax_vals, w, c.tax_lo, c.tax_hi, c.tax_tick)
        s.policy["welfare_bps"] = aggregate_scalar(wel_vals, w, c.welfare_lo, c.welfare_hi, c.welfare_tick)

    def _tax(self, spend: dict) -> None:
        s = self.s
        rate = s.policy.get("tax_bps", self.c.consumption_tax_bps)
        tlines: list[LedgerLine] = []
        for a in sorted(spend, key=str):
            tax = min(fixed.apply_bps_floor(spend[a], rate), s.cash(a))
            if tax > 0:
                tlines.append(LedgerLine(a, s.cur, -tax))
                tlines.append(LedgerLine(s.gov, s.cur, tax))
        if tlines:
            s.ledger.post(s.tick, TurnPhase.P7, Cause.TAX, tlines)

    def _welfare(self) -> None:
        s, c = self.s, self.c
        pay = fixed.apply_bps_floor(c.welfare_base, s.policy.get("welfare_bps", 0))
        if pay <= 0:
            return
        remaining = s.cash(s.gov)
        lines: list[LedgerLine] = []
        for a in s.agents:
            if s.cash(a) < c.welfare_threshold and remaining >= pay:
                lines.append(LedgerLine(s.gov, s.cur, -pay))
                lines.append(LedgerLine(a, s.cur, pay))
                remaining -= pay
        if lines:
            s.ledger.post(s.tick, TurnPhase.P7, Cause.SUBSIDY, lines)

    def _holders(self, asset: AssetId) -> list[EntityId]:
        bals = self.s.ledger.balances()
        return sorted((e for e, row in bals.items() if row.get(asset, 0) > 0), key=str)

    def _finance(self) -> None:
        """P7 protocol transfers: coupons, dividends (quarterly) and redemptions (doc 11)."""
        s = self.s
        tick = s.tick
        if self.cal.is_quarter_end(tick):
            for b in s.bonds:
                for e in self._holders(b.asset):
                    cpn = min(fixed.coupon_quarterly(s.qty(e, b.asset), b.face, b.coupon_bps),
                              s.cash(b.issuer))
                    if cpn > 0:
                        s.ledger.post(tick, TurnPhase.P7, Cause.COUPON,
                                      [LedgerLine(b.issuer, s.cur, -cpn), LedgerLine(e, s.cur, cpn)])
            for eq in s.equities:
                div_ps = (eq.par * eq.dividend_bps) // (10000 * 4)   # floor, quarterly (doc 00 0.20)
                for e in self._holders(eq.asset):
                    amt = min(div_ps * s.qty(e, eq.asset), s.cash(eq.firm))
                    if amt > 0:
                        s.ledger.post(tick, TurnPhase.P7, Cause.DIVIDEND,
                                      [LedgerLine(eq.firm, s.cur, -amt), LedgerLine(e, s.cur, amt)])
        for b in s.bonds:
            if tick == b.maturity_tick:
                for e in self._holders(b.asset):
                    qty = s.qty(e, b.asset)
                    pay = min(qty * b.face, s.cash(b.issuer))
                    lines = [LedgerLine(e, b.asset, -qty)]            # burn the matured bond
                    if pay > 0:
                        lines += [LedgerLine(b.issuer, s.cur, -pay), LedgerLine(e, s.cur, pay)]
                    s.ledger.post(tick, TurnPhase.P7, Cause.REDEEM, lines)

    def _expire_perishables(self) -> int:
        """Burn unused perishable labor at P9; return the total expired (doc 08 8.9.4)."""
        s = self.s
        labor_assets = s.labor_assets()
        lines: list[LedgerLine] = []
        expired = 0
        for e, row in s.ledger.balances().items():
            for a, q in row.items():
                if a in labor_assets and q > 0:
                    lines.append(LedgerLine(e, a, -q))
                    expired += q
        if lines:
            s.ledger.post(s.tick, TurnPhase.P9, Cause.EXPIRE, lines)
        return expired


def run_skeleton(config: SkeletonConfig, n_turns: int) -> tuple[StateStore, list[str]]:
    store = genesis(config)
    engine = SkeletonEngine(store, config)
    return store, engine.run(n_turns)
