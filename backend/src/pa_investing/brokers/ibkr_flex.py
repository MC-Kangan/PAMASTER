from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import sleep
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx

from pa_investing.brokers.interfaces import BrokerConnector
from pa_investing.domain.enums import (
    AssetClass,
    CostBasisStatus,
    ReconciliationStatus,
    TransactionType,
)
from pa_investing.domain.models import (
    Account,
    BrokerReconciliation,
    Instrument,
    InstrumentIdentifier,
    Position,
    Transaction,
)

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
        report_timezone: str = "UTC",
    ) -> None:
        self.token = token
        self.query_id = query_id
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout
        self.user_agent = user_agent
        self.statement_retries = statement_retries
        self.retry_delay_seconds = retry_delay_seconds
        try:
            self.report_timezone = ZoneInfo(report_timezone)
        except Exception as exc:
            raise ValueError(
                f"invalid IBKR Flex report timezone: {report_timezone}"
            ) from exc
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
        base_currency_by_account = _base_currency_by_account(root)

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
            average_cost, cost_basis_status = _average_cost(
                node,
                quantity,
                trade_cost_basis.get(_position_key(node)),
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
                        venue=_first_attr(
                            node,
                            "listingExchange",
                            "exchange",
                            default="",
                        )
                        or None,
                        identifiers=_instrument_identifiers(node),
                    ),
                    quantity=quantity,
                    average_cost=average_cost,
                    latest_price=latest_price,
                    cost_basis_status=cost_basis_status,
                    reporting_currency=base_currency_by_account.get(account_id),
                    fx_rate=_optional_decimal(
                        _first_attr(node, "fxRateToBase", default="")
                    ),
                )
            )

        positions.extend(_cash_positions(root))

        return positions

    def fetch_transactions(self) -> list[Transaction]:
        root = self._load_statement()
        transactions: list[Transaction] = []
        for node in root.findall(".//Trade"):
            account_id = _first_attr(node, "accountId", "fromAccountId")
            external_id = _first_attr(
                node,
                "transactionID",
                "tradeID",
                "ibExecID",
            )
            if not account_id or not external_id:
                continue
            symbol = _first_attr(node, "symbol", "underlyingSymbol") or None
            instrument = None
            try:
                asset_class = _map_asset_class(node)
            except ValueError:
                asset_class = None
            if asset_class is not None and symbol is not None:
                instrument = Instrument(
                    symbol=symbol,
                    name=_first_attr(node, "description", default=symbol),
                    asset_class=asset_class,
                    currency=_first_attr(node, "currency", default="USD"),
                    venue=_first_attr(
                        node,
                        "listingExchange",
                        "exchange",
                        default="",
                    )
                    or None,
                    identifiers=_instrument_identifiers(node),
                )
            buy_sell = _first_attr(node, "buySell").upper()
            if asset_class == AssetClass.CASH:
                transaction_type = TransactionType.FX
            elif buy_sell == "BUY":
                transaction_type = TransactionType.BUY
            elif buy_sell == "SELL":
                transaction_type = TransactionType.SELL
            else:
                transaction_type = TransactionType.OTHER
            transactions.append(
                Transaction(
                    transaction_id=f"ibkr-flex:{account_id}:{external_id}",
                    account_id=account_id,
                    provider="ibkr-flex",
                    external_id=external_id,
                    occurred_at=_parse_flex_datetime(
                        node,
                        self.report_timezone,
                    ),
                    transaction_type=transaction_type,
                    currency=_first_attr(node, "currency", default="USD"),
                    symbol=symbol,
                    instrument=instrument,
                    quantity=_to_decimal(
                        _first_attr(node, "quantity", default="0")
                    ),
                    unit_price=_optional_decimal(
                        _first_attr(node, "tradePrice", default="")
                    ),
                    gross_amount=_to_decimal(
                        _first_attr(node, "proceeds", default="0")
                    ),
                    fees=_to_decimal(
                        _first_attr(node, "ibCommission", default="0")
                    ),
                    taxes=_to_decimal(_first_attr(node, "taxes", default="0")),
                    net_cash=_to_decimal(
                        _first_attr(node, "netCash", default="0")
                    ),
                    description=_first_attr(node, "description") or None,
                )
            )
        return transactions

    def fetch_reconciliations(self) -> list[BrokerReconciliation]:
        root = self._load_statement()
        latest_equity: dict[str, ElementTree.Element] = {}
        for node in root.findall(".//EquitySummaryByReportDateInBase"):
            account_id = _first_attr(node, "accountId", "fromAccountId")
            report_date = _first_attr(node, "reportDate")
            current = latest_equity.get(account_id)
            if not account_id or not report_date:
                continue
            if current is None or report_date > _first_attr(current, "reportDate"):
                latest_equity[account_id] = node

        base_cash: dict[str, Decimal] = {}
        for node in root.findall(".//CashReportCurrency"):
            if _first_attr(node, "levelOfDetail").lower() != "basecurrency":
                continue
            account_id = _first_attr(node, "accountId", "fromAccountId")
            if account_id:
                base_cash[account_id] = _to_decimal(
                    _first_attr(node, "endingCash", default="0")
                )

        securities_value: dict[str, Decimal] = {}
        for node in root.findall(".//OpenPosition"):
            account_id = _first_attr(node, "accountId", "fromAccountId")
            if not account_id:
                continue
            local_value = _to_decimal(
                _first_attr(node, "positionValue", default="0")
            )
            fx_rate = _to_decimal(
                _first_attr(node, "fxRateToBase", default="1")
            )
            securities_value[account_id] = (
                securities_value.get(account_id, Decimal("0"))
                + local_value * fx_rate
            )

        reconciliations: list[BrokerReconciliation] = []
        tolerance = Decimal("0.02")
        for account_id, node in latest_equity.items():
            broker_nav = _to_decimal(_first_attr(node, "total", default="0"))
            broker_cash = _to_decimal(_first_attr(node, "cash", default="0"))
            calculated_cash = base_cash.get(account_id, Decimal("0"))
            calculated_nav = (
                securities_value.get(account_id, Decimal("0")) + calculated_cash
            )
            nav_difference = calculated_nav - broker_nav
            cash_difference = calculated_cash - broker_cash
            status = (
                ReconciliationStatus.MATCHED
                if abs(nav_difference) <= tolerance
                and abs(cash_difference) <= tolerance
                else ReconciliationStatus.WARNING
            )
            report_date = _first_attr(node, "reportDate")
            reconciliations.append(
                BrokerReconciliation(
                    reconciliation_id=(
                        f"ibkr-flex:{account_id}:{report_date}"
                    ),
                    account_id=account_id,
                    provider="ibkr-flex",
                    observed_at=_parse_flex_date(report_date),
                    currency=_first_attr(node, "currency", default="USD"),
                    broker_nav=broker_nav,
                    calculated_nav=calculated_nav,
                    nav_difference=nav_difference,
                    broker_cash=broker_cash,
                    calculated_cash=calculated_cash,
                    cash_difference=cash_difference,
                    status=status,
                )
            )
        return reconciliations

    def fetch_statement_root(self) -> ElementTree.Element:
        return self._load_statement()

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


def _parse_flex_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)


def _parse_flex_datetime(
    node: ElementTree.Element,
    report_timezone: ZoneInfo,
) -> datetime:
    value = _first_attr(node, "dateTime", "tradeDate", "reportDate")
    for pattern in ("%Y%m%d;%H%M%S", "%Y%m%d"):
        try:
            return (
                datetime.strptime(value, pattern)
                .replace(tzinfo=report_timezone)
                .astimezone(UTC)
            )
        except ValueError:
            continue
    raise ValueError(f"unsupported IBKR Flex date/time: {value}")


def _base_currency_by_account(
    root: ElementTree.Element,
) -> dict[str, str]:
    currencies: dict[str, str] = {}
    for statement in root.findall(".//FlexStatement"):
        account_id = _first_attr(statement, "accountId", "fromAccountId")
        if account_id:
            currencies[account_id] = _first_attr(
                statement,
                "currency",
                default="USD",
            ).upper()
    for info in root.findall(".//AccountInformation"):
        account_id = _first_attr(info, "accountId", "fromAccountId")
        if account_id:
            currencies[account_id] = _first_attr(
                info,
                "currency",
                "baseCurrency",
                default=currencies.get(account_id, "USD"),
            ).upper()
    return currencies


def _cash_positions(root: ElementTree.Element) -> list[Position]:
    positions: list[Position] = []
    for node in root.findall(".//CashReportCurrency"):
        if _first_attr(node, "levelOfDetail").lower() != "currency":
            continue
        account_id = _first_attr(node, "accountId", "fromAccountId")
        currency = _first_attr(node, "currency").upper()
        ending_cash = _optional_decimal(_first_attr(node, "endingCash"))
        if not account_id or not currency or not ending_cash:
            continue
        positions.append(
            Position(
                account_id=account_id,
                instrument=Instrument(
                    symbol=f"CASH.{currency}",
                    name=f"{currency} Cash",
                    asset_class=AssetClass.CASH,
                    currency=currency,
                    identifiers=(
                        InstrumentIdentifier(
                            provider="ibkr",
                            identifier_type="cash_currency",
                            value=f"{account_id}:{currency}",
                        ),
                    ),
                ),
                quantity=ending_cash,
                average_cost=Decimal("1"),
                latest_price=Decimal("1"),
                cost_basis_status=CostBasisStatus.BROKER,
            )
        )
    return positions


def _instrument_identifiers(
    node: ElementTree.Element,
) -> tuple[InstrumentIdentifier, ...]:
    identifiers: list[InstrumentIdentifier] = []
    conid = _first_attr(node, "conid", "conId")
    if conid:
        identifiers.append(
            InstrumentIdentifier(
                provider="ibkr",
                identifier_type="conid",
                value=conid,
            )
        )
    isin = _first_attr(node, "isin")
    if isin:
        identifiers.append(
            InstrumentIdentifier(
                provider="ibkr",
                identifier_type="isin",
                value=isin,
            )
        )
    local_symbol = _first_attr(node, "localSymbol")
    if local_symbol:
        venue = _first_attr(node, "listingExchange", "exchange", default="unknown")
        identifiers.append(
            InstrumentIdentifier(
                provider="ibkr",
                identifier_type="local_symbol",
                value=f"{venue}:{local_symbol}",
            )
        )
    return tuple(identifiers)


def _average_cost(
    node: ElementTree.Element,
    quantity: Decimal,
    trade_cost_basis: TradeCostBasis | None = None,
) -> tuple[Decimal, CostBasisStatus]:
    unit_cost = _first_attr(node, "costBasisPrice", "avgCost", "avgPrice", default="")
    if unit_cost and _to_decimal(unit_cost) != 0:
        return _to_decimal(unit_cost), CostBasisStatus.BROKER

    total_cost = _first_attr(node, "costBasisMoney", "costBasis", default="")
    if total_cost and quantity != 0 and _to_decimal(total_cost) != 0:
        return abs(_to_decimal(total_cost) / quantity), CostBasisStatus.BROKER

    if trade_cost_basis is not None:
        average_cost = trade_cost_basis.average_cost(quantity)
        if average_cost is not None:
            return average_cost, CostBasisStatus.TRADE_RECONSTRUCTED

    return Decimal("0"), CostBasisStatus.UNAVAILABLE


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

        basis = basis_by_position.setdefault(_position_key(node), TradeCostBasis())
        basis.quantity += _to_decimal(_first_attr(node, "quantity", "tradeQuantity", default="0"))
        basis.cost += _to_decimal(_first_attr(node, "cost", default="0"))
        basis.commission += _to_decimal(
            _first_attr(node, "ibCommission", "commission", default="0")
        )
    return basis_by_position


def _position_key(node: ElementTree.Element) -> tuple[str, str]:
    account_id = _first_attr(node, "accountId", "fromAccountId")
    conid = _first_attr(node, "conid", "conId")
    if conid:
        return account_id, f"conid:{conid}"
    symbol = _first_attr(node, "symbol", "underlyingSymbol")
    venue = _first_attr(node, "listingExchange", "exchange")
    return account_id, f"listing:{venue}:{symbol}"


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
