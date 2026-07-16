from collections.abc import Sequence
from contextlib import suppress
from decimal import Decimal
from typing import Protocol, Self

from pydantic import (
    BaseModel,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from pa_investing.db.models import (
    InstrumentIdentifierRecord,
    InstrumentRecord,
    MarketDataMappingRecord,
)
from pa_investing.db.repositories import HistoricalDataRepository
from pa_investing.domain.enums import InstrumentScope
from pa_investing.instruments.market_codes import (
    DEFAULT_MARKET_CODES,
    CanonicalInstrumentReference,
)
from pa_investing.market_data.history.models import HistoricalInstrumentRef


class InstrumentCandidate(BaseModel):
    display_symbol: str
    name: str
    asset_class: str
    currency: str
    exchange: str | None
    mic_code: str | None = None
    provider_symbols: dict[str, str] = Field(default_factory=dict)
    provider_exchanges: dict[str, str] = Field(default_factory=dict)
    provider_currencies: dict[str, str] = Field(default_factory=dict)
    provider_price_multipliers: dict[str, Decimal] = Field(default_factory=dict)
    provider_ids: dict[str, str] = Field(default_factory=dict)
    confidence: Decimal

    def market_code(self) -> str | None:
        return DEFAULT_MARKET_CODES.market_for_exchange(
            self.exchange
        ) or DEFAULT_MARKET_CODES.market_for_exchange(self.mic_code)

    def listing_identity(self) -> str | None:
        return DEFAULT_MARKET_CODES.listing_identity(
            self.exchange,
            self.mic_code,
        )

    @computed_field
    @property
    def canonical_reference(self) -> str:
        market_code = self.market_code()
        if market_code is None:
            return self.display_symbol
        return str(
            CanonicalInstrumentReference(
                symbol=self.display_symbol,
                market_code=market_code,
            )
        )

    @field_validator("display_symbol", "currency")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("exchange", "mic_code")
    @classmethod
    def normalize_optional_identity(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class InstrumentSearchResult(BaseModel):
    query: str
    candidates: list[InstrumentCandidate]
    unambiguous: bool

    @model_validator(mode="after")
    def validate_unambiguous_flag(self) -> Self:
        if self.unambiguous != (len(self.candidates) == 1):
            raise ValueError("unambiguous must be true only for one candidate")
        return self


class InstrumentSearcher(Protocol):
    def search(self, query: str) -> list[InstrumentCandidate]: ...


class InstrumentResolutionService:
    def __init__(
        self,
        *,
        session: Session | None,
        searchers: Sequence[InstrumentSearcher] = (),
    ) -> None:
        self.session = session
        self.searchers = tuple(searchers)

    def for_portfolio(self, instrument_id: str) -> HistoricalInstrumentRef:
        if self.session is None:
            raise RuntimeError("portfolio resolution requires a database session")
        instrument = self.session.get(InstrumentRecord, instrument_id)
        if instrument is None:
            raise KeyError(f"instrument not found: {instrument_id}")
        mappings = self.session.scalars(
            select(MarketDataMappingRecord)
            .where(
                MarketDataMappingRecord.instrument_id == instrument_id,
                MarketDataMappingRecord.enabled.is_(True),
            )
            .order_by(MarketDataMappingRecord.provider)
        ).all()
        identifiers = self.session.scalars(
            select(InstrumentIdentifierRecord).where(
                InstrumentIdentifierRecord.instrument_id == instrument_id
            )
        ).all()
        provider_symbols = {mapping.provider: mapping.provider_symbol for mapping in mappings}
        provider_exchanges = {
            mapping.provider: mapping.provider_exchange
            for mapping in mappings
            if mapping.provider_exchange
        }
        provider_currencies = {mapping.provider: mapping.expected_currency for mapping in mappings}
        provider_price_multipliers = {
            mapping.provider: mapping.price_multiplier for mapping in mappings
        }
        provider_ids: dict[str, str] = {}
        for identifier in identifiers:
            if identifier.provider == "ibkr" and identifier.identifier_type == "conid":
                provider_ids["ibkr_tws"] = f"conid:{identifier.value}"

        return HistoricalInstrumentRef(
            scope=InstrumentScope.PORTFOLIO,
            instrument_id=instrument.instrument_id,
            display_symbol=instrument.symbol,
            asset_class=instrument.asset_class,
            currency=instrument.currency,
            exchange=instrument.venue or None,
            provider_symbols=provider_symbols,
            provider_exchanges=provider_exchanges,
            provider_currencies=provider_currencies,
            provider_price_multipliers=provider_price_multipliers,
            provider_ids=provider_ids,
        )

    def search(self, query: str) -> InstrumentSearchResult:
        tokens = query.strip().upper().split()
        symbol_query = tokens[0] if tokens else ""
        exchange_filter = tokens[1] if len(tokens) > 1 else None
        market_filter: str | None = None
        if exchange_filter:
            with suppress(ValueError):
                market_filter = DEFAULT_MARKET_CODES.normalize(exchange_filter)
        merged: dict[tuple[str, str, str, str], InstrumentCandidate] = {}
        for searcher in self.searchers:
            for candidate in searcher.search(symbol_query or query):
                if symbol_query and candidate.display_symbol != symbol_query:
                    continue
                if exchange_filter:
                    if market_filter:
                        if candidate.market_code() != market_filter:
                            continue
                    elif candidate.exchange != exchange_filter:
                        continue
                key = (
                    candidate.display_symbol,
                    candidate.listing_identity() or "",
                    candidate.currency,
                    candidate.asset_class,
                )
                existing = merged.get(key)
                merged[key] = (
                    candidate
                    if existing is None
                    else existing.model_copy(
                        update={
                            "provider_symbols": {
                                **existing.provider_symbols,
                                **candidate.provider_symbols,
                            },
                            "provider_exchanges": {
                                **existing.provider_exchanges,
                                **candidate.provider_exchanges,
                            },
                            "provider_currencies": {
                                **existing.provider_currencies,
                                **candidate.provider_currencies,
                            },
                            "provider_price_multipliers": {
                                **existing.provider_price_multipliers,
                                **candidate.provider_price_multipliers,
                            },
                            "provider_ids": {
                                **existing.provider_ids,
                                **candidate.provider_ids,
                            },
                            "mic_code": existing.mic_code or candidate.mic_code,
                            "confidence": max(
                                existing.confidence,
                                candidate.confidence,
                            ),
                        }
                    )
                )
        candidates = sorted(
            merged.values(),
            key=lambda candidate: (
                -candidate.confidence,
                candidate.display_symbol,
                candidate.exchange or "",
                candidate.currency,
            ),
        )
        return InstrumentSearchResult(
            query=query,
            candidates=candidates,
            unambiguous=len(candidates) == 1,
        )

    @staticmethod
    def require_unambiguous(
        result: InstrumentSearchResult,
    ) -> InstrumentCandidate:
        if not result.unambiguous:
            raise ValueError("instrument resolution is ambiguous")
        return result.candidates[0]

    @staticmethod
    def to_research_ref(candidate: InstrumentCandidate) -> HistoricalInstrumentRef:
        return HistoricalInstrumentRef(
            scope=InstrumentScope.RESEARCH,
            display_symbol=candidate.display_symbol,
            asset_class=candidate.asset_class,
            currency=candidate.currency,
            exchange=candidate.exchange,
            provider_symbols=candidate.provider_symbols,
            provider_exchanges=candidate.provider_exchanges,
            provider_currencies=candidate.provider_currencies,
            provider_price_multipliers=candidate.provider_price_multipliers,
            provider_ids=candidate.provider_ids,
        )

    def promote_research_series(
        self,
        series_key: str,
        instrument_id: str,
    ) -> None:
        if self.session is None:
            raise RuntimeError("series promotion requires a database session")
        HistoricalDataRepository(self.session).promote_series(
            series_key=series_key,
            instrument_id=instrument_id,
        )
