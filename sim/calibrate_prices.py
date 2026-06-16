"""
Calibrate a self-consistent genesis reference-price table:
price[X] = ceil( (sum input_price*coeff + sum wage*coeff) / (out_qty*yield) * markup )
Iterated to a fixpoint (recipe input cycles: energy<->raw). Guarantees every
single-step production margin = (markup-1) > 0. Output replaces doc 16 §16.15.1.
"""
import math
YIELD = 10
MARKUP = 1.40

WAGE = {
    "labor.unskilled": 12000, "labor.farm": 11000, "labor.mine": 14000,
    "labor.build": 13000, "labor.factory": 12000, "labor.office": 16000,
    "labor.service": 11000, "labor.engineer": 22000, "labor.health": 20000,
    "labor.research": 22000, "labor.soldier": 13000,
}
RECIPES = {
    "agri.grain": (1, {"labor.farm": 1, "mat.fertilizer": 1, "energy.fuel": 1}),
    "agri.vegetable": (1, {"labor.farm": 1, "mat.fertilizer": 1, "energy.fuel": 1}),
    "agri.cotton": (1, {"labor.farm": 1, "energy.fuel": 1}),
    "agri.timber": (1, {"labor.farm": 1}),
    "agri.livestock": (1, {"labor.farm": 1, "agri.grain": 1}),
    "agri.fish": (1, {"labor.farm": 1, "energy.fuel": 1}),
    "raw.iron_ore": (1, {"labor.mine": 2, "energy.electricity": 1, "energy.fuel": 1}),
    "raw.coal": (1, {"labor.mine": 2, "energy.fuel": 1}),
    "raw.crude_oil": (1, {"labor.mine": 2, "energy.electricity": 1}),
    "raw.copper_ore": (1, {"labor.mine": 2, "energy.electricity": 1}),
    "raw.bauxite": (1, {"labor.mine": 2, "energy.electricity": 1}),
    "raw.limestone": (1, {"labor.mine": 2, "energy.fuel": 1}),
    "raw.rare_earth": (1, {"labor.mine": 3, "energy.electricity": 1}),
    "energy.electricity": (4, {"raw.coal": 1, "labor.factory": 1, "labor.engineer": 1}),
    "energy.fuel": (3, {"raw.crude_oil": 1, "labor.factory": 1, "labor.engineer": 1}),
    "mat.steel": (1, {"raw.iron_ore": 2, "raw.coal": 1, "energy.electricity": 1, "labor.factory": 1}),
    "mat.aluminum": (1, {"raw.bauxite": 2, "energy.electricity": 3, "labor.factory": 1}),
    "mat.copper": (1, {"raw.copper_ore": 2, "energy.electricity": 1, "labor.factory": 1}),
    "mat.cement": (1, {"raw.limestone": 2, "energy.electricity": 1, "labor.factory": 1}),
    "mat.concrete": (1, {"mat.cement": 1, "raw.limestone": 1, "labor.build": 1}),
    "mat.lumber": (1, {"agri.timber": 2, "labor.factory": 1}),
    "mat.chemicals": (1, {"raw.crude_oil": 2, "energy.electricity": 1, "labor.factory": 1, "labor.engineer": 1}),
    "mat.plastics": (1, {"mat.chemicals": 1, "energy.electricity": 1, "labor.factory": 1}),
    "mat.fertilizer": (1, {"mat.chemicals": 1, "labor.factory": 1}),
    "mat.glass": (1, {"raw.limestone": 1, "energy.electricity": 2, "labor.factory": 1}),
    "mat.fabric": (1, {"agri.cotton": 2, "labor.factory": 1}),
    "mat.flour": (1, {"agri.grain": 2, "labor.factory": 1}),
    "mat.components": (1, {"mat.copper": 1, "mat.plastics": 1, "energy.electricity": 1, "labor.factory": 1, "labor.engineer": 1}),
    "good.food": (1, {"agri.grain": 1, "mat.flour": 1, "labor.factory": 1}),
    "good.clothing": (1, {"mat.fabric": 2, "labor.factory": 1}),
    "good.electronics": (1, {"mat.components": 2, "mat.plastics": 1, "energy.electricity": 1, "labor.factory": 1, "labor.engineer": 1}),
    "good.appliance": (1, {"mat.steel": 1, "good.electronics": 1, "mat.plastics": 1, "labor.factory": 1}),
    "good.vehicle": (1, {"mat.steel": 2, "mat.aluminum": 1, "good.electronics": 1, "mat.plastics": 1, "labor.factory": 1, "labor.engineer": 1}),
    "good.furniture": (1, {"mat.lumber": 2, "mat.fabric": 1, "labor.factory": 1}),
    "good.medicine": (1, {"mat.chemicals": 2, "agri.vegetable": 1, "labor.factory": 1, "labor.research": 1}),
    "svc.healthcare": (1, {"labor.health": 1, "good.medicine": 1}),
    "svc.education": (1, {"labor.research": 1, "labor.office": 1}),
    "svc.leisure": (1, {"labor.service": 1, "good.electronics": 1}),
    "svc.retail": (1, {"labor.service": 1}),
    "svc.transport": (1, {"energy.fuel": 1, "labor.unskilled": 1}),
    "svc.finance": (1, {"labor.office": 1}),
    "mil.munitions": (1, {"mat.steel": 2, "mat.chemicals": 1, "good.electronics": 1, "labor.factory": 1}),
    "build.construction_labor": (1, {"mat.lumber": 1, "mat.concrete": 2, "labor.build": 2}),
}


def round_nice(x):
    # round up to 2 significant figures for readable reference prices
    if x <= 0:
        return 0
    mag = 10 ** (len(str(int(x))) - 2) if x >= 100 else 10
    return int(math.ceil(x / mag) * mag)


def main():
    price = dict(WAGE)
    for k in RECIPES:
        price.setdefault(k, 1000)
    for _ in range(30):  # fixpoint
        for out, (oq, inputs) in RECIPES.items():
            run = sum(price[i] * c for i, c in inputs.items())
            cost_unit = run / (oq * YIELD)
            price[out] = round_nice(cost_unit * MARKUP)

    print("=" * 64)
    print(f"CALIBRATED REFERENCE PRICES  (yield={YIELD}, markup={MARKUP}, minor)")
    print("=" * 64)
    groups = {}
    for k in RECIPES:
        groups.setdefault(k.split(".")[0], []).append(k)
    for g in ["agri", "raw", "energy", "mat", "good", "svc", "mil", "build"]:
        for k in sorted(groups.get(g, [])):
            print(f"  {k:<28} {price[k]:>8}")
    # verify single-step margins
    print("-" * 64)
    bad = []
    minm = 1e9
    for out, (oq, inputs) in RECIPES.items():
        cost = sum(price[i] * c for i, c in inputs.items()) / (oq * YIELD)
        m = (price[out] - cost) / price[out]
        minm = min(minm, m)
        if price[out] <= cost:
            bad.append(out)
    print(f"  all positive margin: {not bad}; min margin {minm*100:.1f}%"
          + (f"; LOSS:{bad}" if bad else ""))
    # household check: wage vs good.food
    print(f"  good.food={price['good.food']}  labor.unskilled wage={WAGE['labor.unskilled']}  "
          f"-> 1 wage buys {WAGE['labor.unskilled']/price['good.food']:.1f} food")


if __name__ == "__main__":
    main()
