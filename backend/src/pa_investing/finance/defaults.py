from pa_investing.finance.registry import SkillRegistry
from pa_investing.finance.skills import (
    CandlestickEventsSkill,
    MarketRiskSnapshotSkill,
    TechnicalSnapshotSkill,
)


def build_default_finance_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(TechnicalSnapshotSkill())
    registry.register(CandlestickEventsSkill())
    registry.register(MarketRiskSnapshotSkill())
    registry.register_bundle(
        "daily_market_review.v1",
        (
            "technical_snapshot.v1",
            "candlestick_events.v1",
            "market_risk_snapshot.v1",
        ),
    )
    return registry
