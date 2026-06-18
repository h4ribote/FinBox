"""Canonical enumerations (doc 00).

Iteration order is fixed and meaningful (determinism): members are declared in
the canonical order used by the spec. All values are the exact string tokens
used in IDs / API / serialization.
"""
from __future__ import annotations
from enum import Enum


class AssetClass(str, Enum):
    """Tradable Asset classes (doc 00 0.5.1)."""
    CUR = "CUR"
    COMM = "COMM"
    BOND = "BOND"
    EQ = "EQ"
    BILL = "BILL"
    FUT = "FUT"


class CommNamespace(str, Enum):
    """COMM namespaces (doc 00 0.5.2)."""
    AGRI = "agri"
    RAW = "raw"
    ENERGY = "energy"
    MAT = "mat"
    GOOD = "good"
    LABOR = "labor"
    SVC = "svc"
    BUILD = "build"
    MIL = "mil"


# Perishable namespaces (doc 00 0.5.3): labor.*, svc.*. energy.electricity is a
# single perishable asset inside the otherwise-storable energy namespace (so it
# cannot be expressed as a whole namespace).
PERISHABLE_NAMESPACES = frozenset({CommNamespace.LABOR, CommNamespace.SVC})
PERISHABLE_ASSET_IDS = frozenset({"COMM:energy.electricity"})


def is_perishable(asset_id: str) -> bool:
    """True iff the asset is force-burned when unused at P9 (doc 00 0.5.3, doc 08 8.9.4).

    Perishable = the ``labor.*`` and ``svc.*`` namespaces, plus the single asset
    ``COMM:energy.electricity`` (``energy.fuel`` and the other ``energy.*`` assets are
    storable). Works on a bare id string (AssetId is a ``str`` subclass).
    """
    if asset_id in PERISHABLE_ASSET_IDS:
        return True
    if not asset_id.startswith("COMM:"):
        return False
    ns = asset_id.split(":", 1)[1].split(".", 1)[0]
    return ns in {CommNamespace.LABOR.value, CommNamespace.SVC.value}


def is_margin_eligible_base(asset_id: str) -> bool:
    """True iff ``asset_id`` is a margin-tradable base: CUR (FX), EQ (equity), or
    storable COMM (commodity) (doc 09 9.x 信用取引, doc 00 0.5.3).

    Perishable COMM (``labor.*``/``svc.*``/``energy.electricity``) cannot be carried to
    the next turn for physical repayment, so it is spot-only. BOND/BILL/FUT are spot-only.
    """
    if asset_id.startswith("CUR:") or asset_id.startswith("EQ:"):
        return True
    if asset_id.startswith("COMM:"):
        return not is_perishable(asset_id)
    return False


class LaborKind(str, Enum):
    """labor.* kinds = skill[k] index set (doc 00 0.5.2, doc 05 5.3)."""
    UNSKILLED = "unskilled"
    FARM = "farm"
    MINE = "mine"
    BUILD = "build"
    FACTORY = "factory"
    OFFICE = "office"
    SERVICE = "service"
    ENGINEER = "engineer"
    HEALTH = "health"
    RESEARCH = "research"
    SOLDIER = "soldier"


class TurnPhase(str, Enum):
    """Canonical turn pipeline phases (doc 00 0.11, doc 03)."""
    P0 = "P0"  # SNAPSHOT
    P1 = "P1"  # SUBMIT
    P2 = "P2"  # VALIDATE
    P3 = "P3"  # GOVERN
    P4 = "P4"  # CLEAR
    P5 = "P5"  # PRODUCE
    P6 = "P6"  # CONSUME
    P7 = "P7"  # FISCAL
    P8 = "P8"  # MILITARY
    P9 = "P9"  # ADVANCE
    INIT = "P-init"  # genesis (outside the pipeline, doc 08 8.6.2)


class OrderType(str, Enum):
    """Order types (doc 00 0.19)."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    IOC = "IOC"
    FOK = "FOK"


class TIF(str, Enum):
    """Time-in-force (doc 00 0.19); GFT is the default."""
    GFT = "GFT"
    GTC = "GTC"
    GTT = "GTT"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeMode(str, Enum):
    """Investor trade mode (doc 06 6.5/6.6): spot (no leverage) vs margin (信用取引)."""
    SPOT = "SPOT"
    MARGIN = "MARGIN"


class InvestStyle(str, Enum):
    """Investor strategy style (doc 06 6.6, doc 07 7.5.2)."""
    FUNDAMENTAL = "FUNDAMENTAL"
    TECHNICAL = "TECHNICAL"
    YIELD = "YIELD"


class PositionSide(str, Enum):
    """Margin position direction (doc 15 15.6 Position, doc 09 信用取引)."""
    LONG = "LONG"
    SHORT = "SHORT"


class AMMInvariant(str, Enum):
    """Automated market-maker bonding curve (doc 09 9.7, doc 15 AMMPool)."""
    CONST_PRODUCT = "CONST_PRODUCT"   # x·y=k, wide range (EQ/COMM)
    CONCENTRATED = "CONCENTRATED"     # constant-sum-ish, tight near parity (FX)


class MarketKind(str, Enum):
    """Market pair kinds (doc 15 15.7)."""
    LABOR = "LABOR"
    GOODS = "GOODS"
    FX = "FX"
    BOND = "BOND"
    EQUITY = "EQUITY"


class EntityKind(str, Enum):
    """Entity kinds (doc 00 0.4, doc 15 15.5)."""
    AGENT = "AGENT"
    FIRM = "FIRM"
    GOVERNMENT = "GOVERNMENT"
    CENTRAL_BANK = "CENTRAL_BANK"
    PLAYER = "PLAYER"
    EXCHANGE = "EXCHANGE"
    # protocol facilities that hold real balances (doc 09 信用取引, doc 15 15.6).
    # Not roles; they are balance-holding clearing facilities like EXCH.
    LENDING_POOL = "LENDING_POOL"
    INSURANCE_FUND = "INSURANCE_FUND"
    AMM_POOL = "AMM_POOL"


class Role(str, Enum):
    """Role taxonomy (doc 00 0.14)."""
    # labor / households
    FARMER = "FARMER"
    MINER = "MINER"
    BUILDER = "BUILDER"
    FACTORY_WORKER = "FACTORY_WORKER"
    SERVICE_WORKER = "SERVICE_WORKER"
    OFFICE_WORKER = "OFFICE_WORKER"
    LOGISTICS_WORKER = "LOGISTICS_WORKER"
    ENGINEER = "ENGINEER"
    HEALTHCARE_WORKER = "HEALTHCARE_WORKER"
    TEACHER = "TEACHER"
    RESEARCHER = "RESEARCHER"
    SOLDIER = "SOLDIER"
    STUDENT = "STUDENT"
    UNEMPLOYED = "UNEMPLOYED"
    RETIREE = "RETIREE"
    # capital / management
    ENTREPRENEUR = "ENTREPRENEUR"
    INVESTOR = "INVESTOR"
    MARKET_MAKER = "MARKET_MAKER"
    # INVESTOR-derived specializations (doc 06 6.6): trade_mode × style plus liquidity roles.
    # These are role tags layered on INVESTOR (not new entity kinds, doc 00 0.4/0.14).
    YIELD_INVESTOR = "YIELD_INVESTOR"   # style=YIELD: harvests income/carry
    ARBITRAGEUR = "ARBITRAGEUR"         # cross-market / cross-rate arbitrage
    AMM = "AMM"                         # passive automated market maker (LP)
    # public
    POLITICIAN = "POLITICIAN"
    CENTRAL_BANKER = "CENTRAL_BANKER"
    BUREAUCRAT = "BUREAUCRAT"
    GENERAL = "GENERAL"
    DIPLOMAT = "DIPLOMAT"


class Industry(str, Enum):
    """Industry taxonomy (doc 00 0.15)."""
    AGRICULTURE = "AGRICULTURE"
    MINING = "MINING"
    ENERGY = "ENERGY"
    CONSTRUCTION = "CONSTRUCTION"
    MANUFACTURING = "MANUFACTURING"
    LOGISTICS = "LOGISTICS"
    FINANCE = "FINANCE"
    SERVICES = "SERVICES"
    RESEARCH = "RESEARCH"


# Extractive industries are capped per region (doc 00 0.15).
EXTRACTIVE_INDUSTRIES = frozenset({Industry.AGRICULTURE, Industry.MINING})


class FirmLifecycle(str, Enum):
    """Firm lifecycle state machine (doc 10 10.8)."""
    FOUNDING = "FOUNDING"
    OPERATING = "OPERATING"
    EXPANDING = "EXPANDING"
    RAISING = "RAISING"
    DISTRIBUTING = "DISTRIBUTING"
    INSOLVENT = "INSOLVENT"
    LIQUIDATING = "LIQUIDATING"


class Terrain(str, Enum):
    """Cell terrain (doc 15 15.3, doc 04 4.2.1). Declaration order is canonical."""
    PLAIN = "PLAIN"
    FOREST = "FOREST"
    MOUNTAIN = "MOUNTAIN"
    DESERT = "DESERT"
    COAST = "COAST"
    TUNDRA = "TUNDRA"
    SWAMP = "SWAMP"


class Climate(str, Enum):
    """Cell climate zone (doc 04 4.4.1, doc 15 15.3). Declaration order = latitude band (canonical)."""
    TROPICAL = "TROPICAL"
    ARID = "ARID"
    TEMPERATE = "TEMPERATE"
    CONTINENTAL = "CONTINENTAL"
    POLAR = "POLAR"
    HIGHLAND = "HIGHLAND"


class Cause(str, Enum):
    """Ledger posting cause (doc 15 15.6, doc 08 8.4.2)."""
    TRADE = "TRADE"            # P4 market settlement
    PRODUCTION = "PRODUCTION"  # P5 produce (mint output / burn inputs)
    CONSUMPTION = "CONSUMPTION"  # P6 consume (burn)
    FISCAL = "FISCAL"          # P7 generic protocol transfer
    TAX = "TAX"
    TARIFF = "TARIFF"
    SUBSIDY = "SUBSIDY"
    COUPON = "COUPON"
    REDEEM = "REDEEM"
    DIVIDEND = "DIVIDEND"
    MINT = "MINT"              # CB currency issuance (P7)
    BURN = "BURN"              # CB currency absorption (P7)
    MILITARY = "MILITARY"      # P8 munitions burn
    LIQUIDATION = "LIQUIDATION"
    GENESIS = "GENESIS"        # initial endowment (P-init)
    EXPIRE = "EXPIRE"          # P9 perishable expiry burn (doc 08 8.9.4)
    # margin / lending facility transfers (doc 09 信用取引) — all conserving real-asset moves
    POOL_SUPPLY = "POOL_SUPPLY"          # supplier -> lending pool (deposit, mint pool share)
    POOL_WITHDRAW = "POOL_WITHDRAW"      # lending pool -> supplier (redeem pool share)
    LOAN = "LOAN"                        # lending pool -> borrower (margin borrow), loan_id ref
    REPAY = "REPAY"                      # borrower -> lending pool (principal repayment)
    INTEREST = "INTEREST"                # borrower -> suppliers + insurance (redistribution, doc 00 0.10)
    LIQUIDATION_PENALTY = "LIQUIDATION_PENALTY"  # forced-liq penalty: collateral -> insurance
    HAIRCUT = "HAIRCUT"                  # insurance/supplier absorbs bad debt (equity<0)
    AMM_SUPPLY = "AMM_SUPPLY"            # LP -> AMM pool reserves (mint LP share)
    AMM_WITHDRAW = "AMM_WITHDRAW"        # AMM pool reserves -> LP (redeem LP share)


# Causes that may change an asset's total supply (mint/burn points, doc 00 0.10/0.17).
# A posting whose per-asset net delta is non-zero is only permitted under these.
# LIQUIDATION burns EQ (and residual securities) at firm wind-up (doc 08 8.6.2, doc 00 0.5.1/0.17).
MINT_BURN_CAUSES = frozenset({
    Cause.MINT, Cause.BURN, Cause.PRODUCTION, Cause.CONSUMPTION,
    Cause.GENESIS, Cause.MILITARY, Cause.EXPIRE, Cause.REDEEM, Cause.LIQUIDATION,
})


class CountryCode(str, Enum):
    """The six fixed countries (doc 00 0.6). Currency code == country code."""
    ALD = "ALD"
    BOR = "BOR"
    CYR = "CYR"
    DOR = "DOR"
    ESM = "ESM"
    FAR = "FAR"
