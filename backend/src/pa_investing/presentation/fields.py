from dataclasses import dataclass


@dataclass(frozen=True)
class FieldDefinition:
    key: str
    label: str
    display_kind: str
    notion_property_name: str | None = None
    notion_property_type: str | None = None


SIGNAL_FIELDS: tuple[FieldDefinition, ...] = (
    FieldDefinition(
        key="symbol",
        label="Symbol",
        display_kind="text",
        notion_property_name="Symbol",
        notion_property_type="rich_text",
    ),
    FieldDefinition(
        key="signal_type",
        label="Signal Type",
        display_kind="text",
        notion_property_name="Signal Type",
        notion_property_type="select",
    ),
    FieldDefinition(
        key="severity",
        label="Severity",
        display_kind="text",
        notion_property_name="Severity",
        notion_property_type="select",
    ),
    FieldDefinition(
        key="status",
        label="Status",
        display_kind="text",
        notion_property_name="Status",
        notion_property_type="status",
    ),
    FieldDefinition(
        key="recommendation",
        label="Recommendation",
        display_kind="text",
        notion_property_name="Recommendation",
        notion_property_type="rich_text",
    ),
    FieldDefinition(
        key="audit_id",
        label="Audit ID",
        display_kind="text",
        notion_property_name="Audit ID",
        notion_property_type="rich_text",
    ),
    FieldDefinition(
        key="analytics_link",
        label="Analytics Link",
        display_kind="text",
        notion_property_name="Analytics Link",
        notion_property_type="url",
    ),
)

DAILY_REVIEW_FIELDS: tuple[FieldDefinition, ...] = (
    FieldDefinition(
        key="review_date",
        label="Review Date",
        display_kind="date",
        notion_property_name="Review Date",
        notion_property_type="date",
    ),
    FieldDefinition(
        key="snapshot_id",
        label="Snapshot ID",
        display_kind="text",
        notion_property_name="Snapshot ID",
        notion_property_type="rich_text",
    ),
    FieldDefinition(
        key="nav",
        label="NAV",
        display_kind="currency",
        notion_property_name="NAV",
        notion_property_type="number",
    ),
    FieldDefinition(
        key="gross_exposure",
        label="Gross Exposure",
        display_kind="currency",
        notion_property_name="Gross Exposure",
        notion_property_type="number",
    ),
    FieldDefinition(
        key="net_exposure",
        label="Net Exposure",
        display_kind="currency",
        notion_property_name="Net Exposure",
        notion_property_type="number",
    ),
    FieldDefinition(
        key="unrealized_pnl",
        label="Unrealized PnL",
        display_kind="currency",
        notion_property_name="Unrealized PnL",
        notion_property_type="number",
    ),
    FieldDefinition(
        key="signal_count",
        label="Signal Count",
        display_kind="count",
        notion_property_name="Signal Count",
        notion_property_type="number",
    ),
)

PERFORMANCE_SUMMARY_FIELDS: tuple[FieldDefinition, ...] = (
    FieldDefinition(key="ending_nav", label="Ending NAV", display_kind="currency"),
    FieldDefinition(key="simple_return", label="Window Return", display_kind="percent"),
    FieldDefinition(key="max_drawdown", label="Max Drawdown", display_kind="percent"),
)

PERFORMANCE_POINT_FIELDS: tuple[FieldDefinition, ...] = (
    FieldDefinition(key="observed_at", label="Observed At", display_kind="datetime"),
    FieldDefinition(key="nav", label="NAV", display_kind="currency"),
    FieldDefinition(key="unrealized_pnl", label="Unrealized PnL", display_kind="currency"),
    FieldDefinition(key="peak_nav", label="Peak NAV", display_kind="currency"),
    FieldDefinition(key="drawdown", label="Drawdown", display_kind="percent"),
    FieldDefinition(key="simple_return", label="Simple Return", display_kind="percent"),
)


def serialize_decimal(value: object) -> str:
    formatted = format(value, "f")
    if "." not in formatted:
        return formatted
    return formatted.rstrip("0").rstrip(".")
