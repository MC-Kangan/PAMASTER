from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree

from pa_investing.domain.models import (
    Account,
    BrokerDailyNav,
    BrokerDailyPnl,
    PortfolioSnapshot,
)


@dataclass(frozen=True)
class IbkrFlexDailyNav:
    account_id: str
    report_date: date
    starting_value: Decimal
    ending_value: Decimal
    mtm: Decimal
    realized: Decimal
    change_in_unrealized: Decimal
    deposits_withdrawals: Decimal
    commissions: Decimal
    dividends: Decimal
    interest: Decimal
    currency: str


@dataclass(frozen=True)
class IbkrFlexDailyPosition:
    account_id: str
    report_date: date
    symbol: str
    asset_category: str
    currency: str
    quantity: Decimal
    mark_price: Decimal
    position_value: Decimal
    position_value_in_base: Decimal
    cost_basis_money: Decimal
    fifo_unrealized_pnl: Decimal
    unrealized_capital_gains_pnl: Decimal
    unrealized_fx_pnl: Decimal
    percent_of_nav: Decimal


@dataclass(frozen=True)
class IbkrFlexDailySecurityPnl:
    account_id: str
    report_date: date
    symbol: str
    asset_category: str
    previous_close_quantity: Decimal
    previous_close_price: Decimal
    close_quantity: Decimal
    close_price: Decimal
    transaction_mtm: Decimal
    prior_open_mtm: Decimal
    commissions: Decimal
    total: Decimal
    is_total: bool = False


@dataclass(frozen=True)
class IbkrFlexTradeSummary:
    account_id: str
    trade_date: date
    symbol: str
    asset_category: str
    currency: str
    buy_sell: str
    quantity: Decimal
    trade_price: Decimal
    commission: Decimal
    proceeds: Decimal
    cost: Decimal
    net_cash: Decimal
    realized_pnl: Decimal


@dataclass(frozen=True)
class IbkrFlexSecurityInfo:
    symbol: str
    asset_category: str
    currency: str
    description: str
    conid: str
    isin: str
    figi: str
    listing_exchange: str
    multiplier: Decimal


@dataclass(frozen=True)
class IbkrFlexDailyStatement:
    account_id: str
    report_date: date
    nav: IbkrFlexDailyNav | None
    positions: tuple[IbkrFlexDailyPosition, ...]
    security_pnl: tuple[IbkrFlexDailySecurityPnl, ...]
    trades: tuple[IbkrFlexTradeSummary, ...]


@dataclass(frozen=True)
class IbkrFlexHistory:
    statements: tuple[IbkrFlexDailyStatement, ...]
    securities: tuple[IbkrFlexSecurityInfo, ...]

    @property
    def accounts(self) -> tuple[Account, ...]:
        seen: dict[str, Account] = {}
        for statement in self.statements:
            currency = statement.nav.currency if statement.nav is not None else "USD"
            seen.setdefault(
                statement.account_id,
                Account(
                    account_id=statement.account_id,
                    name=statement.account_id,
                    source="ibkr-flex",
                    base_currency=currency,
                ),
            )
        return tuple(seen.values())

    def to_portfolio_snapshots(self) -> tuple[PortfolioSnapshot, ...]:
        grouped: dict[tuple[date, str], list[IbkrFlexDailyStatement]] = {}
        for statement in self.statements:
            if statement.nav is None:
                continue
            grouped.setdefault(
                (statement.report_date, statement.nav.currency),
                [],
            ).append(statement)

        snapshots: list[PortfolioSnapshot] = []
        for (report_date, currency), statements in sorted(grouped.items()):
            positions = [
                position
                for statement in statements
                for position in statement.positions
            ]
            gross_exposure = sum(
                abs(position.position_value_in_base)
                for position in positions
            )
            net_exposure = sum(
                position.position_value_in_base
                for position in positions
            )
            unrealized_pnl = sum(
                position.fifo_unrealized_pnl
                for position in positions
            )
            observed_at = datetime.combine(
                report_date,
                datetime.min.time(),
                tzinfo=UTC,
            )
            snapshots.append(
                PortfolioSnapshot(
                    snapshot_id=(
                        f"ibkr-flex-history:portfolio:{currency}:"
                        f"{report_date.isoformat()}"
                    ),
                    observed_at=observed_at,
                    base_currency=currency,
                    nav=sum(
                        (
                            statement.nav.ending_value
                            for statement in statements
                            if statement.nav is not None
                        ),
                        Decimal("0"),
                    ),
                    gross_exposure=gross_exposure,
                    net_exposure=net_exposure,
                    unrealized_pnl=unrealized_pnl,
                    position_count=len(positions),
                    valued_position_count=len(
                        [
                            position
                            for position in positions
                            if position.position_value_in_base != 0
                        ]
                    ),
                    reporting_coverage=Decimal("1"),
                )
            )
        return tuple(snapshots)

    def to_broker_daily_pnl(self) -> tuple[BrokerDailyPnl, ...]:
        points: list[BrokerDailyPnl] = []
        for statement in self.statements:
            for item in statement.security_pnl:
                report_date = item.report_date
                if report_date == date.min:
                    report_date = statement.report_date
                points.append(
                    BrokerDailyPnl(
                        account_id=item.account_id,
                        report_date=report_date,
                        provider="ibkr-flex",
                        symbol=item.symbol or "__TOTAL__",
                        asset_class=item.asset_category or "TOTAL",
                        previous_close_quantity=item.previous_close_quantity,
                        previous_close_price=item.previous_close_price,
                        close_quantity=item.close_quantity,
                        close_price=item.close_price,
                        transaction_mtm=item.transaction_mtm,
                        prior_open_mtm=item.prior_open_mtm,
                        commissions=item.commissions,
                        total=item.total,
                        is_total=item.is_total,
                    )
                )
        return tuple(points)

    def to_broker_daily_nav(self) -> tuple[BrokerDailyNav, ...]:
        points: list[BrokerDailyNav] = []
        for statement in self.statements:
            if statement.nav is None:
                continue
            points.append(
                BrokerDailyNav(
                    account_id=statement.nav.account_id,
                    report_date=statement.nav.report_date,
                    provider="ibkr-flex",
                    currency=statement.nav.currency,
                    starting_value=statement.nav.starting_value,
                    ending_value=statement.nav.ending_value,
                    mtm=statement.nav.mtm,
                    realized=statement.nav.realized,
                    change_in_unrealized=statement.nav.change_in_unrealized,
                    deposits_withdrawals=statement.nav.deposits_withdrawals,
                    commissions=statement.nav.commissions,
                    dividends=statement.nav.dividends,
                    interest=statement.nav.interest,
                )
            )
        return tuple(points)


def parse_ibkr_flex_history_file(path: str | Path) -> IbkrFlexHistory:
    return parse_ibkr_flex_history_root(ElementTree.parse(path).getroot())


def parse_ibkr_flex_history_xml(xml_text: str) -> IbkrFlexHistory:
    return parse_ibkr_flex_history_root(ElementTree.fromstring(xml_text))


def parse_ibkr_flex_history_root(root: ElementTree.Element) -> IbkrFlexHistory:
    statements: list[IbkrFlexDailyStatement] = []
    security_info: dict[tuple[str, str, str], IbkrFlexSecurityInfo] = {}
    for statement in root.findall(".//FlexStatement"):
        account_id = statement.get("accountId", "")
        report_date = _date(statement.get("fromDate", ""))
        nav = _nav(statement.find("ChangeInNAV"), account_id)
        positions = tuple(
            _position(node, account_id, report_date)
            for node in statement.findall(".//OpenPosition")
        )
        security_pnl = tuple(
            _security_pnl(node, account_id)
            for node in statement.findall(".//MTMPerformanceSummaryUnderlying")
        )
        trades = tuple(
            _trade_summary(node, account_id)
            for node in statement.findall(".//SymbolSummary")
        )
        statements.append(
            IbkrFlexDailyStatement(
                account_id=account_id,
                report_date=report_date,
                nav=nav,
                positions=positions,
                security_pnl=security_pnl,
                trades=trades,
            )
        )
        for node in statement.findall(".//SecurityInfo"):
            info = _security_info(node)
            security_info.setdefault(
                (info.symbol, info.asset_category, info.currency),
                info,
            )
    return IbkrFlexHistory(
        statements=tuple(statements),
        securities=tuple(security_info.values()),
    )


def _nav(
    node: ElementTree.Element | None,
    fallback_account_id: str,
) -> IbkrFlexDailyNav | None:
    if node is None:
        return None
    return IbkrFlexDailyNav(
        account_id=node.get("accountId") or fallback_account_id,
        report_date=_date(node.get("toDate", "")),
        starting_value=_decimal(node.get("startingValue")),
        ending_value=_decimal(node.get("endingValue")),
        mtm=_decimal(node.get("mtm")),
        realized=_decimal(node.get("realized")),
        change_in_unrealized=_decimal(node.get("changeInUnrealized")),
        deposits_withdrawals=_decimal(node.get("depositsWithdrawals")),
        commissions=_decimal(node.get("commissions")),
        dividends=_decimal(node.get("dividends")),
        interest=_decimal(node.get("interest")),
        currency=(node.get("currency") or "").upper(),
    )


def _position(
    node: ElementTree.Element,
    fallback_account_id: str,
    report_date: date,
) -> IbkrFlexDailyPosition:
    return IbkrFlexDailyPosition(
        account_id=node.get("accountId") or fallback_account_id,
        report_date=report_date,
        symbol=(node.get("symbol") or "").upper(),
        asset_category=node.get("assetCategory") or "",
        currency=(node.get("currency") or "").upper(),
        quantity=_decimal(node.get("position") or node.get("quantity")),
        mark_price=_decimal(node.get("markPrice")),
        position_value=_decimal(node.get("positionValue")),
        position_value_in_base=_decimal(
            node.get("positionValueInBase") or node.get("positionValue")
        ),
        cost_basis_money=_decimal(node.get("costBasisMoney")),
        fifo_unrealized_pnl=_decimal(node.get("fifoPnlUnrealized")),
        unrealized_capital_gains_pnl=_decimal(
            node.get("unrealizedCapitalGainsPnl")
        ),
        unrealized_fx_pnl=_decimal(node.get("unrealizedlFxPnl")),
        percent_of_nav=_decimal(node.get("percentOfNAV")),
    )


def _security_pnl(
    node: ElementTree.Element,
    fallback_account_id: str,
) -> IbkrFlexDailySecurityPnl:
    symbol = (node.get("symbol") or "").upper()
    asset_category = node.get("assetCategory") or ""
    return IbkrFlexDailySecurityPnl(
        account_id=node.get("accountId") or fallback_account_id,
        report_date=_date(node.get("reportDate", "")),
        symbol=symbol,
        asset_category=asset_category,
        previous_close_quantity=_decimal(node.get("prevCloseQuantity")),
        previous_close_price=_decimal(node.get("prevClosePrice")),
        close_quantity=_decimal(node.get("closeQuantity")),
        close_price=_decimal(node.get("closePrice")),
        transaction_mtm=_decimal(node.get("transactionMtm")),
        prior_open_mtm=_decimal(node.get("priorOpenMtm")),
        commissions=_decimal(node.get("commissions")),
        total=_decimal(node.get("total")),
        is_total=not symbol and not asset_category,
    )


def _trade_summary(
    node: ElementTree.Element,
    fallback_account_id: str,
) -> IbkrFlexTradeSummary:
    return IbkrFlexTradeSummary(
        account_id=node.get("accountId") or fallback_account_id,
        trade_date=_date(node.get("tradeDate", "")),
        symbol=(node.get("symbol") or "").upper(),
        asset_category=node.get("assetCategory") or "",
        currency=(node.get("currency") or "").upper(),
        buy_sell=(node.get("buySell") or "").upper(),
        quantity=_decimal(node.get("quantity")),
        trade_price=_decimal(node.get("tradePrice")),
        commission=_decimal(node.get("ibCommission")),
        proceeds=_decimal(node.get("proceeds")),
        cost=_decimal(node.get("cost")),
        net_cash=_decimal(node.get("netCash")),
        realized_pnl=_decimal(
            node.get("fifoPnlRealized")
            or node.get("capitalGainsPnl")
            or node.get("realizedPnl")
        ),
    )


def _security_info(node: ElementTree.Element) -> IbkrFlexSecurityInfo:
    return IbkrFlexSecurityInfo(
        symbol=(node.get("symbol") or "").upper(),
        asset_category=node.get("assetCategory") or "",
        currency=(node.get("currency") or "").upper(),
        description=node.get("description") or "",
        conid=node.get("conid") or "",
        isin=node.get("isin") or "",
        figi=node.get("figi") or "",
        listing_exchange=node.get("listingExchange") or "",
        multiplier=_decimal(node.get("multiplier"), default=Decimal("1")),
    )


def _date(value: str) -> date:
    if not value:
        return date.min
    return datetime.strptime(value, "%Y%m%d").date()


def _decimal(value: str | None, *, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(value)
    except InvalidOperation:
        return default
