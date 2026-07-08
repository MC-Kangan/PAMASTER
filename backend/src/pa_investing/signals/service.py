from decimal import Decimal

from pa_investing.domain.models import Position, Signal
from pa_investing.signals.rules import StopReferenceRule


class SignalService:
    def __init__(self, stop_rule: StopReferenceRule) -> None:
        self.stop_rule = stop_rule

    def evaluate_stop_rules(
        self,
        positions: list[Position],
        stop_prices: dict[str, Decimal],
        portfolio_nav: Decimal,
    ) -> list[Signal]:
        signals: list[Signal] = []
        for position in positions:
            stop_price = stop_prices.get(position.instrument.symbol)
            if stop_price is None:
                continue
            signal = self.stop_rule.evaluate(
                position=position,
                stop_price=stop_price,
                portfolio_nav=portfolio_nav,
            )
            if signal is not None:
                signals.append(signal)
        return signals
