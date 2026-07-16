from decimal import Decimal
from math import sqrt

import pandas as pd

from pa_investing.market_data.history.models import DailyBar


def bars_frame(bars: list[DailyBar]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [float(bar.open) for bar in bars],
            "high": [float(bar.high) for bar in bars],
            "low": [float(bar.low) for bar in bars],
            "close": [float(bar.close) for bar in bars],
            "volume": [
                float(bar.volume) if bar.volume is not None else float("nan") for bar in bars
            ],
        },
        index=[bar.trading_date for bar in bars],
    )


def decimal_metric(value: float, digits: int = 8) -> Decimal:
    return Decimal(str(round(float(value), digits)))


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()
    average_loss = losses.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()
    relative_strength = average_gain / average_loss
    result = 100 - (100 / (1 + relative_strength))
    return result.mask(
        (average_loss == 0) & (average_gain > 0),
        100.0,
    ).mask(
        (average_loss == 0) & (average_gain == 0),
        50.0,
    )


def adx(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    high_change = frame["high"].diff()
    low_change = -frame["low"].diff()
    plus_dm = high_change.where(
        (high_change > low_change) & (high_change > 0),
        0.0,
    )
    minus_dm = low_change.where(
        (low_change > high_change) & (low_change > 0),
        0.0,
    )
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        (
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ),
        axis=1,
    ).max(axis=1)
    average_true_range = true_range.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()
    plus_di = (
        100
        * plus_dm.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()
        / average_true_range
    )
    minus_di = (
        100
        * minus_dm.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()
        / average_true_range
    )
    denominator = (plus_di + minus_di).replace(0, float("nan"))
    directional_index = 100 * (plus_di - minus_di).abs() / denominator
    return directional_index.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()


def annualized_volatility(
    close: pd.Series,
    period: int = 20,
) -> float:
    returns = close.pct_change().dropna().tail(period)
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * sqrt(252))
