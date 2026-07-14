from decimal import Decimal

import httpx
import pytest

from pa_investing.brokers.ibkr_client_portal import IbkrClientPortalConnector
from pa_investing.domain.enums import AssetClass


def test_ibkr_connector_lists_accounts_and_fetches_supported_positions() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == "https://127.0.0.1:5000/v1/api/portfolio/accounts":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "U1234567",
                        "accountTitle": "Primary IBKR",
                        "currency": "USD",
                    }
                ],
            )
        if (
            str(request.url)
            == "https://127.0.0.1:5000/v1/api/portfolio/U1234567/positions/0"
        ):
            return httpx.Response(
                200,
                json=[
                    {
                        "acctId": "U1234567",
                        "conid": 265598,
                        "contractDesc": "SPGI",
                        "description": "S&P Global Inc.",
                        "assetClass": "STK",
                        "position": 10,
                        "avgCost": 420.5,
                        "mktPrice": 510.25,
                    },
                    {
                        "acctId": "U1234567",
                        "conid": 756733,
                        "contractDesc": "SGLN",
                        "description": "iShares Physical Gold ETC",
                        "assetClass": "STK",
                        "position": 50,
                        "avgCost": 41.1,
                        "mktPrice": 45.4,
                        "currency": "GBP",
                    },
                    {
                        "acctId": "U1234567",
                        "conid": 999001,
                        "contractDesc": "AAPL  260116C00200000",
                        "description": "Apple Jan26 200 Call",
                        "assetClass": "OPT",
                        "position": 1,
                        "avgCost": 12,
                    },
                ],
            )
        if (
            str(request.url)
            == "https://127.0.0.1:5000/v1/api/portfolio/U1234567/positions/1"
        ):
            return httpx.Response(200, json=[])
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    connector = IbkrClientPortalConnector(
        base_url="https://127.0.0.1:5000/v1/api",
        transport=httpx.MockTransport(handler),
    )

    accounts = connector.list_accounts()
    positions = connector.fetch_positions()

    assert [account.account_id for account in accounts] == ["U1234567"]
    assert accounts[0].name == "Primary IBKR"
    assert len(positions) == 2
    assert positions[0].instrument.symbol == "SPGI"
    assert positions[0].instrument.asset_class == AssetClass.EQUITY
    assert positions[0].average_cost == Decimal("420.5")
    assert positions[0].latest_price == Decimal("510.25")
    assert positions[1].instrument.symbol == "SGLN"
    assert positions[1].instrument.asset_class == AssetClass.ETF
    assert positions[1].instrument.currency == "GBP"
    assert requests == [
        "https://127.0.0.1:5000/v1/api/portfolio/accounts",
        "https://127.0.0.1:5000/v1/api/portfolio/U1234567/positions/0",
        "https://127.0.0.1:5000/v1/api/portfolio/U1234567/positions/1",
    ]
    assert connector.last_skipped_positions == [
        {
            "account_id": "U1234567",
            "symbol": "AAPL  260116C00200000",
            "reason": "unsupported asset class: OPT",
        }
    ]


def test_ibkr_connector_raises_clear_error_when_gateway_session_is_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Not authenticated"})

    connector = IbkrClientPortalConnector(
        base_url="https://127.0.0.1:5000/v1/api",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RuntimeError, match="IBKR gateway session is not authenticated"):
        connector.list_accounts()


def test_ibkr_connector_bootstraps_gateway_session_and_retries_once() -> None:
    requests: list[tuple[str, str]] = []
    portfolio_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal portfolio_attempts
        requests.append((request.method, str(request.url)))

        if str(request.url) == "https://localhost:5001/v1/api/portfolio/accounts":
            portfolio_attempts += 1
            if portfolio_attempts == 1:
                return httpx.Response(401, json={"error": "Not authenticated"})
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "U1234567",
                        "accountTitle": "Primary IBKR",
                        "currency": "USD",
                    }
                ],
            )

        if str(request.url) == "https://localhost:5001/sso/validate":
            return httpx.Response(200, json={"status": "ok"})

        if str(request.url) == "https://localhost:5001/v1/api/iserver/auth/status":
            assert request.method == "POST"
            return httpx.Response(200, json={"authenticated": True, "connected": True})

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    connector = IbkrClientPortalConnector(
        base_url="https://localhost:5001/v1/api",
        transport=httpx.MockTransport(handler),
    )

    accounts = connector.list_accounts()

    assert [account.account_id for account in accounts] == ["U1234567"]
    assert requests == [
        ("GET", "https://localhost:5001/v1/api/portfolio/accounts"),
        ("GET", "https://localhost:5001/sso/validate"),
        ("POST", "https://localhost:5001/v1/api/iserver/auth/status"),
        ("GET", "https://localhost:5001/v1/api/portfolio/accounts"),
    ]
