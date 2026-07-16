import logging
from datetime import date
from decimal import Decimal
from typing import Protocol

from pa_investing.audit.events import AuditEvent
from pa_investing.db.repositories import (
    AuditEventRepository,
    PortfolioSnapshotRepository,
    SignalRepository,
)
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Position
from pa_investing.finance.models import AnalysisResult
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.agent_api import AgentAPI, DailyReviewResult, FinanceEvidence

logger = logging.getLogger(__name__)


class PortfolioFinanceAnalyzer(Protocol):
    def analyze_portfolio(
        self,
        instrument_id: str,
        *,
        as_of: date,
        lookback_days: int = 365,
        bundle: str = "daily_market_review.v1",
    ) -> AnalysisResult: ...


class DailyReviewPersistence:
    def __init__(
        self,
        audit_event_repository: AuditEventRepository,
        snapshot_repository: PortfolioSnapshotRepository,
        signal_repository: SignalRepository,
    ) -> None:
        self.audit_event_repository = audit_event_repository
        self.snapshot_repository = snapshot_repository
        self.signal_repository = signal_repository

    def persist(self, result: DailyReviewResult) -> None:
        self.snapshot_repository.upsert(result.snapshot)
        for signal in result.signals:
            self.audit_event_repository.upsert(
                AuditEvent(
                    audit_id=signal.audit_id,
                    event_type=signal.signal_type.value,
                    created_at=signal.created_at,
                    message=signal.message,
                )
            )
            self.signal_repository.upsert(signal)


class DailyReviewWorkflow:
    def __init__(
        self,
        notion_sync: NotionSync,
        persistence: DailyReviewPersistence | None = None,
        finance_analyzer: PortfolioFinanceAnalyzer | None = None,
    ) -> None:
        self.notion_sync = notion_sync
        self.persistence = persistence
        self.finance_analyzer = finance_analyzer
        self.agent_api = AgentAPI()

    def run(
        self,
        positions: list[Position],
        stop_prices: dict[str, Decimal],
        *,
        sync_signals: bool = True,
        base_currency: str = "USD",
    ) -> DailyReviewResult:
        result = self.agent_api.run_daily_review(
            positions=positions,
            stop_prices=stop_prices,
            base_currency=base_currency,
        )
        result.finance_evidence = self._collect_finance_evidence(result)
        if self.persistence is not None:
            self.persistence.persist(result)
        if sync_signals:
            self.sync_signals(result)
        return result

    def _collect_finance_evidence(
        self,
        result: DailyReviewResult,
    ) -> list[FinanceEvidence]:
        if self.finance_analyzer is None:
            return []
        evidence: list[FinanceEvidence] = []
        seen: set[str] = set()
        for position in result.positions:
            instrument = position.instrument
            instrument_id = instrument.instrument_id
            if (
                instrument_id is None
                or instrument_id in seen
                or instrument.asset_class not in {AssetClass.EQUITY, AssetClass.ETF}
            ):
                continue
            seen.add(instrument_id)
            try:
                analysis = self.finance_analyzer.analyze_portfolio(
                    instrument_id,
                    as_of=result.snapshot.observed_at.date(),
                    lookback_days=365,
                    bundle="daily_market_review.v1",
                )
            except Exception as exc:
                logger.warning(
                    "Finance analysis unavailable for %s: %s",
                    instrument.symbol,
                    exc,
                )
                evidence.append(
                    FinanceEvidence(
                        instrument_id=instrument_id,
                        symbol=instrument.symbol,
                        error=str(exc),
                    )
                )
                continue
            evidence.append(
                FinanceEvidence(
                    instrument_id=instrument_id,
                    symbol=instrument.symbol,
                    analysis=analysis,
                )
            )
        return evidence

    def sync_signals(self, result: DailyReviewResult) -> None:
        for signal in result.signals:
            self.notion_sync.sync_signal(signal)
