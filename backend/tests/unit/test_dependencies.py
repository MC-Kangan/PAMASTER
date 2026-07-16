from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from pa_investing.core import dependencies
from pa_investing.core.config import Settings
from pa_investing.market_data.twelve_data import TwelveDataProvider


class StubSession:
    def __init__(self) -> None:
        self.commit = Mock()


class StubSessionFactory:
    def __init__(self, session: StubSession) -> None:
        self.session_instance = session
        self.finance_session = StubSession()
        self.session_count = 0

    @contextmanager
    def session(self) -> Iterator[StubSession]:
        selected = (
            self.session_instance
            if self.session_count == 0
            else self.finance_session
        )
        self.session_count += 1
        yield selected


def _workflow_dependency(
    monkeypatch: pytest.MonkeyPatch,
    session: StubSession,
) -> Iterator[object]:
    monkeypatch.setattr(
        dependencies,
        "get_database_session_factory",
        lambda: StubSessionFactory(session),
    )
    return dependencies.get_refresh_and_sync_workflow(
        market_data_provider=dependencies.ManualPriceProvider(prices={}),
        notion_client=dependencies.FakeNotionClient(),
    )


def test_refresh_and_sync_workflow_dependency_injects_commit_into_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = StubSession()
    dependency = _workflow_dependency(monkeypatch, session)

    workflow = next(dependency)

    assert workflow.daily_review_workflow.finance_analyzer is not None
    assert (
        workflow.daily_review_workflow.finance_analyzer.historical_data.session
        is not session
    )
    workflow.commit()

    session.commit.assert_called_once_with()


def test_refresh_and_sync_workflow_dependency_does_not_commit_during_teardown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = StubSession()
    dependency = _workflow_dependency(monkeypatch, session)

    next(dependency)

    with pytest.raises(StopIteration):
        next(dependency)

    session.commit.assert_not_called()


def test_market_data_dependency_builds_twelve_data_provider() -> None:
    provider = dependencies.get_market_data_provider(
        Settings(
            market_data_provider="twelve_data",
            twelve_data_api_key="test-key",
        )
    )

    assert isinstance(provider, TwelveDataProvider)
    assert provider.api_key == "test-key"
