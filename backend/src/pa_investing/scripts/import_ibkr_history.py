import argparse
from collections.abc import Sequence
from pathlib import Path
from xml.etree import ElementTree

from pa_investing.brokers.ibkr_flex import IbkrFlexConnector
from pa_investing.brokers.ibkr_flex_history import (
    IbkrFlexHistory,
    parse_ibkr_flex_history_file,
    parse_ibkr_flex_history_root,
)
from pa_investing.core.config import Settings
from pa_investing.db.repositories import (
    AccountRepository,
    BrokerDailyNavRepository,
    BrokerDailyPnlRepository,
    PortfolioSnapshotRepository,
)
from pa_investing.db.session import DatabaseSessionFactory


def import_ibkr_history(
    path: str | Path | None = None,
    *,
    settings: Settings | None = None,
    session_factory: DatabaseSessionFactory | None = None,
    connector: IbkrFlexConnector | None = None,
    allow_empty: bool = False,
    save_raw_xml: str | Path | None = None,
) -> tuple[int, int, int, int]:
    resolved_settings = settings or Settings()
    history = _load_history(path, resolved_settings, connector, save_raw_xml)
    resolved_session_factory = session_factory or DatabaseSessionFactory(
        resolved_settings
    )
    snapshots = history.to_portfolio_snapshots()
    daily_nav = history.to_broker_daily_nav()
    daily_pnl = history.to_broker_daily_pnl()
    if not allow_empty and not snapshots and not daily_nav and not daily_pnl:
        source = str(path) if path is not None else "IBKR Flex Web Service"
        raise RuntimeError(
            "IBKR history import returned no daily history rows from "
            f"{source}. Check that PA_IBKR_FLEX_HISTORY_QUERY_ID points to the "
            "saved daily history query, XML output is enabled, and the query "
            "period includes available report dates."
        )
    with resolved_session_factory.session() as session:
        account_repository = AccountRepository(session)
        nav_repository = BrokerDailyNavRepository(session)
        pnl_repository = BrokerDailyPnlRepository(session)
        snapshot_repository = PortfolioSnapshotRepository(session)
        for account in history.accounts:
            account_repository.upsert(account)
        for snapshot in snapshots:
            snapshot_repository.upsert(snapshot)
        for point in daily_nav:
            nav_repository.upsert(point)
        for point in daily_pnl:
            pnl_repository.upsert(point)
        session.commit()
    return len(history.accounts), len(snapshots), len(daily_nav), len(daily_pnl)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        help=(
            "Optional path to an IBKR Activity Flex XML export. "
            "When omitted, fetches PA_IBKR_FLEX_HISTORY_QUERY_ID via Flex Web Service."
        ),
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Treat an empty IBKR history response as a successful no-op.",
    )
    parser.add_argument(
        "--save-raw-xml",
        default=None,
        help="Save the raw fetched IBKR Flex XML before importing.",
    )
    args = parser.parse_args(argv)
    account_count, snapshot_count, nav_count, pnl_count = import_ibkr_history(
        args.path,
        allow_empty=args.allow_empty,
        save_raw_xml=args.save_raw_xml,
    )
    print(
        "IBKR history import completed: "
        f"accounts={account_count} snapshots={snapshot_count} "
        f"nav_points={nav_count} pnl_points={pnl_count}"
    )


def _load_history(
    path: str | Path | None,
    settings: Settings,
    connector: IbkrFlexConnector | None,
    save_raw_xml: str | Path | None,
) -> IbkrFlexHistory:
    if path is not None:
        history = parse_ibkr_flex_history_file(path)
        if save_raw_xml is not None:
            Path(save_raw_xml).write_text(Path(path).read_text(), encoding="utf-8")
        return history
    resolved_connector = connector or _build_history_connector(settings)
    root = resolved_connector.fetch_statement_root()
    if save_raw_xml is not None:
        ElementTree.ElementTree(root).write(
            save_raw_xml,
            encoding="utf-8",
            xml_declaration=True,
        )
    return parse_ibkr_flex_history_root(root)


def _build_history_connector(settings: Settings) -> IbkrFlexConnector:
    if not settings.ibkr_flex_token:
        raise RuntimeError("IBKR history import requires PA_IBKR_FLEX_TOKEN")
    if not settings.ibkr_flex_history_query_id:
        raise RuntimeError(
            "IBKR history import requires PA_IBKR_FLEX_HISTORY_QUERY_ID"
        )
    return IbkrFlexConnector(
        token=settings.ibkr_flex_token,
        query_id=settings.ibkr_flex_history_query_id,
        base_url=settings.ibkr_flex_base_url,
    )


if __name__ == "__main__":
    main()
