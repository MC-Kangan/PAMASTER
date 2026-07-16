import logging
from dataclasses import dataclass, field
from decimal import Decimal

from pa_investing.analytics.metrics import calculate_exposure_by_currency
from pa_investing.domain.enums import AssetClass, CostBasisStatus
from pa_investing.domain.models import Account, Position, Signal
from pa_investing.notion.client import NotionClient
from pa_investing.notion.schemas import NotionPagePayload, NotionPropertyValue
from pa_investing.presentation.fields import serialize_decimal
from pa_investing.workflows.agent_api import DailyReviewResult

logger = logging.getLogger(__name__)

PORTFOLIO_DATABASES = frozenset({"Settings", "Accounts", "Positions"})
PORTFOLIO_BASE_CURRENCY_KEY = "portfolio_base_currency"
SUPPORTED_BASE_CURRENCIES = frozenset({"USD", "GBP"})


@dataclass(frozen=True)
class PortfolioNotionInputs:
    base_currency: str | None = None
    cost_overrides: dict[str, Decimal | None] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


class NotionSync:
    def __init__(self, client: NotionClient) -> None:
        self.client = client

    def portfolio_databases_configured(self) -> bool:
        return all(
            self.client.is_database_configured(database_name)
            for database_name in PORTFOLIO_DATABASES
        )

    def read_portfolio_inputs(self) -> PortfolioNotionInputs:
        if not self.portfolio_databases_configured():
            return PortfolioNotionInputs()

        warnings: list[str] = []
        base_currency: str | None = None
        for row in self.client.query_database("Settings"):
            if row.external_id != "portfolio-settings":
                continue
            raw_currency = row.properties.get("Base Currency")
            if isinstance(raw_currency, str):
                normalized = raw_currency.upper().strip()
                if normalized in SUPPORTED_BASE_CURRENCIES:
                    base_currency = normalized
                elif normalized:
                    warnings.append(
                        f"Ignored unsupported Notion base currency: {raw_currency}"
                    )
            break

        cost_overrides: dict[str, Decimal | None] = {}
        for row in self.client.query_database("Positions"):
            if "Cost Override" not in row.properties:
                continue
            value = row.properties["Cost Override"]
            if value is None:
                cost_overrides[row.external_id] = None
            elif isinstance(value, Decimal) and value >= 0:
                cost_overrides[row.external_id] = value
            else:
                warnings.append(
                    f"Ignored invalid cost override for {row.external_id}: {value}"
                )

        for warning in warnings:
            logger.warning(warning)
        return PortfolioNotionInputs(
            base_currency=base_currency,
            cost_overrides=cost_overrides,
            warnings=tuple(warnings),
        )

    @staticmethod
    def position_external_id(position: Position) -> str:
        instrument_reference = (
            position.instrument.instrument_id or position.instrument.symbol
        )
        return f"position:{position.account_id}:{instrument_reference}"

    @staticmethod
    def account_external_id(account: Account) -> str:
        return f"account:{account.account_id}"

    def build_settings_payload(self) -> NotionPagePayload:
        return NotionPagePayload(
            title="Portfolio Settings",
            properties={},
            body=(
                "Portfolio configuration\n"
                "Base Currency is managed in Notion. Converted portfolio values "
                "will be available after FX support is enabled."
            ),
        )

    def build_account_payload(
        self,
        account: Account,
        positions: list[Position],
    ) -> NotionPagePayload:
        account_positions = [
            position for position in positions if position.account_id == account.account_id
        ]
        exposure = calculate_exposure_by_currency(account_positions)
        currencies = sorted(exposure)
        breakdown = [
            f"- {currency}: {self._format_decimal(value)}"
            for currency, value in sorted(exposure.items())
        ] or ["- No open positions."]
        reporting_values = [
            position.reporting_market_value
            for position in account_positions
            if position.reporting_market_value is not None
        ]
        reporting_currency = next(
            (
                position.reporting_currency
                for position in account_positions
                if position.reporting_currency is not None
            ),
            None,
        )
        reporting_coverage = (
            Decimal("1")
            if not account_positions
            else Decimal(len(reporting_values)) / Decimal(len(account_positions))
        )
        account_properties = {
            "Account ID": NotionPropertyValue.rich_text(account.account_id),
            "Source": NotionPropertyValue.select(account.source),
            "Base Currency": NotionPropertyValue.select(account.base_currency),
            "Position Count": NotionPropertyValue.number(len(account_positions)),
            "Currencies": NotionPropertyValue.rich_text(", ".join(currencies)),
            "Reporting Coverage": NotionPropertyValue.number(reporting_coverage),
        }
        if reporting_values and reporting_currency:
            account_properties["Reporting Currency"] = NotionPropertyValue.select(
                reporting_currency
            )
            account_properties["Reporting Market Value"] = NotionPropertyValue.number(
                sum(reporting_values, Decimal("0"))
            )
        return NotionPagePayload(
            title=account.name,
            properties=account_properties,
            body="\n".join(
                [
                    "Account Overview",
                    f"- Open Positions: {len(account_positions)}",
                    f"- Account Base Currency: {account.base_currency}",
                    "",
                    "Market Value by Currency",
                    *breakdown,
                    "",
                    (
                        "Reporting values use the configured portfolio currency."
                        if reporting_values
                        else "Values are not combined because required FX is unavailable."
                    ),
                ]
            ),
        )

    def build_position_payload(self, position: Position) -> NotionPagePayload:
        properties = {
            "Symbol": NotionPropertyValue.rich_text(position.instrument.symbol),
            "Account": NotionPropertyValue.rich_text(position.account_id),
            "Asset Class": NotionPropertyValue.select(
                position.instrument.asset_class.value
            ),
            "Quantity": NotionPropertyValue.number(position.quantity),
            "Currency": NotionPropertyValue.select(position.instrument.currency),
            "Market Value": NotionPropertyValue.number(position.market_value),
            "Cost Status": NotionPropertyValue.select(position.cost_basis_status.value),
            "Effective Cost": NotionPropertyValue.number(position.average_cost),
            "Broker Cost": NotionPropertyValue.number(
                position.broker_average_cost or Decimal("0")
            ),
        }
        if position.instrument.instrument_id is not None:
            properties["Instrument ID"] = NotionPropertyValue.rich_text(
                position.instrument.instrument_id
            )
        if position.instrument.venue is not None:
            properties["Venue"] = NotionPropertyValue.select(
                position.instrument.venue
            )
        if position.latest_price is not None:
            properties["Price"] = NotionPropertyValue.number(position.latest_price)
        if position.latest_price_observed_at is not None:
            properties["Price As Of"] = NotionPropertyValue.rich_text(
                position.latest_price_observed_at.isoformat()
            )
        if position.latest_price_provider is not None:
            properties["Price Source"] = NotionPropertyValue.select(
                position.latest_price_provider
            )
        if position.latest_price_quality is not None:
            properties["Price Quality"] = NotionPropertyValue.select(
                position.latest_price_quality.value
            )
        if position.reporting_currency is not None:
            properties["Reporting Currency"] = NotionPropertyValue.select(
                position.reporting_currency
            )
        if position.fx_rate is not None:
            properties["FX Rate"] = NotionPropertyValue.number(position.fx_rate)
        if position.fx_observed_at is not None:
            properties["FX As Of"] = NotionPropertyValue.rich_text(
                position.fx_observed_at.isoformat()
            )
        if position.reporting_currency is not None:
            properties["FX Status"] = NotionPropertyValue.select(
                self._fx_status(position)
            )
        if position.reporting_market_value is not None:
            properties["Reporting Market Value"] = NotionPropertyValue.number(
                position.reporting_market_value
            )
        if position.reporting_unrealized_pnl is not None:
            properties["Reporting Unrealized PnL"] = NotionPropertyValue.number(
                position.reporting_unrealized_pnl
            )
        if position.cost_basis_status != CostBasisStatus.UNAVAILABLE:
            properties["Unrealized PnL"] = NotionPropertyValue.number(
                position.unrealized_pnl
            )

        return NotionPagePayload(
            title=position.instrument.symbol,
            properties=properties,
            body="\n".join(
                [
                    "Position Overview",
                    f"- Account: {position.account_id}",
                    f"- Instrument: {position.instrument.name}",
                    f"- Quantity: {self._format_decimal(position.quantity)}",
                    f"- Currency: {position.instrument.currency}",
                    f"- Cost Status: {self._humanize_token(position.cost_basis_status.value)}",
                ]
            ),
        )

    def sync_portfolio(
        self,
        accounts: list[Account],
        positions: list[Position],
    ) -> None:
        if not self.portfolio_databases_configured():
            return
        self.client.upsert_page(
            "Settings",
            "portfolio-settings",
            self.build_settings_payload(),
        )
        for account in accounts:
            self.client.upsert_page(
                "Accounts",
                self.account_external_id(account),
                self.build_account_payload(account, positions),
            )
        for position in positions:
            self.client.upsert_page(
                "Positions",
                self.position_external_id(position),
                self.build_position_payload(position),
            )

    def build_signal_payload(self, signal: Signal) -> NotionPagePayload:
        return NotionPagePayload(
            title=(
                f"{signal.symbol} {self._humanize_token(signal.signal_type.value)} "
                f"{self._humanize_token(signal.severity.value)}"
            ),
            properties={
                "Symbol": NotionPropertyValue.rich_text(signal.symbol),
                "Signal Type": NotionPropertyValue.select(signal.signal_type.value),
                "Severity": NotionPropertyValue.select(signal.severity.value),
                "Status": NotionPropertyValue.status(signal.status.value),
                "Recommendation": NotionPropertyValue.rich_text(
                    signal.deterministic_recommendation
                ),
                "Audit ID": NotionPropertyValue.rich_text(signal.audit_id),
                **(
                    {"Analytics Link": NotionPropertyValue.url(signal.analytics_path)}
                    if signal.analytics_path
                    else {}
                ),
            },
            body=self._build_signal_body(signal),
        )

    def sync_signal(self, signal: Signal) -> str:
        payload = self.build_signal_payload(signal)
        return self.client.upsert_page("Signals", signal.signal_id, payload)

    def build_daily_review_payload(self, result: DailyReviewResult) -> NotionPagePayload:
        snapshot = result.snapshot
        return NotionPagePayload(
            title=f"Daily Review {snapshot.observed_at.date().isoformat()}",
            properties={
                "Review Date": NotionPropertyValue.date(snapshot.observed_at.date()),
                "Snapshot ID": NotionPropertyValue.rich_text(snapshot.snapshot_id),
                "NAV": NotionPropertyValue.number(snapshot.nav),
                "Gross Exposure": NotionPropertyValue.number(snapshot.gross_exposure),
                "Net Exposure": NotionPropertyValue.number(snapshot.net_exposure),
                "Unrealized PnL": NotionPropertyValue.number(snapshot.unrealized_pnl),
                "Signal Count": NotionPropertyValue.number(len(result.signals)),
            },
            body=self._build_daily_review_body(result),
        )

    def sync_daily_review(
        self,
        result: DailyReviewResult,
        external_id: str | None = None,
    ) -> str:
        payload = self.build_daily_review_payload(result)
        return self.client.upsert_page(
            "Daily Review",
            external_id or result.snapshot.snapshot_id,
            payload,
        )

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return serialize_decimal(value)

    @classmethod
    def _build_signal_body(cls, signal: Signal) -> str:
        lines = [
            "Action",
            f"- Recommendation: {signal.deterministic_recommendation}",
            "",
            "Signal",
            f"- Symbol: {signal.symbol}",
            f"- Type: {cls._humanize_token(signal.signal_type.value)}",
            f"- Severity: {cls._humanize_token(signal.severity.value)}",
            f"- Status: {cls._humanize_token(signal.status.value)}",
            "",
            "Context",
            f"- {signal.message}",
            "",
            "Audit",
            f"- Audit ID: {signal.audit_id}",
        ]
        if signal.analytics_path:
            lines.append(f"- Analytics: {signal.analytics_path}")
        return "\n".join(lines)

    @classmethod
    def _build_daily_review_body(cls, result: DailyReviewResult) -> str:
        snapshot = result.snapshot
        lines = [
            "Overview",
            f"- Snapshot Time: {snapshot.observed_at.isoformat()}",
            f"- Snapshot ID: {snapshot.snapshot_id}",
            f"- Signal Count: {len(result.signals)}",
            "",
            "Portfolio",
            f"- NAV: {cls._format_decimal(snapshot.nav)}",
            f"- Gross Exposure: {cls._format_decimal(snapshot.gross_exposure)}",
            f"- Net Exposure: {cls._format_decimal(snapshot.net_exposure)}",
            f"- Unrealized PnL: {cls._format_decimal(snapshot.unrealized_pnl)}",
            f"- Reporting Currency: {snapshot.base_currency}",
            f"- Reporting Coverage: {cls._format_percent(snapshot.reporting_coverage)}",
            "",
            "Data Quality",
            *cls._data_quality_lines(result.positions),
            "",
            "Allocation",
            *cls._allocation_lines(result.positions, snapshot.nav),
            "",
            "Top Holdings",
            *cls._top_holding_lines(result.positions, snapshot.nav),
            "",
            "Signals",
            *cls._signal_summary_lines(result),
            "",
            "Next",
            "- News overview section reserved for a future agent pass.",
        ]
        return "\n".join(lines)

    @classmethod
    def _data_quality_lines(cls, positions: list[Position]) -> list[str]:
        missing_fx = [
            position.instrument.symbol
            for position in positions
            if position.reporting_currency is not None and position.fx_rate is None
        ]
        stale_fx = [
            position.instrument.symbol
            for position in positions
            if position.reporting_currency is not None and position.fx_stale
        ]
        lines: list[str] = []
        if missing_fx:
            lines.append("- Missing FX: " + ", ".join(sorted(missing_fx)))
        if stale_fx:
            lines.append("- Stale FX*: " + ", ".join(sorted(stale_fx)))
        return lines or ["- Quote and FX coverage complete."]

    @classmethod
    def _allocation_lines(
        cls,
        positions: list[Position],
        portfolio_nav: Decimal,
    ) -> list[str]:
        if portfolio_nav == 0:
            return ["- No allocation available."]
        reporting_mode = any(
            position.reporting_currency is not None for position in positions
        )
        exposure_by_asset_class: dict[AssetClass, Decimal] = {}
        for position in positions:
            value = (
                position.reporting_market_value
                if reporting_mode
                else position.market_value
            )
            if value is None:
                continue
            asset_class = position.instrument.asset_class
            exposure_by_asset_class[asset_class] = (
                exposure_by_asset_class.get(asset_class, Decimal("0")) + abs(value)
            )
        ordered_asset_classes = sorted(
            exposure_by_asset_class.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        return [
            f"- {cls._asset_class_label(asset_class)}: "
            f"{cls._format_percent(exposure / portfolio_nav)}"
            for asset_class, exposure in ordered_asset_classes
        ]

    @classmethod
    def _top_holding_lines(
        cls,
        positions: list[Position],
        portfolio_nav: Decimal,
        *,
        limit: int = 5,
    ) -> list[str]:
        if portfolio_nav == 0 or not positions:
            return ["- No holdings available."]
        reporting_mode = any(
            position.reporting_currency is not None for position in positions
        )
        valued_positions = [
            (
                position,
                position.reporting_market_value
                if reporting_mode
                else position.market_value,
            )
            for position in positions
        ]
        ranked_positions = sorted(
            (
                (position, value)
                for position, value in valued_positions
                if value is not None
            ),
            key=lambda item: abs(item[1]),
            reverse=True,
        )[:limit]
        return [
            (
                f"- {position.instrument.symbol} "
                f"({cls._asset_class_label(position.instrument.asset_class)}, "
                f"{position.instrument.currency}) - "
                f"{cls._format_percent(abs(value) / portfolio_nav)} "
                "of portfolio"
            )
            for position, value in ranked_positions
        ]

    @classmethod
    def _signal_summary_lines(cls, result: DailyReviewResult) -> list[str]:
        if not result.signals:
            return ["- No signals generated."]
        return [
            f"- {signal.symbol}: {signal.deterministic_recommendation}"
            for signal in result.signals
        ]

    @staticmethod
    def _humanize_token(value: str) -> str:
        return value.replace("_", " ").title()

    @staticmethod
    def _fx_status(position: Position) -> str:
        if position.fx_rate is None:
            return "missing"
        if position.fx_stale:
            return "stale"
        return "current"

    @staticmethod
    def _asset_class_label(asset_class: AssetClass) -> str:
        if asset_class == AssetClass.ETF:
            return asset_class.value.upper()
        return asset_class.value.title()

    @staticmethod
    def _format_percent(value: Decimal) -> str:
        return f"{(value * Decimal('100')).quantize(Decimal('0.1'))}%"
