from contextlib import AbstractContextManager
from types import TracebackType
from xml.etree import ElementTree

import pytest

from pa_investing.core.config import Settings
from pa_investing.scripts.import_ibkr_history import (
    _build_history_connector,
    import_ibkr_history,
)


class StubHistoryConnector:
    def __init__(self) -> None:
        self.call_count = 0

    def fetch_statement_root(self) -> ElementTree.Element:
        self.call_count += 1
        return ElementTree.fromstring(
            """
            <FlexQueryResponse>
              <FlexStatements>
                <FlexStatement accountId="U1" fromDate="20260724" toDate="20260724">
                  <ChangeInNAV
                    accountId="U1"
                    fromDate="20260724"
                    toDate="20260724"
                    startingValue="1000"
                    endingValue="1025"
                    mtm="25"
                    realized="0"
                    changeInUnrealized="0"
                    depositsWithdrawals="0"
                    commissions="0"
                    dividends="0"
                    interest="0"
                    currency="GBP"
                  />
                  <MTMPerformanceSummaryInBase>
                    <MTMPerformanceSummaryUnderlying
                      accountId="U1"
                      symbol="AAPL"
                      assetCategory="STK"
                      reportDate="20260724"
                      prevCloseQuantity="3"
                      prevClosePrice="321.66"
                      closeQuantity="3"
                      closePrice="333.02"
                      transactionMtm="0"
                      priorOpenMtm="25"
                      commissions="0"
                      total="25"
                    />
                  </MTMPerformanceSummaryInBase>
                </FlexStatement>
              </FlexStatements>
            </FlexQueryResponse>
            """
        )


class EmptyHistoryConnector:
    def fetch_statement_root(self) -> ElementTree.Element:
        return ElementTree.fromstring("<FlexQueryResponse><FlexStatements /></FlexQueryResponse>")


class StubSessionFactory:
    def __init__(self) -> None:
        self.session_obj = None

    def session(self) -> AbstractContextManager[object]:
        factory = self

        class SessionContext:
            def __enter__(self) -> object:
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker

                from pa_investing.db.base import Base

                engine = create_engine("sqlite+pysqlite:///:memory:")
                Base.metadata.create_all(engine)
                session = sessionmaker(bind=engine)()
                factory.session_obj = session
                return session

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                if factory.session_obj is not None:
                    factory.session_obj.close()

        return SessionContext()


def test_import_ibkr_history_fetches_when_path_is_omitted(tmp_path) -> None:
    connector = StubHistoryConnector()
    raw_path = tmp_path / "raw.xml"

    result = import_ibkr_history(
        settings=Settings(
            ibkr_flex_token="token",
            ibkr_flex_history_query_id="history-query",
        ),
        session_factory=StubSessionFactory(),
        connector=connector,
        save_raw_xml=raw_path,
    )

    assert result == (1, 1, 1, 1)
    assert connector.call_count == 1
    assert "MTMPerformanceSummaryUnderlying" in raw_path.read_text()


def test_build_history_connector_requires_history_query_id() -> None:
    with pytest.raises(RuntimeError, match="PA_IBKR_FLEX_HISTORY_QUERY_ID"):
        _build_history_connector(
            Settings(
                ibkr_flex_token="token",
                ibkr_flex_history_query_id="",
            )
        )


def test_import_ibkr_history_rejects_empty_live_response() -> None:
    with pytest.raises(RuntimeError, match="returned no daily history rows"):
        import_ibkr_history(
            settings=Settings(
                ibkr_flex_token="token",
                ibkr_flex_history_query_id="history-query",
            ),
            session_factory=StubSessionFactory(),
            connector=EmptyHistoryConnector(),
        )
