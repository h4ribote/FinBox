"""
FinBox parameter validation: combat curve + fixed-point, finance math,
money supply / M0 mint consistency.
Pure Python. All currency in MINOR units (minor_unit=1000).
"""
import math

LINE = "=" * 70


# ---------------------------------------------------------------- COMBAT
def combat():
    print(LINE); print("COMBAT  P_capture = ratio^k/(ratio^k+1), k=2, clamp<=0.95"); print(LINE)
    # proposed coefficients (doc 12 §12.5.4 currently undefined)
    mun_power, sol_atk, sol_def, fort_power = 10, 3, 4, 2
    P_MAX = 950  # x1000

    def p_capture_float(atk, dfn):
        r = atk / max(dfn, 1)
        return min(0.95, r**2 / (r**2 + 1))

    def p_capture_fp(atk, dfn):
        # integer fixed-point, scale 1000
        ratio = (atk * 1000) // max(dfn, 1)        # ratio x1000
        r2 = (ratio * ratio) // 1000               # ratio^2 x1000
        p = (r2 * 1000) // (r2 + 1000)             # x1000
        return min(P_MAX, p)

    print(f"  coeffs: mun_power={mun_power} sol_atk={sol_atk} sol_def={sol_def} fort_power={fort_power}")
    print(f"  {'ATK':>6} {'DEF':>6} {'ratio':>7} {'P_float':>9} {'P_fp/1000':>10} {'|err|':>7}")
    maxerr = 0.0
    for atk, dfn in [(50, 200), (100, 200), (200, 200), (300, 200), (400, 200), (600, 200), (1000, 200)]:
        pf = p_capture_float(atk, dfn)
        pi = p_capture_fp(atk, dfn) / 1000
        err = abs(pf - pi)
        maxerr = max(maxerr, err)
        print(f"  {atk:>6} {dfn:>6} {atk/max(dfn,1):>7.3f} {pf:>9.4f} {pi:>10.3f} {err:>7.4f}")
    print(f"  max |float-fixedpoint| error = {maxerr:.4f}  -> {'OK (<0.001)' if maxerr<0.001 else 'CHECK'}")
    # sanity: equal forces -> 0.5
    print(f"  sanity ATK==DEF -> {p_capture_float(200,200):.3f} (expect 0.500); 2x -> {p_capture_float(400,200):.3f} (expect 0.800)")


# ---------------------------------------------------------------- FINANCE
def finance():
    print("\n" + LINE); print("FINANCE  coupon / depreciation / growth / YTM"); print(LINE)
    TPY = 48
    # quarterly coupon floor (doc 11 §11.4.3): floor(q*face*bps/10000/4)
    face, bps = 1000, 350
    print(f"  quarterly coupon  face={face} coupon_bps={bps} (=3.5%/yr):")
    for q in (1, 10, 100, 1000):
        cpn = (q * face * bps) // (10000 * 4)
        annual = cpn * 4
        eff = annual / (q * face) if q * face else 0
        print(f"    q={q:>5}: coupon/quarter={cpn:>7}  annual={annual:>8}  effective_yield={eff*100:5.3f}% (nominal 3.500%)")
    print("    -> floor loss only material at tiny holdings; q>=100 hits nominal. OK")

    # depreciation 0.5%/turn -> annual (doc 10 §10.7 / doc 16)
    d = 0.005
    annual_dep = 1 - (1 - d) ** TPY
    print(f"  depreciation 0.5%/turn over 48 turns -> annual {annual_dep*100:.2f}% (doc says ~21.4%)  "
          f"{'OK' if abs(annual_dep-0.214)<0.005 else 'CHECK'}")

    # compound growth g_turn (doc 03 §3.2.2)
    for g in (0.10, 0.02):
        gt = (1 + g) ** (1 / TPY) - 1
        back = (1 + gt) ** TPY - 1
        print(f"  g_annual={g:.2%} -> g_turn={gt*100:.4f}%/turn -> recompounded={back*100:.2f}%  "
              f"{'OK' if abs(back-g)<1e-9 else 'CHECK'}")

    # YTM bisection (doc 11 §11.4.4): simple-discount PV, interval [-0.5, 5.0]
    def price_at_yield(y, face, cpn_q, quarters_to_mat):
        # coupon every 3 turns (quarter); t_k in turns; T = quarters*12 turns
        pv = 0.0
        for k in range(1, quarters_to_mat + 1):
            t = k * 12
            pv += cpn_q / (1 + y * (t / TPY))
        T = quarters_to_mat * 12
        pv += face / (1 + y * (T / TPY))
        return pv

    face, cpn_q, quarters = 1000, 9, 8   # 2-yr bond, ~3.6%/yr coupon
    target_price = 950  # trading below par -> positive yield
    lo, hi = -0.5, 5.0
    iters_to_tol, ytol = None, 1e-9
    for i in range(1, 201):
        mid = (lo + hi) / 2
        p = price_at_yield(mid, face, cpn_q, quarters)
        if p > target_price:   # price too high -> yield too low
            lo = mid
        else:
            hi = mid
        if iters_to_tol is None and abs(hi - lo) < ytol:
            iters_to_tol = i
    y64lo, y64hi = -0.5, 5.0
    for i in range(64):
        mid = (y64lo + y64hi) / 2
        if price_at_yield(mid, face, cpn_q, quarters) > target_price:
            y64lo = mid
        else:
            y64hi = mid
    y64 = (y64lo + y64hi) / 2
    print(f"  YTM bisection [-0.5,5.0]: tol<1e-9 reached at iter {iters_to_tol}; "
          f"y@64iters={y64*100:.4f}%/yr ({round(y64*10000)} bps)")
    print(f"    -> fixed 64 iterations gives interval width {(5.5)/2**64:.2e} (sub-bps). 64 iters OK")


# ---------------------------------------------------------------- MONEY / M0
def money():
    print("\n" + LINE); print("MONEY SUPPLY  genesis CUR:<home> endowment vs M0 mint formula"); print(LINE)
    # per doc 16 §16.7.1 counts (per country) and §16.7.2 cash (minor)
    cash = {
        "POLITICIAN": (7, 120000), "CENTRAL_BANKER": (1, 120000), "BUREAUCRAT": (2, 100000),
        "GENERAL": (1, 120000), "ENTREPRENEUR": (6, 2000000), "INVESTOR": (4, 1500000),
    }
    labor_count = 100 - (7 + 1 + 2 + 1 + 2 + 6 + 4)   # = 77
    cash["LABOR"] = (labor_count, 50000)
    mm_per_country, mm_each = 2, 5000000     # MM holds 5M of EACH of 6 currencies
    gov_cash = 100000000
    firm_count, firm_cash = 12, 800000       # genesis firms per country

    resident_home = sum(n * c for (n, c) in cash.values())          # excludes MM (all-ccy) & firms
    resident_home += mm_per_country * mm_each                       # home-ccy share of resident MMs
    firms_home = firm_count * firm_cash
    foreign_mm_home = (6 - 1) * mm_per_country * mm_each            # foreign MMs each hold 5M of this ccy
    total_home_ccy = resident_home + firms_home + foreign_mm_home + gov_cash

    avg_cash_naive = resident_home / 100
    m0_formula = 100 * avg_cash_naive + gov_cash                    # doc 16 §16.7.3 formula

    print(f"  resident home-ccy cash (incl 2 resident MM): {resident_home:,}")
    print(f"  genesis firms (12) home-ccy cash           : {firms_home:,}")
    print(f"  FOREIGN MMs holding this ccy (10 x 5M)     : {foreign_mm_home:,}")
    print(f"  GOV:<cc> cash                              : {gov_cash:,}")
    print(f"  ----")
    print(f"  TRUE total CUR:<cc> genesis endowment      : {total_home_ccy:,}")
    print(f"  §16.7.3 formula (100*avg + GOV)            : {int(m0_formula):,}")
    gap = total_home_ccy - m0_formula
    print(f"  GAP (formula undercounts by)               : {int(gap):,}  "
          f"({'INCONSISTENT - firms + foreign-MM not minted' if gap>1 else 'ok'})")

    # consumption coverage: avg household 50000 vs core spend ~1728/turn
    core_spend = 1728
    print(f"\n  household cash buffer: 50000 / {core_spend} per-turn core = "
          f"{50000/core_spend:.1f} turns of core consumption (doc 16 wants 6-10)")
    print("    -> 50000 gives ~29 turns; higher than 6-10 target. wage/price ratio is generous.")


if __name__ == "__main__":
    combat()
    finance()
    money()
