from dataclasses import dataclass
from decimal import Decimal
from time import sleep
from xml.etree import ElementTree

import httpx

from pa_investing.brokers.interfaces import BrokerConnector
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Account, Instrument, Position

DEFAULT_IBKR_FLEX_BASE_URL = (
    "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
)
DEFAULT_IBKR_FLEX_TIMEOUT_SECONDS = 20.0
DEFAULT_IBKR_FLEX_USER_AGENT = "pa-investing/0.1"
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


@dataclass
class TradeCostBasis:
    quantity: Decimal = Decimal("0")
    cost: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")

    def average_cost(self, open_quantity: Decimal) -> Decimal | None:
        if open_quantity == 0 or self.quantity != open_quantity or self.cost == 0:
            return None
        return abs((self.cost + abs(self.commission)) / open_quantity)


class IbkrFlexConnector(BrokerConnector):
    def __init__(
        self,
        *,
        token: str,
        query_id: str,
        base_url: str = DEFAULT_IBKR_FLEX_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_IBKR_FLEX_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_IBKR_FLEX_USER_AGENT,
        statement_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self.token = token
        self.query_id = query_id
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout
        self.user_agent = user_agent
        self.statement_retries = statement_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.last_skipped_positions: list[dict[str, str]] = []
        self._statement_root: ElementTree.Element | None = None
        self._client: httpx.Client | None = None

    def list_accounts(self) -> list[Account]:
        root = self._load_statement()
        accounts_by_id: dict[str, Account] = {}

        for statement in root.findall(".//FlexStatement"):
            account_id = _first_attr(statement, "accountId", "fromAccountId")
            if account_id:
                accounts_by_id[account_id] = Account(
                    account_id=account_id,
                    name=_first_attr(
                        statement,
                        "accountName",
                        "accountTitle",
                        default=account_id,
                    ),
                    source="ibkr-flex",
                    base_currency=_first_attr(statement, "currency", default="USD"),
                )

        for info in root.findall(".//AccountInformation"):
            account_id = _first_attr(info, "accountId", "fromAccountId")
            if not account_id:
                continue
            accounts_by_id[account_id] = Account(
                account_id=account_id,
                name=_first_attr(info, "accountTitle", "accountName", default=account_id),
                source="ibkr-flex",
                base_currency=_first_attr(info, "currency", "baseCurrency", default="USD"),
            )

        return list(accounts_by_id.values())

    def fetch_positions(self) -> list[Position]:
        root = self._load_statement()
        self.last_skipped_positions = []
        positions: list[Position] = []
        trade_cost_basis = _trade_cost_basis_by_position(root)

        for node in root.findall(".//OpenPosition"):
            account_id = _first_attr(node, "accountId", "fromAccountId")
            symbol = _first_attr(node, "symbol", "underlyingSymbol")
            if not account_id or not symbol:
                self.last_skipped_positions.append(
                    {
                        "account_id": account_id,
                        "symbol": symbol,
                        "reason": "missing account or symbol",
                    }
                )
                continue
            try:
                asset_class = _map_asset_class(node)
            except ValueError as error:
                self.last_skipped_positions.append(
                    {
                        "account_id": account_id,
                        "symbol": symbol,
                        "reason": str(error),
                    }
                )
                continue

            quantity = _to_decimal(
                _first_attr(node, "position", "quantity", "openPosition", default="0")
            )
            average_cost = _average_cost(
                node,
                quantity,
                trade_cost_basis.get((account_id, symbol)),
            )
            latest_price = _optional_decimal(
                _first_attr(node, "markPrice", "closePrice", "price", default="")
            )
            positions.append(
                Position(
                    account_id=account_id,
                    instrument=Instrument(
                        symbol=symbol,
                        name=_first_attr(node, "description", default=symbol),
                        asset_class=asset_class,
                        currency=_first_attr(node, "currency", default="USD"),
                    ),
                    quantity=quantity,
                    average_cost=average_cost,
                    latest_price=latest_price,
                )
            )

        return positions

    def _load_statement(self) -> ElementTree.Element:
        if self._statement_root is not None:
            return self._statement_root

        reference_code = self._request_report()
        self._statement_root = self._retrieve_report(reference_code)
        return self._statement_root

    def _request_report(self) -> str:
        root = self._get_xml(
            "/SendRequest",
            params={"t": self.token, "q": self.query_id, "v": "3"},
        )
        self._raise_for_flex_failure(root)
        reference_code = root.findtext(".//ReferenceCode", default="").strip()
        if not reference_code:
            raise RuntimeError("IBKR Flex request did not return a reference code")
        return reference_code

    def _retrieve_report(self, reference_code: str) -> ElementTree.Element:
        last_error: RuntimeError | None = None
        for attempt in range(self.statement_retries):
            root = self._get_xml(
                "/GetStatement",
                params={"t": self.token, "q": reference_code, "v": "3"},
            )
            try:
                self._raise_for_flex_failure(root)
            except RuntimeError as error:
                last_error = error
                if attempt < self.statement_retries - 1:
                    sleep(self.retry_delay_seconds)
                    continue
                raise
            return root
        if last_error is not None:
            raise last_error
        raise RuntimeError("IBKR Flex statement was not available")

    def _get_xml(self, path: str, *, params: dict[str, str]) -> ElementTree.Element:
        try:
            response = self._client_instance().get(
                f"{self.base_url}{path}",
                params=params,
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(
                f"Unable to reach IBKR Flex Web Service at {self.base_url}"
            ) from error

        try:
            return ElementTree.fromstring(response.text)
        except ElementTree.ParseError as error:
            raise RuntimeError("IBKR Flex Web Service returned invalid XML") from error

    def _client_instance(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                transport=self.transport,
                timeout=self.timeout,
            )
        return self._client

    def _raise_for_flex_failure(self, root: ElementTree.Element) -> None:
        status = root.findtext(".//Status", default="Success").strip().lower()
        if status != "fail":
            return
        code = root.findtext(".//ErrorCode", default="unknown").strip()
        message = root.findtext(".//ErrorMessage", default="unknown error").strip()
        raise RuntimeError(f"IBKR Flex request failed ({code}): {message}")


def _first_attr(
    node: ElementTree.Element,
    *keys: str,
    default: str = "",
) -> str:
    for key in keys:
        value = node.attrib.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _to_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def _optional_decimal(value: str) -> Decimal | None:
    if not value:
        return None
    return _to_decimal(value)


def _average_cost(
    node: ElementTree.Element,
    quantity: Decimal,
    trade_cost_basis: TradeCostBasis | None = None,
) -> Decimal:
    unit_cost = _first_attr(node, "costBasisPrice", "avgCost", "avgPrice", default="")
    if unit_cost and _to_decimal(unit_cost) != 0:
        return _to_decimal(unit_cost)

    total_cost = _first_attr(node, "costBasisMoney", "costBasis", default="")
    if total_cost and quantity != 0 and _to_decimal(total_cost) != 0:
        return abs(_to_decimal(total_cost) / quantity)

    if trade_cost_basis is not None:
        average_cost = trade_cost_basis.average_cost(quantity)
        if average_cost is not None:
            return average_cost

    return Decimal("0")


def _trade_cost_basis_by_position(
    root: ElementTree.Element,
) -> dict[tuple[str, str], TradeCostBasis]:
    basis_by_position: dict[tuple[str, str], TradeCostBasis] = {}
    for node in root.findall(".//Trade"):
        if _first_attr(node, "assetCategory", "assetClass", default="").upper() not in {
            "STK",
            "STOCK",
            "EQUITY",
            "ETF",
            "FUND",
        }:
            continue
        account_id = _first_attr(node, "accountId", "fromAccountId")
        symbol = _first_attr(node, "symbol", "underlyingSymbol")
        if not account_id or not symbol:
            continue

        basis = basis_by_position.setdefault((account_id, symbol), TradeCostBasis())
        basis.quantity += _to_decimal(_first_attr(node, "quantity", "tradeQuantity", default="0"))
        basis.cost += _to_decimal(_first_attr(node, "cost", default="0"))
        basis.commission += _to_decimal(
            _first_attr(node, "ibCommission", "commission", default="0")
        )
    return basis_by_position


def _map_asset_class(node: ElementTree.Element) -> AssetClass:
    raw_asset_class = _first_attr(
        node,
        "assetClass",
        "assetCategory",
        "category",
        default="",
    ).upper()
    symbol = _first_attr(node, "symbol", default="")
    description = _first_attr(node, "description", default="")
    combined_name = f"{symbol} {description}".upper()

    if raw_asset_class in {"STK", "STOCK", "EQUITY"}:
        if any(hint in combined_name for hint in ETF_NAME_HINTS):
            return AssetClass.ETF
        return AssetClass.EQUITY
    if raw_asset_class in {"ETF", "FUND"}:
        return AssetClass.ETF
    if raw_asset_class in {"CRYPTO", "CRYPTOCURRENCY"}:
        return AssetClass.CRYPTO
    if raw_asset_class in {"CASH", "FX"}:
        return AssetClass.CASH
    raise ValueError(f"unsupported asset class: {raw_asset_class or 'unknown'}")
