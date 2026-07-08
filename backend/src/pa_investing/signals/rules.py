from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from pa_investing.domain.enums import SignalSeverity, SignalStatus, SignalType
from pa_investing.domain.models import Position, Signal
from pa_investing.sizing.models import MaxNavWeightSizingModel


class StopReferenceRule:
    def __init__(self, sizing_model: MaxNavWeightSizingModel) -> None:
        self.sizing_model = sizing_model

    def evaluate(
        self,
        position: Position,
        stop_price: Decimal,
        portfolio_nav: Decimal,
    ) -> Signal | None:
        if position.latest_price is None or position.latest_price > stop_price:
            return None

        sizing = self.sizing_model.recommend_reduction(
            position=position,
            portfolio_nav=portfolio_nav,
        )
        symbol = position.instrument.symbol
        return Signal(
            signal_id=f"sig-{uuid4().hex}",
            symbol=symbol,
            signal_type=SignalType.STOP_REFERENCE,
            severity=SignalSeverity.HIGH,
            status=SignalStatus.OPEN,
            message=(
                f"{symbol} price {position.latest_price} breached "
                f"stop/reference level {stop_price}."
            ),
            deterministic_recommendation=sizing.message,
            audit_id=f"audit-{uuid4().hex}",
            created_at=datetime.now(tz=UTC),
            analytics_path=f"/analysis/signal/{symbol}",
        )
