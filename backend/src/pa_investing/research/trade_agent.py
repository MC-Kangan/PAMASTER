from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Position
from pa_investing.instruments.market_codes import DEFAULT_MARKET_CODES


class TradeAgentClientError(RuntimeError):
    """Raised when TradeAgent returns an unexpected response."""


class TradeAgentUnavailableError(TradeAgentClientError):
    """Raised when TradeAgent is disabled, unconfigured, or unreachable."""


class TradeAgentClient:
    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        enabled: bool,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.base_url and self.bearer_token)

    def list_skills(self) -> list[dict[str, Any]]:
        if not self.configured:
            raise TradeAgentUnavailableError("TradeAgent is not configured")
        response = self._request("GET", "/skills")
        payload = response.json()
        if not isinstance(payload, list):
            raise TradeAgentClientError("TradeAgent returned an invalid skills payload")
        return [item for item in payload if isinstance(item, dict)]

    def run_skill(
        self,
        *,
        skill: str,
        symbol: str,
        market: str,
        position: Position | None = None,
        skill_parameters: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise TradeAgentUnavailableError("TradeAgent is not configured")
        request: dict[str, Any] = {
            "instrument": {"symbol": symbol, "market": market},
            "analysts": [skill],
        }
        if position is not None:
            request["positions"] = [
                {
                    "instrument": {
                        "symbol": position.instrument.symbol,
                        "market": market_for_trade_agent(
                            asset_class=position.instrument.asset_class,
                            venue=position.instrument.venue,
                        )
                        or market,
                    },
                    "quantity": float(position.quantity),
                    "average_cost": _decimal_or_none(
                        position.broker_average_cost or position.average_cost
                    ),
                }
            ]
            request["metadata"] = {
                "source": "pa_investing",
                "position_context": "displayed_by_pa_investing",
            }
        if skill_parameters:
            request["skill_parameters"] = skill_parameters
        response = self._request("POST", f"/skills/{skill}/run", json=request)
        payload = response.json()
        if not isinstance(payload, dict):
            raise TradeAgentClientError("TradeAgent returned an invalid report payload")
        return payload

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self.bearer_token}"},
                timeout=self.timeout_seconds,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise TradeAgentUnavailableError("TradeAgent is unreachable") from exc
        if response.status_code in {401, 403}:
            raise TradeAgentUnavailableError("TradeAgent authentication failed")
        if response.status_code == 503:
            raise TradeAgentUnavailableError("TradeAgent capability is unavailable")
        if response.status_code == 404:
            raise TradeAgentClientError(
                "TradeAgent did not answer this endpoint; check "
                "PA_TRADE_RESEARCH_BASE_URL points to TradeAgent, not PAMASTER"
            )
        if response.status_code >= 400:
            detail = f"TradeAgent request failed with status {response.status_code}"
            try:
                body = response.json()
                if isinstance(body, dict) and body.get("detail"):
                    detail = str(body["detail"])
            except Exception:
                pass
            raise TradeAgentClientError(detail)
        return response


def market_for_trade_agent(*, asset_class: AssetClass, venue: str | None) -> str | None:
    if asset_class is AssetClass.CRYPTO:
        return "CRYPTO"
    market = DEFAULT_MARKET_CODES.market_for_exchange(venue)
    if market == "US":
        return "US"
    if market == "LN":
        return "LSE"
    if market == "GY":
        return "XETRA"
    return market


def _decimal_or_none(value: Decimal | None) -> float | None:
    return None if value is None else float(value)
