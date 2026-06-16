"""
FinBox parameter validation: household survival / affordability loop.

Validates whether the labor -> wage -> consumption -> needs loop is sustainable
under the documented parameters, and compares the two conflicting need-decay
sets (doc 05 detailed vs doc 16 §16.5 table).

All currency values are in MINOR units (money.minor_unit = 1000, so display = /1000).
Pure Python; deterministic (fixed pseudo-policy, no RNG).
"""

# ---- reference prices (minor units). doc 16 §16.11 anchors: good.food~3000, labor.unskilled wage~12000.
PRICES = {
    "good.food": 3000,
    "water": 1500,          # good.food#drink / svc.retail water
    "svc.healthcare": 8000,
    "good.medicine": 5000,
    "svc.leisure": 4000,
}
WAGE_UNSKILLED = 12000      # labor.unskilled clearing price per unit (doc 16 §16.11)
INCOME_TAX_BPS = 1500       # 15% (doc 16)
CONSUMPTION_TAX_BPS = 800   # 8% (doc 16)

# recovery coefficients (doc 05 §5.2)
REC = {
    "satiety_food": 18, "satiety_agri": 6,
    "hydration_water": 25,
    "health_care": 30, "health_med": 12,
    "leisure_svc": 14, "leisure_elec": 6,
}
STAMINA_COST_UNSKILLED = 8  # doc 05 §5.3 table
REST_COST_UNSKILLED = 6
BASE_STAMINA_RECOVERY = 30  # doc 05 §5.2.4

# Two candidate decay sets
DECAY_DOC05 = {  # doc 05 §5.2 (non-labor baseline where applicable)
    "satiety": 6, "hydration": 10, "health": 1, "stamina_nonlabor": 2,
    "rest_nonlabor": 3, "leisure": 7, "comfort": 2, "social": 4, "stress": 3,
}
DECAY_DOC16 = {  # doc 16 §16.5
    "satiety": 8, "hydration": 12, "health": 3, "stamina_nonlabor": 6,
    "rest_nonlabor": 5, "leisure": 6, "comfort": 3, "social": 4, "stress": 4,
}

DEATH = {"satiety_zero_turns": 6, "health_crit": 10}  # doc 05 §5.4


def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def add_tax(cash_out, bps):
    # consumption tax on purchase
    return cash_out + (cash_out * bps) // 10000


def simulate(decay, turns=480, label=""):
    needs = {"satiety": 70, "hydration": 70, "health": 80, "stamina": 80,
             "rest": 80, "leisure": 60, "comfort": 45, "social": 60, "stress": 20}
    cash = 50000  # labor genesis cash (doc 16 §16.7.2)
    starve = 0
    alive = True
    death_turn = None
    min_needs = {k: 100 for k in needs}
    cash_series = []
    work_turns = 0

    for t in range(turns):
        # ---- decision: rest if stamina low, else work
        do_work = needs["stamina"] >= (STAMINA_COST_UNSKILLED + 10)
        # ---- earn (sell 1 unit labor.unskilled at wage, minus income tax) when working
        if do_work:
            gross = WAGE_UNSKILLED
            cash += gross - (gross * INCOME_TAX_BPS) // 10000
            needs["stamina"] -= STAMINA_COST_UNSKILLED
            needs["rest"] -= REST_COST_UNSKILLED
            work_turns += 1
        else:
            needs["stamina"] -= decay["stamina_nonlabor"]
            # rest turn recovers rest & stamina (doc 05 §5.2.4)
            needs["rest"] = clamp(needs["rest"] + 20 + (15 * needs["comfort"]) // 100)
            hf = 60 + (40 * needs["health"]) // 100          # health_factor*100
            hyf = 70 + (30 * needs["hydration"]) // 100        # hydration_factor*100 (cap 100)
            hyf = min(100, hyf)
            rec = (BASE_STAMINA_RECOVERY * needs["rest"] * hf * hyf) // (100 * 100 * 100)
            needs["stamina"] = clamp(needs["stamina"] + rec)

        # ---- consume to maintain needs (greedy thresholds), pay consumption tax
        def buy(asset, qty):
            nonlocal cash
            cost = add_tax(PRICES[asset] * qty, CONSUMPTION_TAX_BPS)
            if cash >= cost:
                cash -= cost
                return qty
            return 0

        # satiety
        if needs["satiety"] < 55:
            q = buy("good.food", 1)
            needs["satiety"] = clamp(needs["satiety"] + REC["satiety_food"] * q)
        # hydration
        if needs["hydration"] < 55:
            q = buy("water", 1)
            needs["hydration"] = clamp(needs["hydration"] + REC["hydration_water"] * q)
        # health
        if needs["health"] < 45:
            q = buy("svc.healthcare", 1)
            needs["health"] = clamp(needs["health"] + REC["health_care"] * q)
        # leisure (only if comfortably positive cash buffer)
        if needs["leisure"] < 35 and cash > 30000:
            q = buy("svc.leisure", 1)
            needs["leisure"] = clamp(needs["leisure"] + REC["leisure_svc"] * q)

        # ---- decay (end of turn)
        needs["satiety"] = clamp(needs["satiety"] - decay["satiety"])
        needs["hydration"] = clamp(needs["hydration"] - decay["hydration"])
        needs["leisure"] = clamp(needs["leisure"] - decay["leisure"])
        needs["comfort"] = clamp(needs["comfort"] - decay["comfort"])
        needs["social"] = clamp(needs["social"] - decay["social"])
        # health: base decay + satiety/hydration penalties (doc 05)
        hpen = decay["health"]
        if needs["satiety"] < 20:
            hpen += 4
        if needs["hydration"] < 15:
            hpen += 3
        needs["health"] = clamp(needs["health"] - hpen)

        for k in needs:
            min_needs[k] = min(min_needs[k], needs[k])
        cash_series.append(cash)

        # ---- death checks (doc 05 §5.4)
        if needs["satiety"] <= 0 or needs["hydration"] <= 0:
            starve += 1
        else:
            starve = 0
        if starve >= DEATH["satiety_zero_turns"]:
            alive = False; death_turn = t; break
        if needs["health"] <= 0:
            alive = False; death_turn = t; break

    return {
        "label": label, "alive": alive, "death_turn": death_turn,
        "final_cash": cash, "work_ratio": round(work_turns / max(1, t + 1), 3),
        "min_needs": {k: round(v, 1) for k, v in min_needs.items()},
        "cash_start": 50000, "cash_end": cash_series[-1] if cash_series else 50000,
    }


def main():
    print("=" * 70)
    print("HOUSEHOLD SURVIVAL / AFFORDABILITY  (minor_unit=1000; cash in minor)")
    print("=" * 70)
    for label, decay in [("doc05 decays", DECAY_DOC05), ("doc16 decays", DECAY_DOC16)]:
        r = simulate(decay, turns=480, label=label)
        print(f"\n[{label}]")
        print(f"  alive after 480 turns (10y): {r['alive']}  (death_turn={r['death_turn']})")
        print(f"  work ratio (turns worked):   {r['work_ratio']}")
        print(f"  cash: start {r['cash_start']} -> end {r['cash_end']} "
              f"(disp {r['cash_end']/1000:.3f})")
        print(f"  min need levels reached:     {r['min_needs']}")

    # steady-state affordability (doc05 decays, full-time-equivalent)
    print("\n" + "-" * 70)
    print("STEADY-STATE SPEND vs INCOME (doc05 decays, per turn, minor)")
    food_rate = DECAY_DOC05["satiety"] / REC["satiety_food"]
    water_rate = DECAY_DOC05["hydration"] / REC["hydration_water"]
    spend_food = food_rate * PRICES["good.food"]
    spend_water = water_rate * PRICES["water"]
    spend = (spend_food + spend_water) * (1 + CONSUMPTION_TAX_BPS / 10000)
    income_ft = WAGE_UNSKILLED * (1 - INCOME_TAX_BPS / 10000)
    # stamina-limited work ratio: rest recovers ~30, work costs 8 -> ~ 30/(30+8*?) ; approximate
    print(f"  food need/turn  : {food_rate:.3f} good.food -> {spend_food:.0f}")
    print(f"  water need/turn : {water_rate:.3f} water     -> {spend_water:.0f}")
    print(f"  core spend/turn (food+water, +8% tax): {spend:.0f}")
    print(f"  net wage/turn (full-time, -15% tax)  : {income_ft:.0f}")
    print(f"  surplus ratio (income/spend): {income_ft/spend:.2f}x")


if __name__ == "__main__":
    main()
