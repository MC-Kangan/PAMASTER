import argparse
from collections.abc import Sequence

from pa_investing.brokers.ibkr_client_portal import IbkrClientPortalConnector
from pa_investing.brokers.ibkr_flex import IbkrFlexConnector
from pa_investing.core.config import Settings
from pa_investing.db.repositories import (
    AccountRepository,
    BrokerReconciliationRepository,
    MarketDataMappingRepository,
    PositionRepository,
    PriceRepository,
    ProviderRunRepository,
    TransactionRepository,
)
from pa_investing.db.session import DatabaseSessionFactory
from pa_investing.workflows.broker_import import BrokerImportResult, BrokerImportWorkflow


def run_ibkr_import(
    *,
    settings: Settings | None = None,
    session_factory: DatabaseSessionFactory | None = None,
    connector: object | None = None,
    workflow: BrokerImportWorkflow | None = None,
    verbose: bool = True,
) -> BrokerImportResult:
    if workflow is None:
        resolved_settings = settings or Settings()
        resolved_session_factory = session_factory or DatabaseSessionFactory(resolved_settings)
        resolved_connector = connector or _build_ibkr_connector(resolved_settings)

        with resolved_session_factory.session() as session:
            workflow = BrokerImportWorkflow(
                connector=resolved_connector,
                account_repository=AccountRepository(session),
                position_repository=PositionRepository(session),
                price_repository=PriceRepository(session),
                transaction_repository=TransactionRepository(session),
                reconciliation_repository=BrokerReconciliationRepository(session),
                provider_run_repository=ProviderRunRepository(session),
                market_data_mapping_repository=MarketDataMappingRepository(session),
                commit=session.commit,
                rollback=getattr(session, "rollback", None),
            )
            result = workflow.run()
    else:
        result = workflow.run()

    if verbose:
        print(
            "IBKR import completed: "
            f"accounts={result.accounts_imported} "
            f"positions={result.positions_imported} "
            f"closed={result.positions_closed} "
            f"skipped={len(result.skipped_positions)} "
            f"transactions={result.transactions_imported} "
            f"market_data_mappings={result.market_data_mappings_imported} "
            f"reconciliations={result.reconciliations_imported} "
            f"reconciliation_warnings={result.reconciliation_warnings}"
        )
        for skipped in result.skipped_positions:
            print(
                f"- skipped {skipped['account_id']} {skipped['symbol']}: {skipped['reason']}"
            )
        print(
            f"Cost basis: available={result.cost_basis_available} "
            f"missing={result.cost_basis_missing}"
        )
        if result.missing_cost_basis_positions:
            for missing in result.missing_cost_basis_positions:
                print(
                    f"- missing cost basis {missing['account_id']} {missing['symbol']}"
                )
    return result


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-url", default=None)
    parser.add_argument(
        "--source",
        choices=("auto", "flex", "gateway"),
        default="auto",
        help="Broker API source. auto uses Flex when token and query id are configured.",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    if args.gateway_url:
        settings = settings.model_copy(update={"ibkr_gateway_base_url": args.gateway_url})
    if args.source == "gateway":
        settings = settings.model_copy(update={"ibkr_flex_token": "", "ibkr_flex_query_id": ""})
    if args.source == "flex" and not (
        settings.ibkr_flex_token and settings.ibkr_flex_query_id
    ):
        raise RuntimeError(
            "IBKR Flex import requires PA_IBKR_FLEX_TOKEN and PA_IBKR_FLEX_QUERY_ID"
        )
    run_ibkr_import(settings=settings)


def _build_ibkr_connector(settings: Settings) -> object:
    if settings.ibkr_flex_token and settings.ibkr_flex_query_id:
        return IbkrFlexConnector(
            token=settings.ibkr_flex_token,
            query_id=settings.ibkr_flex_query_id,
            base_url=settings.ibkr_flex_base_url,
            report_timezone=settings.ibkr_flex_timezone,
        )
    return IbkrClientPortalConnector(base_url=settings.ibkr_gateway_base_url)


if __name__ == "__main__":
    main()
