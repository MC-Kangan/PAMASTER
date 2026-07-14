from decimal import Decimal

import httpx
import pytest

from pa_investing.brokers.ibkr_flex import IbkrFlexConnector
from pa_investing.domain.enums import AssetClass


def test_ibkr_flex_connector_fetches_report_and_maps_accounts_and_positions() -> None:
    requests: list[tuple[str, str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                request.method,
                str(request.url.copy_with(query=None)),
                dict(request.url.params),
            )
        )
        assert request.headers["User-Agent"].startswith("pa-investing/")

        if str(request.url.copy_with(query=None)).endswith("/SendRequest"):
            return httpx.Response(
                200,
                text="""
                <FlexStatementResponse>
                    <Status>Success</Status>
                    <ReferenceCode>987654321</ReferenceCode>
                </FlexStatementResponse>
                """,
            )
        if str(request.url.copy_with(query=None)).endswith("/GetStatement"):
            return httpx.Response(
                200,
                text="""
                <FlexQueryResponse>
                  <FlexStatements>
                    <FlexStatement accountId="U1234567" accountName="Primary IBKR" currency="USD">
                      <AccountInformation
                        accountId="U1234567"
                        accountTitle="Primary IBKR"
                        currency="USD"
                      />
                      <OpenPositions>
                        <OpenPosition
                          accountId="U1234567"
                          symbol="SPGI"
                          description="S&amp;P Global Inc."
                          assetCategory="STK"
                          currency="USD"
                          position="10"
                          costBasisPrice="420.5"
                          markPrice="510.25"
                        />
                        <OpenPosition
                          accountId="U1234567"
                          symbol="SGLN"
                          description="iShares Physical Gold ETC"
                          assetCategory="STK"
                          currency="GBP"
                          position="50"
                          costBasisPrice="41.1"
                          markPrice="45.4"
                        />
                        <OpenPosition
                          accountId="U1234567"
                          symbol="AAPL  260116C00200000"
                          description="Apple Jan26 200 Call"
                          assetCategory="OPT"
                          currency="USD"
                          position="1"
                          costBasisPrice="12"
                          markPrice="15"
                        />
                      </OpenPositions>
                    </FlexStatement>
                  </FlexStatements>
                </FlexQueryResponse>
                """,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    connector = IbkrFlexConnector(
        token="test-token",
        query_id="12345",
        transport=httpx.MockTransport(handler),
    )

    accounts = connector.list_accounts()
    positions = connector.fetch_positions()

    assert [account.account_id for account in accounts] == ["U1234567"]
    assert accounts[0].name == "Primary IBKR"
    assert accounts[0].base_currency == "USD"
    assert len(positions) == 2
    assert positions[0].instrument.symbol == "SPGI"
    assert positions[0].instrument.asset_class == AssetClass.EQUITY
    assert positions[0].quantity == Decimal("10")
    assert positions[0].average_cost == Decimal("420.5")
    assert positions[0].latest_price == Decimal("510.25")
    assert positions[1].instrument.symbol == "SGLN"
    assert positions[1].instrument.asset_class == AssetClass.ETF
    assert positions[1].instrument.currency == "GBP"
    assert requests == [
        (
            "GET",
            "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest",
            {"t": "test-token", "q": "12345", "v": "3"},
        ),
        (
            "GET",
            "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement",
            {"t": "test-token", "q": "987654321", "v": "3"},
        ),
    ]
    assert connector.last_skipped_positions == [
        {
            "account_id": "U1234567",
            "symbol": "AAPL  260116C00200000",
            "reason": "unsupported asset class: OPT",
        }
    ]


def test_ibkr_flex_connector_raises_clear_error_when_report_generation_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="""
            <FlexStatementResponse>
                <Status>Fail</Status>
                <ErrorCode>1012</ErrorCode>
                <ErrorMessage>Token has expired.</ErrorMessage>
            </FlexStatementResponse>
            """,
        )

    connector = IbkrFlexConnector(
        token="expired-token",
        query_id="12345",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RuntimeError, match="IBKR Flex request failed.*Token has expired"):
        connector.list_accounts()


def test_ibkr_flex_connector_reconstructs_average_cost_from_matching_trades() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url.copy_with(query=None)).endswith("/SendRequest"):
            return httpx.Response(
                200,
                text="""
                <FlexStatementResponse>
                    <Status>Success</Status>
                    <ReferenceCode>987654321</ReferenceCode>
                </FlexStatementResponse>
                """,
            )
        if str(request.url.copy_with(query=None)).endswith("/GetStatement"):
            return httpx.Response(
                200,
                text="""
                <FlexQueryResponse>
                  <FlexStatements>
                    <FlexStatement accountId="U1234567" accountName="Primary IBKR">
                      <OpenPositions>
                        <OpenPosition
                          accountId="U1234567"
                          symbol="SPGI"
                          description="S&amp;P Global Inc."
                          assetCategory="STK"
                          currency="USD"
                          position="2"
                          costBasisPrice="0"
                          costBasisMoney="0"
                          markPrice="510.25"
                        />
                        <OpenPosition
                          accountId="U1234567"
                          symbol="MBGL"
                          description="Mobility Global Inc."
                          assetCategory="STK"
                          currency="USD"
                          position="2"
                          costBasisPrice="0"
                          costBasisMoney="0"
                          markPrice="20.8"
                        />
                      </OpenPositions>
                      <Trades>
                        <Trade
                          accountId="U1234567"
                          symbol="SPGI"
                          description="S&amp;P Global Inc."
                          assetCategory="STK"
                          currency="USD"
                          buySell="BUY"
                          quantity="1"
                          cost="440"
                          ibCommission="-1"
                          tradePrice="440"
                        />
                        <Trade
                          accountId="U1234567"
                          symbol="SPGI"
                          description="S&amp;P Global Inc."
                          assetCategory="STK"
                          currency="USD"
                          buySell="BUY"
                          quantity="1"
                          cost="460"
                          ibCommission="-1"
                          tradePrice="460"
                        />
                      </Trades>
                    </FlexStatement>
                  </FlexStatements>
                </FlexQueryResponse>
                """,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    connector = IbkrFlexConnector(
        token="test-token",
        query_id="12345",
        transport=httpx.MockTransport(handler),
    )

    positions = connector.fetch_positions()

    average_cost_by_symbol = {
        position.instrument.symbol: position.average_cost
        for position in positions
    }
    assert average_cost_by_symbol["SPGI"] == Decimal("451")
    assert average_cost_by_symbol["MBGL"] == Decimal("0")
