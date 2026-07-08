from pa_investing.domain.models import Signal
from pa_investing.notion.client import NotionClient
from pa_investing.notion.schemas import NotionPagePayload


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
