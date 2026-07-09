from decimal import Decimal

from pa_investing.domain.models import Signal
from pa_investing.notion.client import NotionClient
from pa_investing.notion.schemas import NotionPagePayload
from pa_investing.workflows.agent_api import DailyReviewResult


class NotionSync:
    def __init__(self, client: NotionClient) -> None:
        self.client = client

    def build_signal_payload(self, signal: Signal) -> NotionPagePayload:
        return NotionPagePayload(
            title=f"{signal.symbol} {signal.signal_type.value}",
            properties={
                "Symbol": signal.symbol,
                "Signal Type": signal.signal_type.value,
                "Severity": signal.severity.value,
                "Status": signal.status.value,
                "Recommendation": signal.deterministic_recommendation,
                "Audit ID": signal.audit_id,
                "Analytics Link": signal.analytics_path or "",
            },
            body=f"{signal.message}\n\nRecommendation: {signal.deterministic_recommendation}",
        )

    def sync_signal(self, signal: Signal) -> str:
        payload = self.build_signal_payload(signal)
        return self.client.upsert_page("Signals", signal.signal_id, payload)

    def build_daily_review_payload(self, result: DailyReviewResult) -> NotionPagePayload:
        snapshot = result.snapshot
        signal_lines = [
            f"- {signal.symbol}: {signal.deterministic_recommendation}"
            for signal in result.signals
        ]
        summary_lines = [
            f"Snapshot {snapshot.snapshot_id}",
            "",
            f"NAV: {self._format_decimal(snapshot.nav)}",
            f"Gross exposure: {self._format_decimal(snapshot.gross_exposure)}",
            f"Net exposure: {self._format_decimal(snapshot.net_exposure)}",
            f"Unrealized PnL: {self._format_decimal(snapshot.unrealized_pnl)}",
            "",
            "Signals:",
            *(
                signal_lines
                if signal_lines
                else ["- No signals generated."]
            ),
        ]
        return NotionPagePayload(
            title=f"Daily Review {snapshot.snapshot_id}",
            properties={
                "Snapshot ID": snapshot.snapshot_id,
                "NAV": self._format_decimal(snapshot.nav),
                "Gross Exposure": self._format_decimal(snapshot.gross_exposure),
                "Net Exposure": self._format_decimal(snapshot.net_exposure),
                "Unrealized PnL": self._format_decimal(snapshot.unrealized_pnl),
                "Signal Count": str(len(result.signals)),
            },
            body="\n".join(summary_lines),
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
        formatted = format(value, "f")
        if "." not in formatted:
            return formatted
        return formatted.rstrip("0").rstrip(".")
