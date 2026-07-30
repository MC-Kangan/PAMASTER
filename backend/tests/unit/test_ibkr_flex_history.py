from datetime import UTC, date, datetime
from decimal import Decimal

from pa_investing.brokers.ibkr_flex_history import parse_ibkr_flex_history_xml


def test_parse_ibkr_flex_history_preserves_daily_nav_positions_and_pnl() -> None:
    history = parse_ibkr_flex_history_xml(
        """
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="U1" fromDate="20260723" toDate="20260723">
              <ChangeInNAV
                accountId="U1"
                fromDate="20260723"
                toDate="20260723"
                startingValue="1000"
                endingValue="1015"
                mtm="15"
                realized="1"
                changeInUnrealized="0"
                depositsWithdrawals="0"
                commissions="-2"
                dividends="3"
                interest="0"
                currency="GBP"
              />
              <MTMPerformanceSummaryInBase>
                <MTMPerformanceSummaryUnderlying
                  accountId="U1"
                  symbol="AAPL"
                  assetCategory="STK"
                  reportDate="20260723"
                  prevCloseQuantity="3"
                  prevClosePrice="321.66"
                  closeQuantity="3"
                  closePrice="333.02"
                  transactionMtm="0"
                  priorOpenMtm="25.5784032"
                  commissions="0"
                  total="25.5784032"
                />
                <MTMPerformanceSummaryUnderlying
                  accountId="U1"
                  symbol=""
                  assetCategory=""
                  reportDate=""
                  transactionMtm="0"
                  priorOpenMtm="0"
                  commissions="0"
                  total="15"
                />
              </MTMPerformanceSummaryInBase>
              <OpenPositions>
                <OpenPosition
                  accountId="U1"
                  symbol="AAPL"
                  position="3"
                  markPrice="333.02"
                  positionValue="999.06"
                  positionValueInBase="749.8344924"
                  costBasisMoney="571.199526"
                  fifoPnlUnrealized="178.634967"
                  unrealizedCapitalGainsPnl="182.835297"
                  unrealizedlFxPnl="-4.20033"
                  currency="USD"
                  assetCategory="STK"
                  percentOfNAV="8.38"
                />
              </OpenPositions>
              <Trades>
                <SymbolSummary
                  accountId="U1"
                  symbol="AAPL"
                  tradeDate="20260723"
                  buySell="BUY"
                  quantity="3"
                  tradePrice="321.66"
                  ibCommission="-1"
                  proceeds="-964.98"
                  cost="965.98"
                  netCash="-965.98"
                  fifoPnlRealized="0"
                  currency="USD"
                  assetCategory="STK"
                />
              </Trades>
              <SecuritiesInfo>
                <SecurityInfo
                  currency="USD"
                  assetCategory="STK"
                  symbol="AAPL"
                  description="APPLE INC"
                  conid="265598"
                  isin="US0378331005"
                  figi="BBG000B9XRY4"
                  listingExchange="NASDAQ"
                  multiplier="1"
                />
              </SecuritiesInfo>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
        """
    )

    assert len(history.statements) == 1
    statement = history.statements[0]
    assert statement.account_id == "U1"
    assert statement.report_date == date(2026, 7, 23)
    assert statement.nav is not None
    assert statement.nav.ending_value == Decimal("1015")
    assert statement.nav.mtm == Decimal("15")
    assert statement.nav.currency == "GBP"
    daily_nav = history.to_broker_daily_nav()
    assert len(daily_nav) == 1
    assert daily_nav[0].mtm == Decimal("15")
    assert daily_nav[0].deposits_withdrawals == Decimal("0")

    assert len(statement.positions) == 1
    assert statement.positions[0].symbol == "AAPL"
    assert statement.positions[0].position_value_in_base == Decimal("749.8344924")
    assert statement.positions[0].fifo_unrealized_pnl == Decimal("178.634967")

    assert len(statement.security_pnl) == 2
    assert statement.security_pnl[0].symbol == "AAPL"
    assert statement.security_pnl[0].total == Decimal("25.5784032")
    assert statement.security_pnl[1].is_total is True

    assert len(statement.trades) == 1
    assert statement.trades[0].trade_date == date(2026, 7, 23)
    assert statement.trades[0].net_cash == Decimal("-965.98")

    assert len(history.securities) == 1
    assert history.securities[0].conid == "265598"
    assert history.securities[0].isin == "US0378331005"


def test_ibkr_flex_history_converts_daily_nav_to_portfolio_snapshots() -> None:
    history = parse_ibkr_flex_history_xml(
        """
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="U1" fromDate="20260724" toDate="20260724">
              <ChangeInNAV
                accountId="U1"
                fromDate="20260724"
                toDate="20260724"
                startingValue="11964.198030989"
                endingValue="11987.492084189"
                mtm="23.2940532"
                realized="0"
                changeInUnrealized="0"
                depositsWithdrawals="0"
                commissions="0"
                dividends="0"
                interest="0"
                currency="GBP"
              />
              <OpenPositions>
                <OpenPosition
                  accountId="U1"
                  symbol="SAP"
                  position="4"
                  positionValueInBase="478.564288"
                  fifoPnlUnrealized="-102.520832"
                  currency="EUR"
                  assetCategory="STK"
                />
                <OpenPosition
                  accountId="U1"
                  symbol="AAPL"
                  position="3"
                  positionValueInBase="749.8344924"
                  fifoPnlUnrealized="178.634967"
                  currency="USD"
                  assetCategory="STK"
                />
              </OpenPositions>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
        """
    )

    snapshots = history.to_portfolio_snapshots()

    assert len(snapshots) == 1
    assert (
        snapshots[0].snapshot_id
        == "ibkr-flex-history:portfolio:GBP:2026-07-24"
    )
    assert snapshots[0].observed_at == datetime(2026, 7, 24, tzinfo=UTC)
    assert snapshots[0].base_currency == "GBP"
    assert snapshots[0].nav == Decimal("11987.492084189")
    assert snapshots[0].gross_exposure == Decimal("1228.3987804")
    assert snapshots[0].net_exposure == Decimal("1228.3987804")
    assert snapshots[0].unrealized_pnl == Decimal("76.114135")
    assert snapshots[0].position_count == 2
    assert snapshots[0].valued_position_count == 2


def test_ibkr_flex_history_aggregates_accounts_by_date_and_currency() -> None:
    history = parse_ibkr_flex_history_xml(
        """
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="U1" fromDate="20260724" toDate="20260724">
              <ChangeInNAV accountId="U1" fromDate="20260724" toDate="20260724"
                startingValue="1000" endingValue="1010" mtm="10"
                realized="0" changeInUnrealized="0" depositsWithdrawals="0"
                commissions="0" dividends="0" interest="0" currency="GBP" />
            </FlexStatement>
            <FlexStatement accountId="U2" fromDate="20260724" toDate="20260724">
              <ChangeInNAV accountId="U2" fromDate="20260724" toDate="20260724"
                startingValue="500" endingValue="505" mtm="5"
                realized="0" changeInUnrealized="0" depositsWithdrawals="0"
                commissions="0" dividends="0" interest="0" currency="GBP" />
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
        """
    )

    snapshots = history.to_portfolio_snapshots()

    assert len(snapshots) == 1
    assert snapshots[0].nav == Decimal("1515")
