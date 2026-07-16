import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MarketDefinition:
    code: str
    aliases: frozenset[str]
    exchanges: frozenset[str]
    yahoo_suffixes: tuple[str, ...] = ()


class MarketCodeRegistry:
    def __init__(self, definitions: tuple[MarketDefinition, ...]) -> None:
        self._definitions = {item.code: item for item in definitions}
        self._aliases = {
            self._normalize_token(alias): item.code
            for item in definitions
            for alias in {*item.aliases, item.code}
        }
        self._exchanges = {
            exchange.upper(): item.code for item in definitions for exchange in item.exchanges
        }

    @staticmethod
    def _normalize_token(value: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", value.strip().upper())

    def normalize(self, value: str) -> str:
        normalized = self._normalize_token(value)
        try:
            return self._aliases[normalized]
        except KeyError as exc:
            raise ValueError(f"unknown market code: {value}") from exc

    def market_for_exchange(self, exchange: str | None) -> str | None:
        if not exchange:
            return None
        normalized = exchange.strip().upper()
        return self._exchanges.get(normalized) or self._aliases.get(
            self._normalize_token(normalized)
        )

    def display_symbol(self, provider_symbol: str, market_code: str) -> str:
        symbol = provider_symbol.strip().upper()
        definition = self._definitions[self.normalize(market_code)]
        for suffix in definition.yahoo_suffixes:
            if symbol.endswith(suffix):
                return symbol[: -len(suffix)]
        return symbol


DEFAULT_MARKET_CODES = MarketCodeRegistry(
    (
        MarketDefinition(
            code="US",
            aliases=frozenset({"U.S.", "USA"}),
            exchanges=frozenset(
                {
                    "US",
                    "NASDAQ",
                    "NYSE",
                    "NYSE ARCA",
                    "AMEX",
                    "NMS",
                    "NGM",
                    "NCM",
                    "NYQ",
                    "ASE",
                    "XNAS",
                    "XNYS",
                    "ARCX",
                    "BATS",
                }
            ),
        ),
        MarketDefinition(
            code="LN",
            aliases=frozenset({"LONDON", "UK"}),
            exchanges=frozenset({"LN", "LSE", "XLON", "LONDON"}),
            yahoo_suffixes=(".L",),
        ),
        MarketDefinition(
            code="HK",
            aliases=frozenset({"HONGKONG", "HKEX"}),
            exchanges=frozenset({"HK", "HKG", "HKEX", "XHKG"}),
            yahoo_suffixes=(".HK",),
        ),
        MarketDefinition(
            code="JP",
            aliases=frozenset({"JAPAN", "TOKYO", "TSE"}),
            exchanges=frozenset({"JP", "TSE", "XTKS", "TOKYO"}),
            yahoo_suffixes=(".T",),
        ),
        MarketDefinition(
            code="GY",
            aliases=frozenset({"GERMANY", "XETRA"}),
            exchanges=frozenset({"GY", "XETRA", "XETR", "FRANKFURT"}),
            yahoo_suffixes=(".DE", ".F"),
        ),
        MarketDefinition(
            code="FP",
            aliases=frozenset({"FRANCE", "PARIS"}),
            exchanges=frozenset({"FP", "EURONEXT PARIS", "XPAR", "PARIS"}),
            yahoo_suffixes=(".PA",),
        ),
        MarketDefinition(
            code="NA",
            aliases=frozenset({"NETHERLANDS", "AMSTERDAM"}),
            exchanges=frozenset({"NA", "EURONEXT AMSTERDAM", "XAMS", "AMSTERDAM"}),
            yahoo_suffixes=(".AS",),
        ),
        MarketDefinition(
            code="SW",
            aliases=frozenset({"SWITZERLAND", "SIX"}),
            exchanges=frozenset({"SW", "SIX", "XSWX"}),
            yahoo_suffixes=(".SW",),
        ),
        MarketDefinition(
            code="IM",
            aliases=frozenset({"ITALY", "MILAN"}),
            exchanges=frozenset({"IM", "MILAN", "XMIL"}),
            yahoo_suffixes=(".MI",),
        ),
        MarketDefinition(
            code="SM",
            aliases=frozenset({"SPAIN", "MADRID"}),
            exchanges=frozenset({"SM", "MADRID", "XMAD"}),
            yahoo_suffixes=(".MC",),
        ),
    )
)


@dataclass(frozen=True)
class CanonicalInstrumentReference:
    symbol: str
    market_code: str

    @classmethod
    def parse(
        cls,
        value: str,
        *,
        registry: MarketCodeRegistry = DEFAULT_MARKET_CODES,
    ) -> "CanonicalInstrumentReference":
        tokens = value.strip().split()
        if len(tokens) != 2:
            raise ValueError("instrument reference must use 'SYMBOL MARKET'")
        symbol = tokens[0].strip().upper()
        if not symbol:
            raise ValueError("instrument symbol cannot be empty")
        return cls(symbol=symbol, market_code=registry.normalize(tokens[1]))

    def __str__(self) -> str:
        return f"{self.symbol} {self.market_code}"
