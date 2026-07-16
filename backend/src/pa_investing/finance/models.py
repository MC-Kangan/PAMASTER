from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from pa_investing.market_data.history.models import (
    HistoricalDataset,
    HistoricalInstrumentRef,
    ProviderAttempt,
)

MetricValue = Decimal | int | float | str | bool | None


class ExecutionMode(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"


class SkillStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class AnalysisStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class Direction(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class FindingSeverity(StrEnum):
    INFO = "info"
    WATCH = "watch"
    ATTENTION = "attention"


class SkillMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_id: str
    name: str
    description: str
    execution_mode: ExecutionMode
    min_bars: int = Field(ge=1)
    default_thresholds: dict[str, Decimal] = Field(default_factory=dict)

    @field_validator("skill_id")
    @classmethod
    def require_versioned_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if ".v" not in normalized:
            raise ValueError("skill_id must include a version suffix")
        return normalized

    def resolve_thresholds(
        self,
        overrides: dict[str, Decimal],
    ) -> dict[str, Decimal]:
        unknown = set(overrides) - set(self.default_thresholds)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"unknown threshold for {self.skill_id}: {names}")
        if any(not value.is_finite() for value in overrides.values()):
            raise ValueError(f"thresholds for {self.skill_id} must be finite")
        return {**self.default_thresholds, **overrides}


class AnalysisRequest(BaseModel):
    instrument: HistoricalInstrumentRef
    as_of: date
    lookback_days: int = Field(default=365, ge=1)
    bundle: str = "daily_market_review.v1"
    skill_ids: tuple[str, ...] = ()
    threshold_overrides: dict[str, dict[str, Decimal]] = Field(default_factory=dict)

    @field_validator("bundle")
    @classmethod
    def normalize_bundle(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("skill_ids")
    @classmethod
    def normalize_skill_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(item.strip().lower() for item in value)

    @model_validator(mode="after")
    def require_supported_asset_class(self) -> Self:
        if self.instrument.asset_class.lower() not in {"equity", "etf"}:
            raise ValueError("finance analysis v1 supports equities and ETFs only")
        return self


class Finding(BaseModel):
    code: str
    severity: FindingSeverity
    direction: Direction
    summary: str
    observed_on: date | None = None
    values: dict[str, MetricValue] = Field(default_factory=dict)


class SkillResult(BaseModel):
    skill_id: str
    status: SkillStatus
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class AnalysisResult(BaseModel):
    status: AnalysisStatus
    instrument: HistoricalInstrumentRef
    as_of: date
    dataset_id: str
    provider: str
    completed_through: date | None
    stale: bool = False
    data_warnings: list[str] = Field(default_factory=list)
    provider_attempts: list[ProviderAttempt] = Field(default_factory=list)
    skill_results: list[SkillResult]
    summary: list[str]


class FinanceSkill(Protocol):
    metadata: SkillMetadata

    def run(
        self,
        request: AnalysisRequest,
        dataset: HistoricalDataset,
    ) -> SkillResult: ...
