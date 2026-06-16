"""
FinBox supply-chain cost consistency check.
Builds bottom-up production cost per asset from doc 10 recipes (unit coefficients)
and a wage table, then checks final-good margins at the doc 16 reference prices.
Reveals whether final goods can be produced profitably (positive margin),
i.e. whether the reference-price / wage / recipe scale is self-consistent.

Currency in MINOR units (minor_unit=1000).
"""

# wages per 1 labor unit (clearing price guesses; unskilled anchored to doc 16 ~12000)
WAGE = {
    "labor.unskilled": 12000, "labor.farm": 11000, "labor.mine": 14000,
    "labor.build": 13000, "labor.factory": 12000, "labor.office": 16000,
    "labor.service": 11000, "labor.engineer": 22000, "labor.health": 20000,
    "labor.research": 22000, "labor.soldier": 13000,
}

# recipes: output_asset -> (output_qty_per_run, {input_asset: qty_per_run})  (doc 10 §10.4)
RECIPES = {
    "agri.grain":  (1, {"labor.farm": 1, "mat.fertilizer": 1, "energy.fuel": 1}),
    "agri.cotton": (1, {"labor.farm": 1, "energy.fuel": 1}),
    "agri.timber": (1, {"labor.farm": 1}),
    "raw.iron_ore":(1, {"labor.mine": 2, "energy.electricity": 1, "energy.fuel": 1}),
    "raw.coal":    (1, {"labor.mine": 2, "energy.fuel": 1}),
    "raw.crude_oil":(1,{"labor.mine": 2, "energy.electricity": 1}),
    "raw.limestone":(1,{"labor.mine": 2, "energy.fuel": 1}),
    "energy.electricity": (4, {"raw.coal": 1, "labor.factory": 1, "labor.engineer": 1}),
    "energy.fuel":        (3, {"raw.crude_oil": 1, "labor.factory": 1, "labor.engineer": 1}),
    "mat.steel":   (1, {"raw.iron_ore": 2, "raw.coal": 1, "energy.electricity": 1, "labor.factory": 1}),
    "mat.cement":  (1, {"raw.limestone": 2, "energy.electricity": 1, "labor.factory": 1}),
    "mat.concrete":(1, {"mat.cement": 1, "raw.limestone": 1, "labor.build": 1}),
    "mat.lumber":  (1, {"agri.timber": 2, "labor.factory": 1}),
    "mat.chemicals":(1,{"raw.crude_oil": 2, "energy.electricity": 1, "labor.factory": 1, "labor.engineer": 1}),
    "mat.plastics":(1, {"mat.chemicals": 1, "energy.electricity": 1, "labor.factory": 1}),
    "mat.fertilizer":(1,{"mat.chemicals": 1, "labor.factory": 1}),
    "mat.fabric":  (1, {"agri.cotton": 2, "labor.factory": 1}),
    "mat.flour":   (1, {"agri.grain": 2, "labor.factory": 1}),
    "mat.components":(1,{"mat.copper": 1, "mat.plastics": 1, "energy.electricity": 1, "labor.factory": 1, "labor.engineer": 1}),
    "mat.copper":  (1, {"raw.copper_ore": 2, "energy.electricity": 1, "labor.factory": 1}),
    "raw.copper_ore":(1,{"labor.mine": 2, "energy.electricity": 1}),
    "good.food":   (1, {"agri.grain": 1, "mat.flour": 1, "labor.factory": 1}),
    "good.clothing":(1,{"mat.fabric": 2, "labor.factory": 1}),
    "good.medicine":(1,{"mat.chemicals": 2, "agri.vegetable": 1, "labor.factory": 1, "labor.research": 1}),
    "agri.vegetable":(1,{"labor.farm": 1, "mat.fertilizer": 1, "energy.fuel": 1}),
    "svc.healthcare":(1,{"labor.health": 1, "good.medicine": 1}),
    "svc.leisure": (1, {"labor.service": 1}),
    "svc.retail":  (1, {"labor.service": 1}),
    "svc.transport":(1,{"energy.fuel": 1, "labor.unskilled": 1}),
    "build.construction_labor": (1, {"mat.lumber": 1, "mat.concrete": 2, "labor.build": 2}),
}

# doc 16 §16.11 reference prices (the ones the doc anchors)
DOC_REF = {"good.food": 3000, "labor.unskilled": 12000}


def unit_cost(asset, yield_scale, memo, stack=()):
    """bottom-up per-output-unit production cost (no markup)."""
    if asset in WAGE:
        return WAGE[asset]
    if asset in memo:
        return memo[asset]
    if asset not in RECIPES or asset in stack:
        return None  # raw extracted (priced by region scarcity) or cycle
    out_qty, inputs = RECIPES[asset]
    total = 0.0
    for inp, q in inputs.items():
        c = unit_cost(inp, yield_scale, memo, stack + (asset,))
        if c is None:
            # extracted primary with no recipe cost here: approximate by its labor proxy
            c = WAGE["labor.mine"] if inp.startswith("raw.") else WAGE["labor.farm"]
        total += c * q
    cost = total / (out_qty * yield_scale)
    memo[asset] = cost
    return cost


def report(yield_scale):
    memo = {}
    print(f"\n--- recipe_yield_scale = {yield_scale}  (per-output-unit cost, no markup, minor) ---")
    finals = ["good.food", "good.clothing", "good.medicine", "svc.healthcare",
              "svc.leisure", "build.construction_labor", "mat.steel", "energy.electricity"]
    for a in finals:
        c = unit_cost(a, yield_scale, memo)
        print(f"  {a:<28} cost/unit = {c:>10.0f}")
    food = unit_cost("good.food", yield_scale, memo)
    print(f"  good.food cost {food:.0f} vs doc ref price 3000  -> "
          f"{'PROFITABLE' if 3000 > food else 'LOSS (price < cost!)'} (margin {3000-food:.0f})")
    return food


def main():
    print("=" * 70)
    print("SUPPLY-CHAIN COST CONSISTENCY  (does final-good price cover cost?)")
    print("=" * 70)
    print(f"wage labor.unskilled={WAGE['labor.unskilled']}, doc ref good.food={DOC_REF['good.food']}")
    food1 = report(1.0)
    food10 = report(10.0)
    food50 = report(50.0)
    print("\nDIAGNOSIS:")
    print(f"  At yield_scale=1, good.food cost ~{food1:.0f} >> ref price 3000  -> NEGATIVE margin.")
    print(f"  Because recipes embed ~1 labor unit (~12000) per 1 output unit, a final good")
    print(f"  cannot be cheaper than ~a wage unless one labor run yields many units.")
    # implied yield to make food ~ 3000 with ~25% markup target
    target_cost = 3000 / 1.25
    print(f"  To make good.food cost ~{target_cost:.0f} (so 3000 = cost x1.25), need yield_scale ~ {food1/target_cost:.1f}.")
    print("  => Either set recipe_yield_scale (1 labor -> many units) OR raise final-good")
    print("     reference prices above embedded labor cost. The doc's 'wage buys a few")
    print("     final goods' intent requires yield_scale >> 1.")


if __name__ == "__main__":
    main()
