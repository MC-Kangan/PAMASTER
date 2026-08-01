from decimal import Decimal

import httpx
import pytest

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, Position
from pa_investing.research.trade_agent import (
    TradeAgentClient,
    TradeAgentUnavailableError,
    market_for_trade_agent,
)


def test_market_for_trade_agent_maps_common_portfolio_venues() -> None:
    assert market_for_trade_agent(asset_class=AssetClass.EQUITY, venue="NASDAQ") == "US"
    assert market_for_trade_agent(asset_class=AssetClass.ETF, venue="LSE") == "LSE"
    assert market_for_trade_agent(asset_class=AssetClass.EQUITY, venue="XETRA") == "XETRA"
    assert market_for_trade_agent(asset_class=AssetClass.CRYPTO, venue=None) == "CRYPTO"


def test_trade_agent_client_requires_enabled_token_and_url() -> None:
    client = TradeAgentClient(
        base_url="http://127.0.0.1:8002",
        bearer_token="",
        enabled=True,
    )

    assert client.configured is False
    with pytest.raises(TradeAgentUnavailableError):
        client.list_skills()


def test_trade_agent_client_sends_bearer_token_and_position_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_request(
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(httpx, "request", fake_request)
    client = TradeAgentClient(
        base_url="http://127.0.0.1:8002/",
        bearer_token="secret-token",
        enabled=True,
    )
    position = Position(
        account_id="acct-1",
        instrument=Instrument(
            symbol="AAPL",
            name="Apple Inc.",
            asset_class=AssetClass.EQUITY,
            instrument_id="aapl-id",
            venue="NASDAQ",
        ),
        quantity=Decimal("10"),
        average_cost=Decimal("150"),
    )

    client.run_skill(skill="technical", symbol="AAPL", market="US", position=position)

    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:8002/skills/technical/run"
    assert captured["headers"] == {"Authorization": "Bearer secret-token"}
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["instrument"] == {"symbol": "AAPL", "market": "US"}
    assert body["analysts"] == ["technical"]
    assert body["positions"] == [
        {
            "instrument": {"symbol": "AAPL", "market": "US"},
            "quantity": 10.0,
            "average_cost": 150.0,
        }
    ]
    assert body["metadata"]["source"] == "pa_investing"


def test_trade_agent_client_forwards_skill_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_request(
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(httpx, "request", fake_request)
    client = TradeAgentClient(
        base_url="http://127.0.0.1:8002",
        bearer_token="secret-token",
        enabled=True,
    )

    client.run_skill(
        skill="technical",
        symbol="AAPL",
        market="US",
        skill_parameters={"technical": {"lookback_days": 90}},
    )

    body = captured["json"]
    assert isinstance(body, dict)
    assert body["skill_parameters"] == {"technical": {"lookback_days": 90}}


def test_trade_agent_client_omits_skill_parameters_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_request(
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        captured["json"] = kwargs["json"]
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(httpx, "request", fake_request)
    client = TradeAgentClient(
        base_url="http://127.0.0.1:8002",
        bearer_token="secret-token",
        enabled=True,
    )

    client.run_skill(skill="technical", symbol="AAPL", market="US")

    assert "skill_parameters" not in captured["json"]


class TestRunSkillWithParameters:
    def test_skill_parameters_included_in_request_body(self) -> None:
        """Verify skill_parameters are forwarded in the POST body."""
        client = TradeAgentClient(
            base_url="http://127.0.0.1:8002",
            bearer_token="test",
            enabled=True,
            timeout_seconds=1,
        )
        import inspect

        sig = inspect.signature(client.run_skill)
        assert "skill_parameters" in sig.parameters
        param = sig.parameters["skill_parameters"]
        assert param.default is None

    def test_run_skill_without_parameters_still_works(self) -> None:
        """Backward compat: calling without skill_parameters should not break."""
        client = TradeAgentClient(
            base_url="http://127.0.0.1:8002",
            bearer_token="test",
            enabled=True,
            timeout_seconds=1,
        )
        import inspect

        sig = inspect.signature(client.run_skill)
        assert sig.parameters["skill_parameters"].default is None
