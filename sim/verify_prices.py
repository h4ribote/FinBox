"""
Verify the documented genesis reference prices (doc 16 §16.15.1) give a
positive single-step production margin for every recipe at recipe_yield_scale=10.
A firm buys inputs+labor at market (reference) prices, runs the recipe, sells
output at its reference price. margin = price - (input+labor cost)/(out_qty*yield).
"""
YIELD = 10

WAGE = {
    "labor.unskilled": 12000, "labor.farm": 11000, "labor.mine": 14000,
    "labor.build": 13000, "labor.factory": 12000, "labor.office": 16000,
    "labor.service": 11000, "labor.engineer": 22000, "labor.health": 20000,
    "labor.research": 22000, "labor.soldier": 13000,
}
# documented reference prices (doc 16 §16.15.1), minor units
PRICE = {
    "energy.electricity": 1000, "energy.fuel": 1500,
    "agri.grain": 800, "agri.vegetable": 1000, "agri.timber": 1000,
    "agri.cotton": 1200, "agri.livestock": 2500, "agri.fish": 2500,
    "raw.iron_ore": 1500, "raw.coal": 1200, "raw.crude_oil": 2000,
    "raw.limestone": 800, "raw.copper_ore": 1800, "raw.bauxite": 1800, "raw.rare_earth": 8000,
    "mat.steel": 2500, "mat.flour": 1200, "mat.lumber": 1200, "mat.concrete": 1500,
    "mat.cement": 1000, "mat.fabric": 1500, "mat.components": 6000, "mat.chemicals": 2500,
    "mat.fertilizer": 1500, "mat.plastics": 2000, "mat.copper": 3000, "mat.aluminum": 3500,
    "mat.glass": 1500,
    "good.food": 3000, "good.clothing": 3000, "good.medicine": 9000,
    "good.electronics": 45000, "good.vehicle": 120000, "good.appliance": 30000, "good.furniture": 12000,
    "svc.healthcare": 8000, "svc.education": 9000, "svc.leisure": 4000, "svc.retail": 1500,
    "svc.transport": 2000, "svc.finance": 3000,
    "build.construction_labor": 3500, "mil.munitions": 15000,
}
PRICE.update(WAGE)

# recipes: output -> (out_qty_per_run, {input: coeff_per_run}) (doc 10 §10.4)
RECIPES = {
    "agri.grain": (1, {"labor.farm": 1, "mat.fertilizer": 1, "energy.fuel": 1}),
    "agri.vegetable": (1, {"labor.farm": 1, "mat.fertilizer": 1, "energy.fuel": 1}),
    "energy.electricity": (4, {"raw.coal": 1, "labor.factory": 1, "labor.engineer": 1}),
    "energy.fuel": (3, {"raw.crude_oil": 1, "labor.factory": 1, "labor.engineer": 1}),
    "raw.iron_ore": (1, {"labor.mine": 2, "energy.electricity": 1, "energy.fuel": 1}),
    "raw.coal": (1, {"labor.mine": 2, "energy.fuel": 1}),
    "raw.crude_oil": (1, {"labor.mine": 2, "energy.electricity": 1}),
    "raw.copper_ore": (1, {"labor.mine": 2, "energy.electricity": 1}),
    "mat.steel": (1, {"raw.iron_ore": 2, "raw.coal": 1, "energy.electricity": 1, "labor.factory": 1}),
    "mat.cement": (1, {"raw.limestone": 2, "energy.electricity": 1, "labor.factory": 1}),
    "mat.concrete": (1, {"mat.cement": 1, "raw.limestone": 1, "labor.build": 1}),
    "mat.lumber": (1, {"agri.timber": 2, "labor.factory": 1}),
    "mat.chemicals": (1, {"raw.crude_oil": 2, "energy.electricity": 1, "labor.factory": 1, "labor.engineer": 1}),
    "mat.plastics": (1, {"mat.chemicals": 1, "energy.electricity": 1, "labor.factory": 1}),
    "mat.fertilizer": (1, {"mat.chemicals": 1, "labor.factory": 1}),
    "mat.fabric": (1, {"agri.cotton": 2, "labor.factory": 1}),
    "mat.flour": (1, {"agri.grain": 2, "labor.factory": 1}),
    "mat.copper": (1, {"raw.copper_ore": 2, "energy.electricity": 1, "labor.factory": 1}),
    "mat.components": (1, {"mat.copper": 1, "mat.plastics": 1, "energy.electricity": 1, "labor.factory": 1, "labor.engineer": 1}),
    "good.food": (1, {"agri.grain": 1, "mat.flour": 1, "labor.factory": 1}),
    "good.clothing": (1, {"mat.fabric": 2, "labor.factory": 1}),
    "good.medicine": (1, {"mat.chemicals": 2, "agri.vegetable": 1, "labor.factory": 1, "labor.research": 1}),
    "good.electronics": (1, {"mat.components": 2, "mat.plastics": 1, "energy.electricity": 1, "labor.factory": 1, "labor.engineer": 1}),
    "svc.healthcare": (1, {"labor.health": 1, "good.medicine": 1}),
    "svc.education": (1, {"labor.research": 1, "labor.office": 1}),
    "svc.leisure": (1, {"labor.service": 1, "good.electronics": 1}),
    "svc.retail": (1, {"labor.service": 1}),
    "svc.transport": (1, {"energy.fuel": 1, "labor.unskilled": 1}),
    "mil.munitions": (1, {"mat.steel": 2, "mat.chemicals": 1, "good.electronics": 1, "labor.factory": 1}),
    "build.construction_labor": (1, {"mat.lumber": 1, "mat.concrete": 2, "labor.build": 2}),
}


def main():
    print("=" * 74)
    print(f"REFERENCE-PRICE MARGIN CHECK  (yield_scale={YIELD}, single-step P&L, minor)")
    print("=" * 74)
    print(f"  {'output':<26}{'price':>8}{'cost/unit':>11}{'margin':>9}{'mgn%':>7}  status")
    bad = []
    for out, (oq, inputs) in RECIPES.items():
        run_cost = sum(PRICE[i] * c for i, c in inputs.items())
        cost_unit = run_cost / (oq * YIELD)
        price = PRICE[out]
        margin = price - cost_unit
        pct = 100 * margin / price if price else 0
        status = "OK" if margin > 0 else "LOSS"
        if margin <= 0:
            bad.append(out)
        print(f"  {out:<26}{price:>8}{cost_unit:>11.0f}{margin:>9.0f}{pct:>6.0f}%  {status}")
    print("-" * 74)
    if bad:
        print(f"  NEGATIVE-MARGIN steps (would not be produced): {bad}")
        print("  -> raise those output reference prices or their input yields.")
    else:
        print("  ALL recipes have POSITIVE margin at documented prices + yield=10.")
        print("  => supply chain is self-consistent: every stage is profitable to produce.")


if __name__ == "__main__":
    main()
