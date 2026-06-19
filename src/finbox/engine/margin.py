"""Margin / lending engine: borrow, clear, forced-liquidate, accrue interest (doc 09 信用取引).

This holds every margin-specific step of the P4 CLEAR / P7 FISCAL pipeline so the core
SkeletonEngine stays focused on the spot economy. It is created with a back-reference to the
SkeletonEngine and shares its StateStore. Every transfer is a conserving double-entry posting:
the lending pool never lends more than it holds, borrowers are over-collateralised at the initial
margin, and bad debt is absorbed by insurance then supplier haircut — assets are never minted
(doc 00 0.10/0.17, doc 08 8.8).
"""
from __future__ import annotations

from ..core import fixed
from ..core.enums import (
    AMMInvariant, Cause, MarketKind, OrderType, PositionSide, Side, TIF, TurnPhase,
    is_margin_eligible_base)
from ..core.ids import EntityId
from ..domain.margin import Position, maintenance_margin_bps
from ..ledger import LedgerLine
from ..market import clear
from ..market.types import Order


class MarginEngine:
    def __init__(self, engine) -> None:
        self.e = engine
        self.opens: dict[str, dict] = {}     # order_id -> open meta for the current turn

    @property
    def s(self):
        return self.e.s

    @property
    def c(self):
        return self.e.c

    # ---- helpers ----
    def _post(self, cause: Cause, lines: list[LedgerLine], phase: TurnPhase = TurnPhase.P4,
              ref: str | None = None):
        if lines:
            self.s.ledger.post(self.s.tick, phase, cause, lines, cause_ref=ref)

    def _base_rate(self, pool) -> int:
        """Currency pools track the policy rate; asset pools use the config base rate (doc 09/11)."""
        if pool.asset == self.s.cur:
            return self.s.cb_policy_rate_bps
        return self.c.lending_asset_base_rate_bps

    def _borrow_rate(self, pool) -> int:
        c = self.c
        return pool.borrow_rate(self._base_rate(pool), c.lending_slope1_bps,
                                c.lending_slope2_bps, c.lending_u_kink_bps)

    def _insf(self) -> EntityId:
        return EntityId.insurance_fund("ALD")

    def locked_quote(self, entity: EntityId) -> int:
        """Quote (CUR) collateral encumbered by the entity's SHORT positions (doc 09 §証拠金)."""
        return sum(p.collateral_qty for p in self.s.positions
                   if p.entity == entity and p.collateral_asset == self.s.cur)

    def locked_base(self, entity: EntityId, base) -> int:
        """Base units held as collateral by the entity's LONG positions on ``base``."""
        return sum(p.collateral_qty for p in self.s.positions
                   if p.entity == entity and p.side is PositionSide.LONG
                   and p.pair_id.split("/", 1)[0] == str(base))

    # ---- pool / AMM operations (confirmed before P4 board-clearing, doc 09 §プール操作の順序) ----
    def process_pool_ops(self) -> None:
        for op in self.s.pending_pool_ops:
            kind, entity, asset, qty = op["kind"], op["entity"], op["asset"], op["qty"]
            if kind == "SUPPLY":
                self.pool_supply(entity, asset, qty)
            elif kind == "WITHDRAW":
                self.pool_withdraw(entity, asset, qty)
        self.s.pending_pool_ops = []

    def pool_supply(self, entity: EntityId, asset, qty: int) -> int:
        """Deposit ``qty`` of ``asset`` into its lending pool; mint pro-rata shares (doc 09 §供給と引出)."""
        s = self.s
        pool = s.lending_pools.get(str(asset))
        if pool is None or qty <= 0 or s.ledger.get(entity, asset) < qty:
            return 0
        pe = pool.entity_id
        if pool.total_shares <= 0 or s.pool_value(pool) <= 0:
            minted = qty
        else:
            minted = qty * pool.total_shares // s.pool_value(pool)
        self._post(Cause.POOL_SUPPLY, [LedgerLine(entity, asset, -qty), LedgerLine(pe, asset, qty)])
        pool.supplied += qty
        pool.total_shares += minted
        pool.shares[entity] = pool.shares.get(entity, 0) + minted
        return minted

    def pool_withdraw(self, entity: EntityId, asset, shares: int) -> int:
        """Redeem ``shares`` for the underlying, capped at the pool's available balance (doc 09 §供給と引出)."""
        s = self.s
        pool = s.lending_pools.get(str(asset))
        if pool is None or shares <= 0:
            return 0
        shares = min(shares, pool.shares.get(entity, 0))
        if shares <= 0 or pool.total_shares <= 0:
            return 0
        pe = pool.entity_id
        want = s.pool_value(pool) * shares // pool.total_shares
        # only honour up to what is physically present in the pool (doc 09 §借入上限=利用可能残高)
        # the asset withdrawn is the pool asset; interest retained in CUR is realised separately
        avail = s.ledger.get(pe, asset)
        give = min(want, avail) if asset == s.cur else min(want, avail)
        if give <= 0:
            return 0
        self._post(Cause.POOL_WITHDRAW, [LedgerLine(pe, asset, -give), LedgerLine(entity, asset, give)])
        pool.supplied = max(0, pool.supplied - give)
        pool.total_shares -= shares
        pool.shares[entity] -= shares
        if pool.shares[entity] <= 0:
            pool.shares.pop(entity, None)
        return give

    # ---- opening positions (LOAN + board order) ----
    def open_orders(self, protos, rcash: dict, rsell: dict, tick: int) -> list[Order]:
        """Borrow from pools and build the board orders that open/close margin positions."""
        self.opens = {}
        out: list[Order] = []
        seq = 0
        for p in protos:
            order = self._open_one(p, rcash, rsell, tick, seq)
            if order is not None:
                out.append(order)
                seq += 1
        return out

    def _make_order(self, entity, pid, side, otype, price, qty, tick, seq) -> Order:
        return Order(order_id=f"MGN:{tick}:{seq:04d}", entity_id=entity, pair_id=pid, side=side,
                     order_type=otype, limit_price=(None if otype is OrderType.MARKET else price),
                     qty=qty, submit_seq=tick * 1_000_000 + 900_000 + seq, tif=TIF.GFT)

    def _open_one(self, proto, rcash, rsell, tick, seq) -> Order | None:
        s, c = self.s, self.c
        pair = proto.pair
        pid = pair.pair_id
        base, quote = pair.base, pair.quote
        if quote != s.cur or not is_margin_eligible_base(str(base)):
            return None
        if proto.intent == "CLOSE":
            return self._close_one(proto, rcash, rsell, tick, seq)
        side = proto.position_side or (
            PositionSide.LONG if proto.side is Side.BUY else PositionSide.SHORT)
        n = proto.qty
        p_ref = max(1, s.last_price[pid])
        im = c.initial_margin_bps
        free_quote = s.ledger.get(proto.entity, quote) - rcash[proto.entity] - self.locked_quote(proto.entity)
        if n <= 0 or free_quote <= 0:
            return None
        if side is PositionSide.LONG:
            pool = s.lending_pools.get(str(quote))
            if pool is None:
                return None
            avail = s.ledger.get(pool.entity_id, quote)
            margin = fixed.ceildiv(n * p_ref * im, fixed.BPS_DEN)
            if margin > free_quote:                       # clamp size to affordable margin
                n = (free_quote * fixed.BPS_DEN) // (p_ref * im) if p_ref * im > 0 else 0
                if n <= 0:
                    return None
                margin = fixed.ceildiv(n * p_ref * im, fixed.BPS_DEN)
            borrow = min(max(0, n * p_ref - margin), avail)
            n = min(n, (margin + borrow) // p_ref)        # fund-bound the deployable size
            if n <= 0:
                return None
            borrow = min(max(0, n * p_ref - margin), avail)
            if borrow > 0:
                self._post(Cause.LOAN, [LedgerLine(pool.entity_id, quote, -borrow),
                                        LedgerLine(proto.entity, quote, borrow)], ref="LOAN")
                pool.borrowed += borrow
            order = self._make_order(proto.entity, pid, Side.BUY, proto.order_type,
                                     proto.limit_price, n, tick, seq)
            rcash[proto.entity] += (proto.limit_price or p_ref) * n
            self.opens[order.order_id] = {"side": side, "entity": proto.entity, "pid": pid,
                                          "borrowed_asset": quote, "borrowed_qty": borrow,
                                          "margin": margin, "req_qty": n}
            return order
        # SHORT: borrow base from its pool and sell it
        pool = s.lending_pools.get(str(base))
        if pool is None:
            return None
        avail = s.ledger.get(pool.entity_id, base)
        n = min(n, avail)
        if n <= 0:
            return None
        margin = fixed.ceildiv(n * p_ref * im, fixed.BPS_DEN)
        if margin > free_quote:
            n = (free_quote * fixed.BPS_DEN) // (p_ref * im) if p_ref * im > 0 else 0
            n = min(n, avail)
            if n <= 0:
                return None
            margin = fixed.ceildiv(n * p_ref * im, fixed.BPS_DEN)
        self._post(Cause.LOAN, [LedgerLine(pool.entity_id, base, -n),
                                LedgerLine(proto.entity, base, n)], ref="LOAN")
        pool.borrowed += n
        order = self._make_order(proto.entity, pid, Side.SELL, proto.order_type,
                                 proto.limit_price, n, tick, seq)
        rsell[(proto.entity, base)] += n
        self.opens[order.order_id] = {"side": side, "entity": proto.entity, "pid": pid,
                                      "borrowed_asset": base, "borrowed_qty": n,
                                      "margin": margin, "req_qty": n}
        return order

    def _close_one(self, proto, rcash, rsell, tick, seq) -> Order | None:
        """A client-initiated close: trade the opposite side; repayment happens on fill."""
        s = self.s
        pos = next((p for p in s.positions if p.position_id == proto.position_id
                    and p.entity == proto.entity), None)
        if pos is None:
            return None
        pair = proto.pair
        base = pair.base
        qty = min(proto.qty, pos.qty)
        if qty <= 0:
            return None
        if pos.side is PositionSide.LONG:           # sell held base to unwind
            order = self._make_order(proto.entity, pair.pair_id, Side.SELL, OrderType.MARKET,
                                     None, qty, tick, seq)
            rsell[(proto.entity, base)] += qty
        else:                                       # buy base back to cover the short
            order = self._make_order(proto.entity, pair.pair_id, Side.BUY, OrderType.MARKET,
                                     None, qty, tick, seq)
            rcash[proto.entity] += max(1, s.last_price[pair.pair_id]) * qty
        self.opens[order.order_id] = {"close_position": pos.position_id, "entity": proto.entity,
                                      "pid": pair.pair_id}
        return order

    # ---- AMM passive liquidity (doc 09 9.7): a deterministic price-curve ladder ----
    def amm_orders(self, tick: int) -> list[Order]:
        """Quote each AMM pool as a BUY/SELL ladder around its reserve-ratio mid (doc 09 9.7).

        The embedded ``spread_bps`` is the 気配幅 (not a fee): takers fill at mid±slippage and the
        difference accrues to the reserves. Orders are bounded by reserves so the AMM never trades
        more than it holds (non-negative / conservation, doc 00 0.17).
        """
        s, c = self.s, self.c
        if not c.amm_enabled:
            return []
        out: list[Order] = []
        levels = max(1, c.amm_ladder_levels)
        seq = 0
        for pid in sorted(s.amm_pools):
            amm = s.amm_pools[pid]
            mid = amm.mid()
            if mid <= 0:
                continue
            base_slice = max(0, amm.r_base // (2 * levels))         # half the base reserve, laddered
            quote_slice = max(0, amm.r_quote // (2 * levels))
            k = amm.r_base * amm.r_quote                            # constant-product invariant x*y=k
            concentrated = amm.invariant is AMMInvariant.CONCENTRATED
            half = amm.spread_bps // 2
            for i in range(1, levels + 1):
                if concentrated:
                    # CONCENTRATED (doc 09 9.7.7): a tight band around mid (narrow per-level steps),
                    # liquidity concentrated near parity -- for low-vol pairs such as FX.
                    off = half + (i - 1) * max(1, half)
                    ask = mid + fixed.ceildiv(mid * off, fixed.BPS_DEN)
                    bid = max(1, mid - (mid * off) // fixed.BPS_DEN)
                else:
                    # CONST_PRODUCT (doc 09 9.7.7): the marginal price k/x^2 walks up/down the x*y=k
                    # curve as the pool sells/buys base, so price impact emerges from reserve depth
                    # (thinner pools and volatile EQ/COMM quote wider). Spread is added on top.
                    xa = max(1, amm.r_base - (i - 1) * base_slice)
                    xb = amm.r_base + (i - 1) * base_slice
                    ask = k // (xa * xa) + fixed.ceildiv(mid * half, fixed.BPS_DEN)
                    bid = max(1, k // (xb * xb) - (mid * half) // fixed.BPS_DEN)
                ask = max(ask, mid + 1)                             # strictly richer than mid
                if mid > 1:
                    bid = min(bid, mid - 1)                         # strictly cheaper than mid
                if base_slice > 0:
                    out.append(Order(order_id=f"AMM:{tick}:{seq:04d}", entity_id=amm.entity_id,
                                     pair_id=pid, side=Side.SELL, order_type=OrderType.LIMIT,
                                     limit_price=ask, qty=base_slice,
                                     submit_seq=tick * 1_000_000 + 800_000 + seq, tif=TIF.GFT))
                    seq += 1
                bq = quote_slice // bid
                if bq > 0:
                    out.append(Order(order_id=f"AMM:{tick}:{seq:04d}", entity_id=amm.entity_id,
                                     pair_id=pid, side=Side.BUY, order_type=OrderType.LIMIT,
                                     limit_price=bid, qty=bq,
                                     submit_seq=tick * 1_000_000 + 800_000 + seq, tif=TIF.GFT))
                    seq += 1
        return out

    def sync_amm_reserves(self) -> None:
        """Re-read each AMM pool's reserves from the ledger after clearing (doc 09 9.7)."""
        s = self.s
        for amm in s.amm_pools.values():
            amm.r_base = s.ledger.get(amm.entity_id, amm.base)
            amm.r_quote = s.ledger.get(amm.entity_id, amm.quote)

    # ---- per-pair clearing with forced-liquidation re-auction (doc 09 §強制決済) ----
    def clear_and_settle(self, pair, orders):
        s, c = self.s, self.c
        pid = pair.pair_id
        mw = s.policy.get("min_wage", 0) if pair.kind is MarketKind.LABOR else 0
        p_ref = s.last_price[pid]

        # preliminary clear (voluntary + margin-open board orders) -> p*_0
        p_star = clear(pid, orders, p_ref, min_wage=mw).p_star
        liq_close: dict[str, int] = {}     # position_id -> cumulative base units to force-close
        for _ in range(c.liquidation_max_rounds):
            changed = self._mark_and_schedule(pid, p_star, liq_close)
            if not changed:
                break
            liq_orders = self._liquidation_orders(pair, liq_close, p_star)
            p_star = clear(pid, orders + liq_orders, p_ref, min_wage=mw).p_star
        liq_orders = self._liquidation_orders(pair, liq_close, p_star)
        res = clear(pid, orders + liq_orders, p_ref, min_wage=mw)
        p = res.p_star

        fills_map = {f.order_id: f.qty for f in res.fills}
        spend, fills_out = self._settle(pair, res.fills, p)
        self._finalize_opens(pair, fills_map, p)
        self._apply_liquidations(pair, liq_close, fills_map, p)
        s.last_price[pid] = p
        return p * res.q_star, spend, fills_out

    def _settle(self, pair, fills, p):
        """Spot double-entry settlement of every fill — no fees (doc 09 9.6.4)."""
        s = self.s
        lines: list[LedgerLine] = []
        spend: dict = {}
        fills_out: list = []
        for f in fills:
            cash_amt = p * f.qty
            if f.side is Side.BUY:
                lines.append(LedgerLine(f.entity_id, pair.base, f.qty))
                lines.append(LedgerLine(f.entity_id, pair.quote, -cash_amt))
                spend[f.entity_id] = spend.get(f.entity_id, 0) + cash_amt
            else:
                lines.append(LedgerLine(f.entity_id, pair.base, -f.qty))
                lines.append(LedgerLine(f.entity_id, pair.quote, cash_amt))
            fills_out.append((f.order_id, f.qty))
        if lines:
            s.ledger.post(s.tick, TurnPhase.P4, Cause.TRADE, lines)
        return spend, fills_out

    def _mark_and_schedule(self, pid, p_star, liq_close) -> bool:
        """Mark all positions on the pair at ``p_star``; schedule additional close qty. (doc 09 §強制決済)."""
        s, c = self.s, self.c
        changed = False
        for pos in s.positions:
            if pos.pair_id != pid:
                continue
            base = pid.split("/", 1)[0]
            if base != str(pos.pair_id.split("/", 1)[0]):
                continue
            mark = p_star
            maint = maintenance_margin_bps(base, c.maint_margin_fx_bps,
                                           c.maint_margin_comm_bps, c.maint_margin_equity_bps)
            if pos.margin_ratio_bps(mark) >= maint:
                continue
            already = liq_close.get(pos.position_id, 0)
            remaining = pos.qty - already
            if remaining <= 0:
                continue
            want = self._close_qty(pos, mark, remaining)
            if want > 0:
                liq_close[pos.position_id] = already + want
                changed = True
        return changed

    def _close_qty(self, pos, mark, remaining) -> int:
        """Units to close this round: enough to restore initial margin, capped by close_factor."""
        c = self.c
        if mark <= 0:
            return remaining
        eq = pos.equity(mark)
        if eq <= 0:
            target = remaining                                  # underwater: close all remaining
        else:
            keep = eq * fixed.BPS_DEN // (c.initial_margin_bps * mark) if c.initial_margin_bps else 0
            target = max(0, pos.qty - keep)
            target = min(target, remaining)
        cap = max(1, fixed.ceildiv(remaining * c.close_factor_bps, fixed.BPS_DEN))
        return min(target, cap, remaining)

    def _liquidation_orders(self, pair, liq_close, mark) -> list[Order]:
        s = self.s
        targets = [p for p in s.positions
                   if p.pair_id == pair.pair_id and liq_close.get(p.position_id, 0) > 0]
        # most-underwater first, then entity_id, then position_id (deterministic, doc 09 §強制決済 step 2);
        # the resulting submit_seq order gives the worst positions liquidation time-priority on the board
        targets.sort(key=lambda p: (p.margin_ratio_bps(mark), str(p.entity), p.position_id))
        out: list[Order] = []
        for i, pos in enumerate(targets):
            side = Side.SELL if pos.side is PositionSide.LONG else Side.BUY     # involuntary close
            out.append(Order(order_id=f"LIQ:{pos.position_id}", entity_id=pos.entity,
                             pair_id=pair.pair_id, side=side, order_type=OrderType.MARKET,
                             limit_price=None, qty=liq_close[pos.position_id],
                             submit_seq=-1_000_000 + i, tif=TIF.GFT))
        return out

    # ---- finalize new positions and apply liquidation results ----
    def _finalize_opens(self, pair, fills_map, p):
        s = self.s
        base, quote = pair.base, pair.quote
        for oid, meta in self.opens.items():
            if meta.get("pid") != pair.pair_id:
                continue                            # finalize each open only on its own pair
            if "close_position" in meta:
                self._finalize_close(meta, fills_map.get(oid, 0), pair, p)
                continue
            filled = fills_map.get(oid, 0)
            side = meta["side"]
            pool = s.lending_pools.get(str(meta["borrowed_asset"]))
            if filled <= 0:                                 # nothing traded: unwind the borrow
                self._repay(pool, meta["entity"], meta["borrowed_asset"], meta["borrowed_qty"])
                continue
            if side is PositionSide.LONG:
                borrow = meta["borrowed_qty"]
                spent = filled * p
                surplus = max(0, meta["margin"] + borrow - spent)
                repay = min(borrow, surplus)
                self._repay(pool, meta["entity"], quote, repay)
                pos = Position(position_id=s.next_position_id(), entity=meta["entity"], pair_id=pair.pair_id,
                               side=side, qty=filled, entry_price=p, borrowed_asset=quote,
                               borrowed_qty=borrow - repay, collateral_asset=base, collateral_qty=filled,
                               open_tick=s.tick)
            else:
                borrowed = meta["borrowed_qty"]
                unsold = borrowed - filled
                self._repay(pool, meta["entity"], base, unsold)         # return any unsold base
                proceeds = filled * p
                margin = fixed.ceildiv(filled * p * self.c.initial_margin_bps, fixed.BPS_DEN)
                pos = Position(position_id=s.next_position_id(), entity=meta["entity"], pair_id=pair.pair_id,
                               side=side, qty=filled, entry_price=p, borrowed_asset=base,
                               borrowed_qty=filled, collateral_asset=quote,
                               collateral_qty=margin + proceeds, open_tick=s.tick)
            s.positions.append(pos)

    def _finalize_close(self, meta, filled, pair, p):
        pos = next((x for x in self.s.positions if x.position_id == meta["close_position"]), None)
        if pos is not None and filled > 0:
            self._reduce_position(pos, filled, p, penalty=False)

    def _apply_liquidations(self, pair, liq_close, fills_map, p):
        for pos in list(self.s.positions):
            want = liq_close.get(pos.position_id, 0)
            if want <= 0:
                continue
            filled = fills_map.get(f"LIQ:{pos.position_id}", 0)
            if filled > 0:
                self._reduce_position(pos, filled, p, penalty=True)

    def _reduce_position(self, pos, filled, p, penalty: bool):
        """Repay the freed leg, shrink the position, charge a liquidation penalty (doc 09 §強制決済)."""
        s, c = self.s, self.c
        pool = s.lending_pools.get(str(pos.borrowed_asset))
        quote = s.cur
        if pos.side is PositionSide.LONG:
            proceeds = filled * p                               # quote received from the SELL
            repay = min(pos.borrowed_qty, proceeds)
            self._repay(pool, pos.entity, quote, repay)
            pos.borrowed_qty -= repay
            pos.collateral_qty -= filled                        # base collateral consumed
        else:
            self._repay(pool, pos.entity, pos.borrowed_asset, filled)   # return bought-back base
            pos.borrowed_qty -= filled
            pos.collateral_qty = max(0, pos.collateral_qty - filled * p)  # quote collateral spent
        pos.qty -= filled
        if penalty and c.liquidation_penalty_bps > 0:
            pen = fixed.apply_bps_floor(filled * p, c.liquidation_penalty_bps)
            pen = min(pen, s.ledger.get(pos.entity, quote))
            if pen > 0:
                self._post(Cause.LIQUIDATION_PENALTY,
                           [LedgerLine(pos.entity, quote, -pen), LedgerLine(self._insf(), quote, pen)])
        if pos.qty <= 0:
            self._absorb_bad_debt(pos)
            s.positions.remove(pos)

    def _repay(self, pool, entity, asset, qty):
        if pool is None or qty <= 0:
            return
        qty = min(qty, self.s.ledger.get(entity, asset))
        if qty <= 0:
            return
        self._post(Cause.REPAY, [LedgerLine(entity, asset, -qty),
                                 LedgerLine(pool.entity_id, asset, qty)], ref="REPAY")
        pool.borrowed = max(0, pool.borrowed - qty)

    def _absorb_bad_debt(self, pos):
        """A fully-closed position that still owes is bad debt: insurance first, then supplier haircut."""
        s = self.s
        if pos.borrowed_qty <= 0:
            return
        pool = s.lending_pools.get(str(pos.borrowed_asset))
        base = pos.pair_id.split("/", 1)[0]
        mark = 1 if pos.borrowed_asset == s.cur else s.mark_price(base)
        shortfall_value = pos.borrowed_qty * mark + pos.accrued_interest
        insf = self._insf()
        cover = min(shortfall_value, s.ledger.get(insf, s.cur))
        if cover > 0:                                          # insurance fund covers the gap (in CUR)
            self._post(Cause.HAIRCUT, [LedgerLine(insf, s.cur, -cover),
                                       LedgerLine(pool.entity_id, s.cur, cover)], ref="HAIRCUT")
        if pool is not None:                                   # remaining gap = supplier haircut (claim write-down)
            pool.borrowed = max(0, pool.borrowed - pos.borrowed_qty)
            uncovered_units = max(0, (shortfall_value - cover)) // max(1, mark)
            pool.supplied = max(0, pool.supplied - uncovered_units)
        pos.borrowed_qty = 0
        pos.accrued_interest = 0

    # ---- P7 interest accrual (doc 09 §利息の発生, doc 11 11.7.1) ----
    def accrue_interest(self):
        s, c = self.s, self.c
        tpy = self.e.cal.turns_per_year
        insf = self._insf()
        for pos in s.positions:
            base = pos.pair_id.split("/", 1)[0]
            mark = s.mark_price(base)
            pool = s.lending_pools.get(str(pos.borrowed_asset))
            bval = pos.borrowed_value(mark)
            if pool is None or bval <= 0:
                continue
            rate = self._borrow_rate(pool)
            interest = fixed.interest_per_turn(bval, rate, tpy)
            if interest <= 0:
                continue
            pay = min(interest, s.ledger.get(pos.entity, s.cur))
            if pay > 0:
                ins_cut = fixed.apply_bps_floor(pay, c.lending_reserve_factor_bps)
                lines = [LedgerLine(pos.entity, s.cur, -pay)]
                if ins_cut > 0:
                    lines.append(LedgerLine(insf, s.cur, ins_cut))
                if pay - ins_cut > 0:
                    lines.append(LedgerLine(pool.entity_id, s.cur, pay - ins_cut))
                self._post(Cause.INTEREST, lines, phase=TurnPhase.P7, ref="INTEREST")
            pos.accrued_interest += interest - pay      # unpaid interest accrues (reduces equity)
