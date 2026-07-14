from decimal import Decimal

import httpx

from pa_investing.brokers.interfaces import BrokerConnector
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Account, Instrument, Position

DEFAULT_IBKR_TIMEOUT_SECONDS = 10.0
ETF_NAME_HINTS = (
    " ETF",
    " ETC",
    " ETN",
    " FUND",
    " TRUST",
    "ISHARES",
    "VANGUARD",
    "SPDR",
    "INVESCO",
    "XTRACKERS",
    "WISDOMTREE",
    "VANECK",
)


class IbkrClientPortalConnector(BrokerConnector):
    def __init__(
        self,
        *,
        base_url: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_IBKR_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout
        self.last_skipped_positions: list[dict[str, str]] = []
        self._accounts_cache: list[Account] | None = None
        self._client: httpx.Client | None = None

    def list_accounts(self) -> list[Account]:
        payload = self._get_json("/portfolio/accounts")
        if not isinstance(payload, list):
            raise RuntimeError("IBKR gateway returned an invalid accounts payload")

        accounts: list[Account] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            account_id = _first_text(row, "id", "accountId", "acctId")
            if not account_id:
                continue
            accounts.append(
                Account(
                    account_id=account_id,
                    name=_first_text(
                        row,
                        "accountTitle",
                        "accountName",
                        "name",
                        default=account_id,
                    ),
                    source="ibkr",
                    base_currency=_first_text(row, "currency", "baseCurrency", default="USD"),
                )
            )
        self._accounts_cache = accounts
        return accounts

    def fetch_positions(self) -> list[Position]:
        accounts = self._accounts_cache or self.list_accounts()
        self.last_skipped_positions = []
        positions: list[Position] = []
        for account in accounts:
            page = 0
            while True:
                payload = self._get_json(f"/portfolio/{account.account_id}/positions/{page}")
                if not isinstance(payload, list):
                    raise RuntimeError(
                        "IBKR gateway returned an invalid positions payload for "
                        f"{account.account_id}"
                    )
                if not payload:
                    break
                positions.extend(self._parse_positions(account.account_id, payload))
                page += 1
        return positions

    def _parse_positions(
        self,
        account_id: str,
        rows: list[object],
    ) -> list[Position]:
        positions: list[Position] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = _first_text(row, "contractDesc", "ticker", "symbol")
            if not symbol:
                self.last_skipped_positions.append(
                    {
                        "account_id": account_id,
                        "symbol": "",
                        "reason": "missing symbol",
                    }
                )
                continue
            try:
                asset_class = _map_asset_class(row)
            except ValueError as error:
                self.last_skipped_positions.append(
                    {
                        "account_id": account_id,
                        "symbol": symbol,
                        "reason": str(error),
                    }
                )
                continue

            quantity = _to_decimal(row.get("position"))
            average_cost = _to_decimal(
                row.get("avgCost"),
                row.get("avgPrice"),
                default=Decimal("0"),
            )
            latest_price = _optional_decimal(
                row.get("mktPrice"),
                row.get("marketPrice"),
                row.get("last"),
                row.get("lastPrice"),
            )
            positions.append(
                Position(
                    account_id=account_id,
                    instrument=Instrument(
                        symbol=symbol,
                        name=_first_text(row, "description", "contractDesc", default=symbol),
                        asset_class=asset_class,
                        currency=_first_text(row, "currency", default="USD"),
                    ),
                    quantity=quantity,
                    average_cost=average_cost,
                    latest_price=latest_price,
                )
            )
        return positions

    def _get_json(self, path: str) -> object:
        try:
            response = self._client_instance().get(f"{self.base_url}{path}")
        except httpx.HTTPError as error:
            raise RuntimeError(f"Unable to reach IBKR gateway at {self.base_url}") from error

        if response.status_code in {401, 403}:
            self._bootstrap_session()
            try:
                response = self._client_instance().get(f"{self.base_url}{path}")
            except httpx.HTTPError as error:
                raise RuntimeError(
                    f"Unable to reach IBKR gateway at {self.base_url}"
                ) from error
            if response.status_code in {401, 403}:
                raise RuntimeError("IBKR gateway session is not authenticated")
        response.raise_for_status()
        return response.json()

    def _bootstrap_session(self) -> None:
        client = self._client_instance()
        try:
            client.get(f"{self._gateway_origin()}/sso/validate")
            response = client.post(
                f"{self.base_url}/iserver/auth/status",
                json={},
            )
        except httpx.HTTPError as error:
            raise RuntimeError(f"Unable to reach IBKR gateway at {self.base_url}") from error
        if response.status_code in {401, 403}:
            raise RuntimeError("IBKR gateway session is not authenticated")
        response.raise_for_status()

    def _client_instance(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                transport=self.transport,
                timeout=self.timeout,
                verify=False,
            )
        return self._client

    def _gateway_origin(self) -> str:
        return self.base_url.split("/v1/api", 1)[0]


def _first_text(payload: dict[str, object], *keys: str, default: str = "") -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _to_decimal(*values: object, default: Decimal | None = None) -> Decimal:
    for value in values:
        if value in (None, ""):
            continue
        return Decimal(str(value))
    if default is None:
        raise ValueError("decimal value is required")
    return default


def _optional_decimal(*values: object) -> Decimal | None:
    for value in values:
        if value in (None, ""):
            continue
        return Decimal(str(value))
    return None


def _map_asset_class(payload: dict[str, object]) -> AssetClass:
    raw_asset_class = _first_text(payload, "assetClass", "secType").upper()
    description = _first_text(payload, "description", "contractDesc").upper()

    if raw_asset_class in {"OPT", "FOP", "FUT", "WAR", "IOPT", "CASH", "BOND", "CMDTY"}:
        raise ValueError(f"unsupported asset class: {raw_asset_class}")
    if raw_asset_class == "CRYPTO":
        return AssetClass.CRYPTO
    if raw_asset_class in {"ETF"}:
        return AssetClass.ETF
    if raw_asset_class in {"STK", "EQUITY"}:
        if any(hint in description for hint in ETF_NAME_HINTS):
            return AssetClass.ETF
        return AssetClass.EQUITY
    raise ValueError(f"unsupported asset class: {raw_asset_class or 'UNKNOWN'}")
