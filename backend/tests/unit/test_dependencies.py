from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from pa_investing.core import dependencies


class StubSession:
    def __init__(self) -> None:
        self.commit = Mock()


class StubSessionFactory:
    def __init__(self, session: StubSession) -> None:
        self.session_instance = session

    @contextmanager
    def session(self) -> Iterator[StubSession]:
        yield self.session_instance


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
