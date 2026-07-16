from pa_investing.scripts.import_ibkr_positions import run_ibkr_import
from pa_investing.workflows.broker_import import BrokerImportResult


class StubConnector:
    pass


class StubWorkflow:
    def run(self) -> BrokerImportResult:
        return BrokerImportResult(
            accounts_imported=1,
            positions_imported=2,
            positions_closed=1,
            skipped_positions=[
                {
                    "account_id": "U1234567",
                    "symbol": "AAPL  260116C00200000",
                    "reason": "unsupported asset class: OPT",
                }
            ],
            cost_basis_available=1,
            cost_basis_missing=1,
            missing_cost_basis_positions=[
                {
                    "account_id": "U1234567",
                    "symbol": "MBGL",
                    "reason": "cost basis unavailable",
                }
            ],
        )


def test_run_ibkr_import_prints_summary(capsys) -> None:
    run_ibkr_import(
        connector=StubConnector(),
        workflow=StubWorkflow(),
    )

    captured = capsys.readouterr()

    assert "IBKR import completed: accounts=1 positions=2 closed=1 skipped=1" in captured.out
    assert "unsupported asset class: OPT" in captured.out
    assert "Cost basis: available=1 missing=1" in captured.out
    assert "missing cost basis U1234567 MBGL" in captured.out


def test_run_ibkr_import_uses_flex_connector_when_flex_credentials_are_configured(
    monkeypatch,
) -> None:
    captured_connector: object | None = None

    class StubSessionFactory:
        def session(self):
            raise AssertionError("session factory should not be used by this test")

    class StubIbkrFlexConnector:
        def __init__(self, *, token: str, query_id: str, base_url: str) -> None:
            self.token = token
            self.query_id = query_id
            self.base_url = base_url

    class StubBrokerImportWorkflow:
        def __init__(
            self,
            *,
            connector,
            account_repository,
            position_repository,
            price_repository,
            commit,
        ):
            nonlocal captured_connector
            captured_connector = connector

        def run(self) -> BrokerImportResult:
            return BrokerImportResult(
                accounts_imported=1,
                positions_imported=1,
                positions_closed=0,
                skipped_positions=[],
            )

    monkeypatch.setattr(
        "pa_investing.scripts.import_ibkr_positions.IbkrFlexConnector",
        StubIbkrFlexConnector,
    )
    monkeypatch.setattr(
        "pa_investing.scripts.import_ibkr_positions.BrokerImportWorkflow",
        StubBrokerImportWorkflow,
    )
    monkeypatch.setattr(
        "pa_investing.scripts.import_ibkr_positions.AccountRepository",
        lambda session: object(),
    )
    monkeypatch.setattr(
        "pa_investing.scripts.import_ibkr_positions.PriceRepository",
        lambda session: object(),
    )
    monkeypatch.setattr(
        "pa_investing.scripts.import_ibkr_positions.PositionRepository",
        lambda session: object(),
    )

    from pa_investing.core.config import Settings

    settings = Settings(
        ibkr_flex_token="test-token",
        ibkr_flex_query_id="12345",
        ibkr_flex_base_url="https://flex.example",
    )

    class UsableSessionFactory:
        class _SessionContext:
            def __enter__(self):
                class Session:
                    def commit(self):
                        return None

                return Session()

            def __exit__(self, exc_type, exc_value, traceback):
                return None

        def session(self):
            return self._SessionContext()

    run_ibkr_import(
        settings=settings,
        session_factory=UsableSessionFactory(),
    )

    assert isinstance(captured_connector, StubIbkrFlexConnector)
    assert captured_connector.token == "test-token"
    assert captured_connector.query_id == "12345"
    assert captured_connector.base_url == "https://flex.example"
