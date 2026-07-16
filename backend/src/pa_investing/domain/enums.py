from enum import StrEnum


class AssetClass(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    CRYPTO = "crypto"
    CASH = "cash"


class SignalType(StrEnum):
    ENTRY_LEVEL = "entry_level"
    STOP_REFERENCE = "stop_reference"
    RISK_LIMIT = "risk_limit"
    REVIEW_REQUIRED = "review_required"


class SignalSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalStatus(StrEnum):
    OPEN = "open"
    REVIEW_REQUESTED = "review_requested"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class CostBasisStatus(StrEnum):
    MANUAL = "manual"
    BROKER = "broker"
    TRADE_RECONSTRUCTED = "trade_reconstructed"
    UNAVAILABLE = "unavailable"


class QuoteQuality(StrEnum):
    LIVE = "live"
    DELAYED = "delayed"
    EOD = "eod"
    EOD_FALLBACK = "eod_fallback"
    MANUAL = "manual"
