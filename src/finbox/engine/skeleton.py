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
from dataclasses import replace

from ..agents.scripted import generate_orders
from ..core import fixed
from ..core.enums import (
    Cause, FirmLifecycle, OrderType, Side, TIF, TradeMode, TurnPhase, is_perishable)
from ..core.ids import AssetId, EntityId
from ..core.rng import STREAM_DEMOGRAPHY, rng as derive_rng
from ..core.time import Calendar
from ..domain import needs

MIGRATE_PCT = 5    # per-turn migration probability when a strictly better cell exists (doc 04 4.6.1)
from ..init.config import SkeletonConfig
from ..init.genesis import genesis
from ..ledger import LedgerLine
from ..market.types import Order, TradingPair
from ..politics import aggregate_scalar
from ..state import StateStore, state_hash
from .margin import MarginEngine


class SkeletonEngine:
    def __init__(self, store: StateStore, config: SkeletonConfig) -> None:
        self.s = store
        self.c = config
        self.cal = Calendar()
        self.margin = MarginEngine(self)   # 信用取引: lending, positions, forced liquidation (doc 09)
        self._next_player = 0          # per-room PLAYER numbering from 0 (doc 13 13.3.2)

    def onboard_player(self, endowment: int) -> EntityId:
        """Engine-owned onboarding: assign a PLAYER id and post the genesis endowment (doc 13 13.3.1).

        The engine is the single writer of the ledger (doc 02 2.1); the gateway delegates here
        rather than posting to the ledger itself.
        """
        ent = EntityId.player(self._next_player)
        self._next_player += 1
        self.s.ledger.post(self.s.tick, TurnPhase.INIT, Cause.GENESIS,
                           [LedgerLine(ent, self.s.cur, endowment)])
        return ent

    def run_turn(self, external_protos=None) -> None:
        s, c = self.s, self.c
        tick = s.tick

        # P1: workers produce (mint) their perishable labor via the skill/stamina model (doc 05 5.3)
        labor_supplied = needs.mint_labor(s, c)

        # P1/P2: assemble orders from carried resting GTC/GTT, scripted intent, and external
        # (player/agent) submissions; assign deterministic submit_seq; validate+clamp with
        # per-entity cash/inventory reservation so orders cannot double-spend (doc 09 9.4.2/9.5)
        protos = generate_orders(s, c)
        if external_protos:
            protos = protos + list(external_protos)
        protos.sort(key=lambda p: (str(p.entity), p.pair.pair_id, p.side.value, p.intent))
        spot_protos = [p for p in protos if p.trade_mode is TradeMode.SPOT]
        margin_protos = [p for p in protos if p.trade_mode is TradeMode.MARGIN]

        # Action Log: append this tick's collected pre-validation intents, tagged with entity_id
        # (doc 02 2.6.1); the basis for action-log replay verification (doc 02 2.6.2)
        s.action_log.append({"tick": tick, "intents": [
            {"entity": str(p.entity), "kind": "ORDER", "pair": p.pair.pair_id,
             "side": p.side.value, "qty": p.qty, "mode": p.trade_mode.value} for p in protos]})

        orders_by_pair: dict[str, list[Order]] = defaultdict(list)
        reserved_cash: dict = defaultdict(int)
        reserved_sell: dict = defaultdict(int)
        live_orders: list[Order] = []

        # (a) carried resting orders first: older => higher time priority (doc 09 9.6.3)
        for ro in s.resting_orders:
            pair = s.pairs.get(ro.pair_id)
            if pair is None:
                continue
            q = self._reserve(ro.entity_id, pair, ro.side, ro.limit_price, ro.qty,
                              reserved_cash, reserved_sell)
            if q <= 0:
                continue   # P2 invalidation: balance gone -> drop from book (doc 09 9.4.2)
            vis = min(ro.qty_visible, q) if ro.qty_visible is not None else None
            o = replace(ro, qty=q, qty_visible=vis)
            orders_by_pair[pair.pair_id].append(o)
            live_orders.append(o)

        # (b) fresh spot orders this turn (submit_seq = tick-scoped key so carried < fresh)
        seq = 0
        for p in spot_protos:
            pair = p.pair
            q = self._reserve(p.entity, pair, p.side, p.limit_price, p.qty,
                              reserved_cash, reserved_sell)
            if q <= 0:
                continue
            vis = min(p.qty_visible, q) if (c.iceberg_enabled and p.qty_visible is not None) else None
            o = Order(order_id=f"ORD:{tick}:{seq:04d}", entity_id=p.entity, pair_id=pair.pair_id,
                      side=p.side, order_type=p.order_type, limit_price=p.limit_price, qty=q,
                      submit_seq=tick * 1_000_000 + seq, tif=p.tif, expires_tick=p.expires_tick,
                      qty_visible=vis)
            orders_by_pair[pair.pair_id].append(o)
            live_orders.append(o)
            seq += 1

        self._govern()            # P3 GOVERN: aggregate politician proposals into policy

        # P4-pre (doc 03 §3.3.5 / doc 09 §プール操作の順序): confirm lending-pool deposits/withdrawals
        # at the top of P4, strictly after P3 GOVERN and before board-clearing.
        self.margin.process_pool_ops()

        # margin opens (信用取引): borrow from lending pools and inject the opening board orders so
        # they clear on the same board as spot (doc 09 §信用取引), reserved against margin + borrow
        for o in self.margin.open_orders(margin_protos, reserved_cash, reserved_sell, tick):
            orders_by_pair[o.pair_id].append(o)
            live_orders.append(o)

        # AMM passive ladder (doc 09 9.7): deterministic per-pair liquidity from pool reserves
        for o in self.margin.amm_orders(tick):
            orders_by_pair[o.pair_id].append(o)

        # P4 CLEAR all pairs
        turnover = 0
        food_spend: dict = {}
        filled: dict[str, int] = {}
        for pair in s.sorted_pairs():
            t, spend, fills = self._clear_and_settle(pair, orders_by_pair.get(pair.pair_id, []))
            turnover += t
            for oid, fq in fills:
                filled[oid] = filled.get(oid, 0) + fq
            if pair.base == s.food:
                food_spend = spend
        self.margin.sync_amm_reserves()   # re-read AMM reserves after trading (doc 09 9.7)
        self._roll_resting_book(live_orders, filled)   # GTC/GTT carry, GFT/IOC/FOK drop (doc 09 9.6.5)

        self._produce_all()       # P5
        needs.consume(s, c)       # P6 CONSUME: needs update, multi-food, skill growth, death (doc 05)
        self._migrate()           # P6 CONSUME: residency / migration (doc 04 4.6.1)
        # P7 protocol-transfer order (doc 03 3.7): taxation -> coupon/redemption -> dividend -> subsidy
        self._tax(food_spend)     # P7 taxation (policy-driven rate)
        self._finance()           # P7 coupons -> redemptions -> dividends
        self.margin.accrue_interest()   # P7 margin borrow interest -> pool + insurance (doc 09 §利息の発生)
        self._welfare()           # P7 subsidy / welfare transfers to low-cash agents
        self._liquidate_insolvent()  # P7 insolvency -> liquidation (doc 10.8.5)
        expired = self._expire_perishables()  # P9
        self._finalize_macro(turnover, expired, labor_supplied)
        s.tick += 1

    def _finalize_macro(self, turnover: int, expired_labor: int, labor_supplied: int) -> None:
        """P9: confirm macro indicators / KPIs (doc 00 0.16)."""
        s, c = self.s, self.c
        s.macro["gdp"] = turnover
        s.macro["policy_rate"] = s.cb_policy_rate_bps
        if s.investors:
            s.macro["investor_nav"] = s.net_worth(s.investors[0])
        alive = [a for a in s.agents if a not in s.deceased]
        n = len(alive)
        # avg_satiety as a 0..100 KPI (needs are held x1000 internally, doc 05 5.2)
        s.macro["avg_satiety"] = sum(s.satiety[a] for a in alive) // (n * needs.SCALE) if n else 0
        s.macro["population"] = n
        s.macro["unemployment_bps"] = (expired_labor * 10000) // labor_supplied if labor_supplied else 0
        food_pid = f"{s.food}/{s.cur}"
        s.macro["cpi"] = s.last_price[food_pid] * 10000 // c.food_ref_price  # genesis = 10000

    def run(self, n_turns: int) -> list[str]:
        return [self._step_hash() for _ in range(n_turns)]

    def _step_hash(self) -> str:
        self.run_turn()
        return state_hash(self.s)

    # ---- market helpers ----
    def _reserve(self, entity: EntityId, pair: TradingPair, side: Side,
                 limit_price: int | None, requested: int, rcash: dict, rsell: dict) -> int:
        """Validate+clamp one order against current balances (doc 09 9.5); return fillable qty.

        There are no trading fees and no price-band clamps (both removed): a BUY simply reserves
        ``price × qty`` of quote; a market BUY reserves at the last price (no band ceiling).
        """
        s = self.s
        if side is Side.BUY:
            if limit_price is None:
                rprice = max(1, s.last_price[pair.pair_id])    # market buy: reserve at last price
            else:
                if limit_price <= 0:
                    return 0
                rprice = limit_price
            avail = s.ledger.get(entity, pair.quote) - rcash[entity]
            q = min(requested, avail // rprice) if rprice > 0 else 0
            if q <= 0:
                return 0
            rcash[entity] += rprice * q
            return q
        key = (entity, pair.base)
        q = min(requested, s.ledger.get(entity, pair.base) - rsell[key])
        if q <= 0:
            return 0
        rsell[key] += q
        return q

    def _roll_resting_book(self, live_orders: list[Order], filled: dict[str, int]) -> None:
        """Rebuild the GTC/GTT resting book after P4: carry unfilled remainders, drop the rest.

        GFT and IOC/FOK never rest; GTT expires once tick >= expires_tick (P9) (doc 09 9.4/9.6.5).
        """
        tick = self.s.tick
        new_resting: list[Order] = []
        for o in live_orders:
            if o.tif is TIF.GFT or o.order_type in (OrderType.IOC, OrderType.FOK):
                continue
            if o.tif is TIF.GTT and o.expires_tick is not None and tick >= o.expires_tick:
                continue
            remainder = o.qty - filled.get(o.order_id, 0)
            if remainder > 0:
                vis = min(o.qty_visible, remainder) if o.qty_visible is not None else None
                new_resting.append(replace(o, qty=remainder, qty_visible=vis))
        self.s.resting_orders = new_resting

    # ---- phases ----
    def _clear_and_settle(self, pair: TradingPair, orders: list[Order]) -> tuple[int, dict, list]:
        """P4: clear one pair (no fees, no price band) with forced-liquidation re-auction, then
        settle by double-entry (doc 09 9.3/9.6.4/§強制決済). Delegated to the margin engine."""
        return self.margin.clear_and_settle(pair, orders)

    def _produce_all(self) -> None:
        """P5 PRODUCE: Leontief production, then capacity expansion, then depreciation (doc 10.8.2)."""
        s, c = self.s, self.c
        scale = c.recipe_yield_scale

        # (1) region-cap-free desired runs per firm (capacity / labor / inputs) (doc 10.3)
        desired: dict = {}
        for fid in sorted(s.firms):
            fs = s.firms[fid]
            r = fs.recipe
            if fs.state is FirmLifecycle.LIQUIDATING:
                desired[fid] = 0
                continue
            runs = fs.capacity // r.capacity_cost
            for inp, q in r.inputs.items():
                runs = min(runs, s.qty(fid, inp) // q)
            desired[fid] = max(0, runs)

        # (2) proportional region-cap allocation per (capped asset, region) (doc 10.6)
        region_runs = dict(desired)
        groups: dict = defaultdict(list)
        for fid in sorted(s.firms):
            r = s.firms[fid].recipe
            if r.region_capped_output is not None:
                groups[(r.region_capped_output, s.firms[fid].region_id)].append(fid)
        for (asset, region), fids in groups.items():
            cap = s.region_cap_for(asset, region)
            opr = {fid: s.firms[fid].recipe.outputs[asset] * scale for fid in fids}   # output units / run
            demand = {fid: desired[fid] * opr[fid] for fid in fids}                   # output units
            total = sum(demand.values())
            if total <= cap:
                share = demand
            else:
                share = {fid: (cap * demand[fid]) // total for fid in fids}
                order = sorted(fids, key=lambda f: (-demand[f], str(f)))
                for i in range(cap - sum(share.values())):     # remainder 1-by-1 (doc 10.6)
                    share[order[i]] += 1
            for fid in fids:
                region_runs[fid] = min(desired[fid], share[fid] // opr[fid] if opr[fid] else 0)

        # (3) produce, then expand, then depreciate (doc 10.8.2 order)
        for fid in sorted(s.firms):
            fs = s.firms[fid]
            r = fs.recipe
            runs = region_runs[fid]
            if runs > 0:
                lines = [LedgerLine(fid, inp, -runs * q) for inp, q in r.inputs.items()]
                lines += [LedgerLine(fid, outp, runs * q * scale) for outp, q in r.outputs.items()]
                s.ledger.post(s.tick, TurnPhase.P5, Cause.PRODUCTION, lines)
            cap_max = c.capacity_max_for(fs.industry)
            if fs.expands and fs.capacity < cap_max:               # capacity expansion (doc 10.7)
                # consume up to the planned expansion amount; the rest (e.g. a builder's own
                # output) stays as sellable inventory rather than being cannibalized
                bh = min(s.qty(fid, s.build), c.firm_expand_buy)
                if bh > 0:
                    dcap = (c.expand_g * bh) // (1 + fs.capacity // c.expand_k)
                    s.ledger.post(s.tick, TurnPhase.P5, Cause.PRODUCTION, [LedgerLine(fid, s.build, -bh)])
                    fs.capacity = min(cap_max, fs.capacity + dcap)
            # depreciation: pure exponential decay, no floor (doc 10.7 "放置した設備は朽ちる")
            fs.capacity = (fs.capacity * (10000 - c.depreciation_bps)) // 10000

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
        self._apply_submitted_votes()

    def _apply_submitted_votes(self) -> None:
        """Aggregate submitted PolicyVotes (doc 14 14.5.6) into confirmed policy levers (doc 12 12.2)."""
        s, c = self.s, self.c
        cc = s.gov.country.value if s.gov.country else None
        levers = s.pending_votes.pop(cc, {}) if cc else {}
        # SCALAR levers: weighted mean -> clamp -> round to tick (doc 12 12.2.1)
        if levers.get("tax_consumption"):
            vals = levers["tax_consumption"]
            s.policy["tax_bps"] = aggregate_scalar(vals, [1] * len(vals), c.tax_lo, c.tax_hi, c.tax_tick)
        if levers.get("welfare_level"):
            vals = levers["welfare_level"]
            s.policy["welfare_bps"] = aggregate_scalar(vals, [1] * len(vals), c.welfare_lo, c.welfare_hi, c.welfare_tick)
        if levers.get("min_wage"):
            vals = levers["min_wage"]
            s.policy["min_wage"] = aggregate_scalar(vals, [1] * len(vals), 0, 1_000_000, 1)
        if levers.get("policy_rate"):
            vals = levers["policy_rate"]
            # canonical SCALAR range [POLICY_RATE_MIN, POLICY_RATE_MAX] = [-100, 4000] bps, tick 25
            # (doc 11 §11.10, doc 12 §12.3); the floor is negative so the documented negative rates pass.
            s.cb_policy_rate_bps = aggregate_scalar(vals, [1] * len(vals),
                                                    c.policy_rate_min_bps, c.policy_rate_max_bps,
                                                    c.policy_rate_tick_bps)

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
            if a in s.deceased:              # DECEASED agents are inert: no welfare transfers (doc 05 5.4.1)
                continue
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
        """P7 protocol transfers at quarter boundaries: coupon -> redemption -> dividend (doc 03 3.7, doc 11)."""
        s = self.s
        tick = s.tick
        if not self.cal.is_quarter_end(tick):
            return
        # (1) coupons (doc 11.4.3)
        for b in s.bonds:
            for e in self._holders(b.asset_id):
                cpn = min(fixed.coupon_quarterly(s.qty(e, b.asset_id), b.face, b.coupon_bps),
                          s.cash(b.issuer))
                if cpn > 0:
                    s.ledger.post(tick, TurnPhase.P7, Cause.COUPON,
                                  [LedgerLine(b.issuer, s.cur, -cpn), LedgerLine(e, s.cur, cpn)])
        # (2) principal redemption of matured bonds (quarter-end gated, doc 03 table 3.5)
        for b in s.bonds:
            if tick == b.maturity_tick:
                for e in self._holders(b.asset_id):
                    qty = s.qty(e, b.asset_id)
                    pay = min(qty * b.face, s.cash(b.issuer))
                    lines = [LedgerLine(e, b.asset_id, -qty)]            # burn the matured bond
                    if pay > 0:
                        lines += [LedgerLine(b.issuer, s.cur, -pay), LedgerLine(e, s.cur, pay)]
                    s.ledger.post(tick, TurnPhase.P7, Cause.REDEEM, lines)
        # (3) dividends (doc 11.6.2): profit distribution, not a fixed par-rate
        # dividend_per_share = floor(distributable_profit * payout_ratio / shares_outstanding)
        for eq in s.equities:
            shares = eq.shares_outstanding
            if shares <= 0:
                continue
            distributable = fixed.apply_bps_floor(s.distributable_profit(eq.firm_id), eq.dividend_policy_bps)
            div_ps = distributable // shares          # floor; truncated remainder retained by firm
            if div_ps <= 0:
                continue
            for e in self._holders(eq.asset_id):
                amt = min(div_ps * s.qty(e, eq.asset_id), s.cash(eq.firm_id))
                if amt > 0:
                    s.ledger.post(tick, TurnPhase.P7, Cause.DIVIDEND,
                                  [LedgerLine(eq.firm_id, s.cur, -amt), LedgerLine(e, s.cur, amt)])

    def _liquidate_insolvent(self) -> None:
        """P7: a firm that can neither produce (capacity 0) nor pay (cash 0) is liquidated (doc 10.8.5)."""
        s = self.s
        for fid in sorted(s.firms):
            fs = s.firms[fid]
            if fs.state is FirmLifecycle.LIQUIDATING:
                continue
            if fs.capacity <= 0 and s.cash(fid) <= 0:
                self._liquidate(fid)

    def _liquidate(self, fid: EntityId) -> None:
        """Distribute residual firm cash to shareholders pro-rata, then burn all EQ (doc 10.8.5)."""
        s = self.s
        residual = s.cash(fid)
        for eq in s.equities:
            if eq.firm_id != fid:
                continue
            holders = [(e, s.qty(e, eq.asset_id)) for e in self._holders(eq.asset_id)]
            total = sum(q for _, q in holders)
            lines: list[LedgerLine] = []
            if total > 0 and residual > 0:                       # residual distribution (largest-remainder)
                alloc = fixed.largest_remainder(residual, [q for _, q in holders])
                for (e, _), a in zip(holders, alloc):
                    if a > 0:
                        lines.append(LedgerLine(fid, s.cur, -a))
                        lines.append(LedgerLine(e, s.cur, a))
                residual = 0
            for e, q in holders:                                 # burn the equity (doc 00 0.5.1)
                if q > 0:
                    lines.append(LedgerLine(e, eq.asset_id, -q))
            if lines:
                s.ledger.post(s.tick, TurnPhase.P7, Cause.LIQUIDATION, lines)
        s.firms[fid].state = FirmLifecycle.LIQUIDATING

    def _migrate(self) -> None:
        """P6: agents may relocate within their home region toward a less-crowded cell (doc 04 4.6.1).

        Utility favours capacity headroom and low pollution; the move conserves total population
        (source -1 / dest +1) and keeps agents in the active region (where the labor market is).
        """
        s = self.s
        if not s.cells:
            return
        by_region: dict = defaultdict(list)
        for c in s.cells.values():
            if not c.terrain_locked:
                by_region[str(c.region_id)].append(c)
        for a in s.agents:
            if a in s.deceased or a not in s.home_cell:
                continue
            cur = s.cells.get(s.home_cell[a])
            if cur is None:
                continue
            region_cells = by_region.get(str(cur.region_id), [])
            if len(region_cells) < 2:
                continue
            g = derive_rng(s.master_seed, s.tick, STREAM_DEMOGRAPHY, str(a), "migrate")
            cand = region_cells[int(g.integers(0, len(region_cells)))]
            if cand.cell_id == cur.cell_id:
                continue
            # U(dest) - U(home): capacity headroom minus pollution (doc 04 4.6.1, slice signals)
            u_cur = (cur.population_capacity - cur.base_population) - cur.pollution
            u_cand = (cand.population_capacity - cand.base_population) - cand.pollution
            if u_cand > u_cur and int(g.integers(0, 100)) < MIGRATE_PCT:
                cur.base_population = max(0, cur.base_population - 1)
                cand.base_population += 1
                s.home_cell[a] = cand.cell_id

    def _expire_perishables(self) -> int:
        """Burn unused perishables (labor.*, svc.*, energy.electricity) at P9 (doc 08 8.9.4)."""
        s = self.s
        lines: list[LedgerLine] = []
        expired = 0
        for e, row in s.ledger.balances().items():
            for a, q in row.items():
                if q > 0 and is_perishable(a):
                    lines.append(LedgerLine(e, a, -q))
                    expired += q
        if lines:
            s.ledger.post(s.tick, TurnPhase.P9, Cause.EXPIRE, lines)
        return expired


def run_skeleton(config: SkeletonConfig, n_turns: int) -> tuple[StateStore, list[str]]:
    store = genesis(config)
    engine = SkeletonEngine(store, config)
    return store, engine.run(n_turns)
