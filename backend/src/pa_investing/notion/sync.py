from decimal import Decimal

from pa_investing.analytics.metrics import calculate_exposure_by_asset_class
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Position, Signal
from pa_investing.notion.client import NotionClient
from pa_investing.notion.schemas import NotionPagePayload, NotionPropertyValue
from pa_investing.presentation.fields import serialize_decimal
from pa_investing.workflows.agent_api import DailyReviewResult


class NotionSync:
    def __init__(self, client: NotionClient) -> None:
        self.client = client

    def build_signal_payload(self, signal: Signal) -> NotionPagePayload:
        return NotionPagePayload(
            title=(
                f"{signal.symbol} {self._humanize_token(signal.signal_type.value)} "
                f"{self._humanize_token(signal.severity.value)}"
            ),
            properties={
                "Symbol": NotionPropertyValue.rich_text(signal.symbol),
                "Signal Type": NotionPropertyValue.select(signal.signal_type.value),
                "Severity": NotionPropertyValue.select(signal.severity.value),
                "Status": NotionPropertyValue.status(signal.status.value),
                "Recommendation": NotionPropertyValue.rich_text(
                    signal.deterministic_recommendation
                ),
                "Audit ID": NotionPropertyValue.rich_text(signal.audit_id),
                **(
                    {"Analytics Link": NotionPropertyValue.url(signal.analytics_path)}
                    if signal.analytics_path
                    else {}
                ),
            },
            body=self._build_signal_body(signal),
        )

    def sync_signal(self, signal: Signal) -> str:
        payload = self.build_signal_payload(signal)
        return self.client.upsert_page("Signals", signal.signal_id, payload)

    def build_daily_review_payload(self, result: DailyReviewResult) -> NotionPagePayload:
        snapshot = result.snapshot
        return NotionPagePayload(
            title=f"Daily Review {snapshot.observed_at.date().isoformat()}",
            properties={
                "Review Date": NotionPropertyValue.date(snapshot.observed_at.date()),
                "Snapshot ID": NotionPropertyValue.rich_text(snapshot.snapshot_id),
                "NAV": NotionPropertyValue.number(snapshot.nav),
                "Gross Exposure": NotionPropertyValue.number(snapshot.gross_exposure),
                "Net Exposure": NotionPropertyValue.number(snapshot.net_exposure),
                "Unrealized PnL": NotionPropertyValue.number(snapshot.unrealized_pnl),
                "Signal Count": NotionPropertyValue.number(len(result.signals)),
            },
            body=self._build_daily_review_body(result),
        )

    def sync_daily_review(
        self,
        result: DailyReviewResult,
        external_id: str | None = None,
    ) -> str:
        payload = self.build_daily_review_payload(result)
        return self.client.upsert_page(
            "Daily Review",
            external_id or result.snapshot.snapshot_id,
            payload,
        )

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return serialize_decimal(value)

    @classmethod
    def _build_signal_body(cls, signal: Signal) -> str:
        lines = [
            "Action",
            f"- Recommendation: {signal.deterministic_recommendation}",
            "",
            "Signal",
            f"- Symbol: {signal.symbol}",
            f"- Type: {cls._humanize_token(signal.signal_type.value)}",
            f"- Severity: {cls._humanize_token(signal.severity.value)}",
            f"- Status: {cls._humanize_token(signal.status.value)}",
            "",
            "Context",
            f"- {signal.message}",
            "",
            "Audit",
            f"- Audit ID: {signal.audit_id}",
        ]
        if signal.analytics_path:
            lines.append(f"- Analytics: {signal.analytics_path}")
        return "\n".join(lines)

    @classmethod
    def _build_daily_review_body(cls, result: DailyReviewResult) -> str:
        snapshot = result.snapshot
        lines = [
            "Overview",
            f"- Snapshot Time: {snapshot.observed_at.isoformat()}",
            f"- Snapshot ID: {snapshot.snapshot_id}",
            f"- Signal Count: {len(result.signals)}",
            "",
            "Portfolio",
            f"- NAV: {cls._format_decimal(snapshot.nav)}",
            f"- Gross Exposure: {cls._format_decimal(snapshot.gross_exposure)}",
            f"- Net Exposure: {cls._format_decimal(snapshot.net_exposure)}",
            f"- Unrealized PnL: {cls._format_decimal(snapshot.unrealized_pnl)}",
            "",
            "Allocation",
            *cls._allocation_lines(result.positions, snapshot.nav),
            "",
            "Top Holdings",
            *cls._top_holding_lines(result.positions, snapshot.nav),
            "",
            "Signals",
            *cls._signal_summary_lines(result),
            "",
            "Next",
            "- News overview section reserved for a future agent pass.",
        ]
        return "\n".join(lines)

    @classmethod
    def _allocation_lines(
        cls,
        positions: list[Position],
        portfolio_nav: Decimal,
    ) -> list[str]:
        if portfolio_nav == 0:
            return ["- No allocation available."]
        exposure_by_asset_class = calculate_exposure_by_asset_class(positions)
        ordered_asset_classes = sorted(
            exposure_by_asset_class.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        return [
            f"- {cls._asset_class_label(asset_class)}: "
            f"{cls._format_percent(exposure / portfolio_nav)}"
            for asset_class, exposure in ordered_asset_classes
        ]

    @classmethod
    def _top_holding_lines(
        cls,
        positions: list[Position],
        portfolio_nav: Decimal,
        *,
        limit: int = 5,
    ) -> list[str]:
        if portfolio_nav == 0 or not positions:
            return ["- No holdings available."]
        ranked_positions = sorted(
            positions,
            key=lambda position: abs(position.market_value),
            reverse=True,
        )[:limit]
        return [
            (
                f"- {position.instrument.symbol} "
                f"({cls._asset_class_label(position.instrument.asset_class)}, "
                f"{position.instrument.currency}) - "
                f"{cls._format_percent(abs(position.market_value) / portfolio_nav)} "
                "of portfolio"
            )
            for position in ranked_positions
        ]

    @classmethod
    def _signal_summary_lines(cls, result: DailyReviewResult) -> list[str]:
        if not result.signals:
            return ["- No signals generated."]
        return [
            f"- {signal.symbol}: {signal.deterministic_recommendation}"
            for signal in result.signals
        ]

    @staticmethod
    def _humanize_token(value: str) -> str:
        return value.replace("_", " ").title()

    @staticmethod
    def _asset_class_label(asset_class: AssetClass) -> str:
        if asset_class == AssetClass.ETF:
            return asset_class.value.upper()
        return asset_class.value.title()

    @staticmethod
    def _format_percent(value: Decimal) -> str:
        return f"{(value * Decimal('100')).quantize(Decimal('0.1'))}%"
