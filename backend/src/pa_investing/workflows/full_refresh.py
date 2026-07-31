from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from pa_investing.core.config import Settings
from pa_investing.db.repositories import AppSettingRepository
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


@dataclass(frozen=True)
class PositionRefreshResult:
    position_import: BrokerImportResult
    dashboard_refresh: DailyReviewResult


class FullRefreshError(RuntimeError):
    def __init__(self, stage: str, error: Exception) -> None:
        self.stage = stage
        self.original_error = error
        super().__init__(str(error))


class FullRefreshCooldownError(FullRefreshError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            "ibkr_cooldown",
            RuntimeError(
                "IBKR refresh was requested recently. "
                f"Please try again in about {retry_after_seconds} seconds."
            ),
        )


PositionImporter = Callable[..., BrokerImportResult]
HistoryImporter = Callable[..., tuple[int, int, int, int]]
Clock = Callable[[], datetime]

LAST_ATTEMPTED_AT_KEY = "ibkr_full_refresh_last_attempted_at"
LAST_COMPLETED_AT_KEY = "ibkr_full_refresh_last_completed_at"
LAST_POSITIONS_COMPLETED_AT_KEY = "ibkr_positions_refresh_last_completed_at"
LAST_HISTORY_COMPLETED_AT_KEY = "ibkr_history_refresh_last_completed_at"


class FullRefreshWorkflow:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: DatabaseSessionFactory,
        refresh_and_sync_workflow: RefreshAndSyncWorkflow,
        position_importer: PositionImporter = run_ibkr_import,
        history_importer: HistoryImporter = import_ibkr_history,
        clock: Clock | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.refresh_and_sync_workflow = refresh_and_sync_workflow
        self.position_importer = position_importer
        self.history_importer = history_importer
        self.clock = clock or (lambda: datetime.now(tz=UTC))

    def run(self) -> FullRefreshResult:
        self._record_attempt_or_raise_cooldown()
        position_import = self._import_positions()
        history_import = self._import_history()
        dashboard_refresh = self._refresh_dashboard()
        self._record_success(
            extra_keys=(
                LAST_POSITIONS_COMPLETED_AT_KEY,
                LAST_HISTORY_COMPLETED_AT_KEY,
            )
        )
        return FullRefreshResult(
            position_import=position_import,
            history_import=history_import,
            dashboard_refresh=dashboard_refresh,
        )

    def run_positions(self) -> PositionRefreshResult:
        self._record_attempt_or_raise_cooldown()
        position_import = self._import_positions()
        dashboard_refresh = self._refresh_dashboard()
        self._record_success(extra_keys=(LAST_POSITIONS_COMPLETED_AT_KEY,))
        return PositionRefreshResult(
            position_import=position_import,
            dashboard_refresh=dashboard_refresh,
        )

    def run_history(self) -> IbkrHistoryImportResult:
        self._record_attempt_or_raise_cooldown()
        history_import = self._import_history()
        self._record_success(extra_keys=(LAST_HISTORY_COMPLETED_AT_KEY,))
        return history_import

    def _import_positions(self) -> BrokerImportResult:
        try:
            return self.position_importer(
                settings=self.settings,
                session_factory=self.session_factory,
                verbose=False,
            )
        except Exception as error:
            raise FullRefreshError("ibkr_positions", error) from error

    def _import_history(self) -> IbkrHistoryImportResult:
        try:
            history_counts = self.history_importer(
                settings=self.settings,
                session_factory=self.session_factory,
            )
        except Exception as error:
            raise FullRefreshError("ibkr_history", error) from error
        return IbkrHistoryImportResult(*history_counts)

    def _refresh_dashboard(self) -> DailyReviewResult:
        try:
            return self.refresh_and_sync_workflow.run(stop_prices={})
        except Exception as error:
            raise FullRefreshError("dashboard_refresh", error) from error

    def _record_attempt_or_raise_cooldown(self) -> None:
        cooldown_seconds = max(0, self.settings.ibkr_flex_refresh_cooldown_seconds)
        if cooldown_seconds == 0:
            return
        now = _normalize_utc(self.clock())
        with self.session_factory.session() as session:
            repository = AppSettingRepository(session)
            last_attempted_at = _parse_timestamp(
                repository.get(LAST_ATTEMPTED_AT_KEY)
            )
            if last_attempted_at is not None and cooldown_seconds > 0:
                elapsed_seconds = int((now - last_attempted_at).total_seconds())
                if elapsed_seconds < cooldown_seconds:
                    raise FullRefreshCooldownError(cooldown_seconds - elapsed_seconds)

            repository.set(LAST_ATTEMPTED_AT_KEY, now.isoformat())
            session.commit()

    def _record_success(self, *, extra_keys: tuple[str, ...] = ()) -> None:
        if self.settings.ibkr_flex_refresh_cooldown_seconds <= 0:
            return
        with self.session_factory.session() as session:
            repository = AppSettingRepository(session)
            completed_at = _normalize_utc(self.clock()).isoformat()
            repository.set(LAST_COMPLETED_AT_KEY, completed_at)
            for key in extra_keys:
                repository.set(key, completed_at)
            session.commit()


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _normalize_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
