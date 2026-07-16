from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pa_investing.analytics.performance import (
    build_performance_history,
    latest_snapshot_per_day,
)
from pa_investing.db.base import Base
from pa_investing.db.repositories import PortfolioSnapshotRepository
from pa_investing.domain.models import PortfolioSnapshot


def test_build_performance_history_calculates_peak_drawdown_and_return() -> None:
    history = build_performance_history(
        [
            _snapshot("snap-1", "2026-07-10T00:00:00+00:00", nav="1000", pnl="0"),
            _snapshot("snap-2", "2026-07-10T06:00:00+00:00", nav="1200", pnl="200"),
            _snapshot("snap-3", "2026-07-10T12:00:00+00:00", nav="900", pnl="-100"),
        ]
    )

    assert history.starting_nav == Decimal("1000")
    assert history.ending_nav == Decimal("900")
    assert history.simple_return == Decimal("-0.1")
    assert history.max_drawdown == Decimal("-0.25")
    assert [point.peak_nav for point in history.points] == [
        Decimal("1000"),
        Decimal("1200"),
        Decimal("1200"),
    ]
    assert [point.drawdown for point in history.points] == [
        Decimal("0"),
        Decimal("0"),
        Decimal("-0.25"),
    ]
    assert [point.simple_return for point in history.points] == [
        Decimal("0"),
        Decimal("0.2"),
        Decimal("-0.1"),
    ]


def test_build_performance_history_handles_single_snapshot() -> None:
    history = build_performance_history(
        [
            _snapshot("snap-1", "2026-07-10T00:00:00+00:00", nav="1000", pnl="25"),
        ]
    )

    assert history.starting_nav == Decimal("1000")
    assert history.ending_nav == Decimal("1000")
    assert history.simple_return == Decimal("0")
    assert history.max_drawdown == Decimal("0")
    assert len(history.points) == 1
    assert history.points[0].drawdown == Decimal("0")
    assert history.points[0].simple_return == Decimal("0")


def test_latest_snapshot_per_day_keeps_last_refresh_for_each_day() -> None:
    snapshots = [
        _snapshot("morning", "2026-07-10T06:00:00+00:00", nav="900", pnl="0"),
        _snapshot("evening", "2026-07-10T18:00:00+00:00", nav="1000", pnl="10"),
        _snapshot("next-day", "2026-07-11T06:00:00+00:00", nav="1010", pnl="20"),
    ]

    result = latest_snapshot_per_day(snapshots)

    assert [snapshot.snapshot_id for snapshot in result] == ["evening", "next-day"]


def test_build_performance_history_handles_empty_history() -> None:
    history = build_performance_history([])

    assert history.points == []
    assert history.starting_nav is None
    assert history.ending_nav is None
    assert history.simple_return is None
    assert history.max_drawdown is None


def test_portfolio_snapshot_repository_lists_history_in_time_order() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        repository = PortfolioSnapshotRepository(session)
        repository.upsert(_snapshot("snap-2", "2026-07-10T06:00:00+00:00", nav="1100", pnl="100"))
        repository.upsert(_snapshot("snap-1", "2026-07-10T00:00:00+00:00", nav="1000", pnl="0"))
        repository.upsert(_snapshot("snap-3", "2026-07-10T12:00:00+00:00", nav="900", pnl="-100"))
        session.commit()

        history = repository.list_history()

    assert [snapshot.snapshot_id for snapshot in history] == ["snap-1", "snap-2", "snap-3"]


def test_portfolio_snapshot_repository_filters_history_by_days() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)

    with session_factory() as session:
        repository = PortfolioSnapshotRepository(session)
        repository.upsert(
            PortfolioSnapshot(
                snapshot_id="snap-old",
                observed_at=now - timedelta(days=10),
                base_currency="USD",
                nav=Decimal("800"),
                gross_exposure=Decimal("800"),
                net_exposure=Decimal("800"),
                unrealized_pnl=Decimal("-200"),
            )
        )
        repository.upsert(
            PortfolioSnapshot(
                snapshot_id="snap-new",
                observed_at=now - timedelta(days=1),
                base_currency="USD",
                nav=Decimal("1000"),
                gross_exposure=Decimal("1000"),
                net_exposure=Decimal("1000"),
                unrealized_pnl=Decimal("0"),
            )
        )
        session.commit()

        history = repository.list_history(days=2, now=now)

    assert [snapshot.snapshot_id for snapshot in history] == ["snap-new"]


def _snapshot(snapshot_id: str, observed_at: str, nav: str, pnl: str) -> PortfolioSnapshot:
    nav_decimal = Decimal(nav)
    return PortfolioSnapshot(
        snapshot_id=snapshot_id,
        observed_at=datetime.fromisoformat(observed_at),
        base_currency="USD",
        nav=nav_decimal,
        gross_exposure=nav_decimal,
        net_exposure=nav_decimal,
        unrealized_pnl=Decimal(pnl),
    )
