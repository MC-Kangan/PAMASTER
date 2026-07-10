from decimal import Decimal

from pa_investing.audit.events import AuditEvent
from pa_investing.db.repositories import (
    AuditEventRepository,
    PortfolioSnapshotRepository,
    SignalRepository,
)
from pa_investing.domain.models import Position
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.agent_api import AgentAPI, DailyReviewResult


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
    ) -> None:
        self.notion_sync = notion_sync
        self.persistence = persistence
        self.agent_api = AgentAPI()

    def run(
        self,
        positions: list[Position],
        stop_prices: dict[str, Decimal],
        *,
        sync_signals: bool = True,
    ) -> DailyReviewResult:
        result = self.agent_api.run_daily_review(positions=positions, stop_prices=stop_prices)
        if self.persistence is not None:
            self.persistence.persist(result)
        if sync_signals:
            self.sync_signals(result)
        return result

    def sync_signals(self, result: DailyReviewResult) -> None:
        for signal in result.signals:
            self.notion_sync.sync_signal(signal)
