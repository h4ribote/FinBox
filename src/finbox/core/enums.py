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


# Perishable namespaces (doc 00 0.5.3): labor.*, svc.*, energy.electricity.
PERISHABLE_NAMESPACES = frozenset({CommNamespace.LABOR, CommNamespace.SVC})


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


# Causes that may change an asset's total supply (mint/burn points, doc 00 0.10/0.17).
# A posting whose per-asset net delta is non-zero is only permitted under these.
MINT_BURN_CAUSES = frozenset({
    Cause.MINT, Cause.BURN, Cause.PRODUCTION, Cause.CONSUMPTION,
    Cause.GENESIS, Cause.MILITARY, Cause.EXPIRE, Cause.REDEEM,
})


class CountryCode(str, Enum):
    """The six fixed countries (doc 00 0.6). Currency code == country code."""
    ALD = "ALD"
    BOR = "BOR"
    CYR = "CYR"
    DOR = "DOR"
    ESM = "ESM"
    FAR = "FAR"
