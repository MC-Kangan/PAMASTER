from collections.abc import Callable
from dataclasses import dataclass

from pa_investing.core.config import Settings
from pa_investing.db.session import DatabaseSessionFactory
from pa_investing.scripts.import_ibkr_history import import_ibkr_history
from pa_investing.scripts.import_ibkr_positions import run_ibkr_import
from pa_investing.workflows.agent_api import DailyReviewResult
from pa_investing.workflows.broker_import import BrokerImportResult
from pa_investing.workflows.refresh_and_sync import RefreshAndSyncWorkflow


@dataclass(frozen=True)
class IbkrHistoryImportResult:
    accounts_imported: int
    snapshots_imported: int
    nav_points_imported: int
    pnl_points_imported: int


@dataclass(frozen=True)
class FullRefreshResult:
    position_import: BrokerImportResult
    history_import: IbkrHistoryImportResult
    dashboard_refresh: DailyReviewResult


class FullRefreshError(RuntimeError):
    def __init__(self, stage: str, error: Exception) -> None:
        self.stage = stage
        self.original_error = error
        super().__init__(str(error))


PositionImporter = Callable[..., BrokerImportResult]
HistoryImporter = Callable[..., tuple[int, int, int, int]]


class FullRefreshWorkflow:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: DatabaseSessionFactory,
        refresh_and_sync_workflow: RefreshAndSyncWorkflow,
        position_importer: PositionImporter = run_ibkr_import,
        history_importer: HistoryImporter = import_ibkr_history,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.refresh_and_sync_workflow = refresh_and_sync_workflow
        self.position_importer = position_importer
        self.history_importer = history_importer

    def run(self) -> FullRefreshResult:
        try:
            position_import = self.position_importer(
                settings=self.settings,
                session_factory=self.session_factory,
                verbose=False,
            )
        except Exception as error:
            raise FullRefreshError("ibkr_positions", error) from error

        try:
            history_counts = self.history_importer(
                settings=self.settings,
                session_factory=self.session_factory,
            )
        except Exception as error:
            raise FullRefreshError("ibkr_history", error) from error

        try:
            dashboard_refresh = self.refresh_and_sync_workflow.run(stop_prices={})
        except Exception as error:
            raise FullRefreshError("dashboard_refresh", error) from error

        return FullRefreshResult(
            position_import=position_import,
            history_import=IbkrHistoryImportResult(*history_counts),
            dashboard_refresh=dashboard_refresh,
        )
