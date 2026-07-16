from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, Field

from pa_investing.analytics.snapshots import build_portfolio_snapshot
from pa_investing.domain.models import PortfolioSnapshot, Position, Signal
from pa_investing.finance.models import AnalysisResult
from pa_investing.signals.rules import StopReferenceRule
from pa_investing.signals.service import SignalService
from pa_investing.sizing.models import MaxNavWeightSizingModel


class FinanceEvidence(BaseModel):
    instrument_id: str
    symbol: str
    analysis: AnalysisResult | None = None
    error: str | None = None


class DailyReviewResult(BaseModel):
    snapshot: PortfolioSnapshot
    positions: list[Position]
    signals: list[Signal]
    previous_daily_snapshot: PortfolioSnapshot | None = None
    finance_evidence: list[FinanceEvidence] = Field(default_factory=list)


class AgentAPI:
    def __init__(self) -> None:
        sizing_model = MaxNavWeightSizingModel(max_weight=Decimal("0.10"))
        self.signal_service = SignalService(stop_rule=StopReferenceRule(sizing_model=sizing_model))

    def run_daily_review(
        self,
        positions: list[Position],
        stop_prices: dict[str, Decimal],
        base_currency: str = "USD",
    ) -> DailyReviewResult:
        snapshot = build_portfolio_snapshot(
            snapshot_id=f"snap-{uuid4().hex}",
            positions=positions,
            observed_at=datetime.now(tz=UTC),
            base_currency=base_currency,
        )
        signals = self.signal_service.evaluate_stop_rules(
            positions=positions,
            stop_prices=stop_prices,
            portfolio_nav=snapshot.nav,
        )
        return DailyReviewResult(
            snapshot=snapshot,
            positions=positions,
            signals=signals,
        )
