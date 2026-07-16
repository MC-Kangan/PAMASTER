from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from pa_investing.domain.enums import AdjustmentMode, InstrumentScope
from pa_investing.finance.models import (
    AnalysisRequest,
    AnalysisStatus,
    Direction,
    ExecutionMode,
    Finding,
    FindingSeverity,
    SkillMetadata,
    SkillResult,
    SkillStatus,
)
from pa_investing.finance.orchestrator import FinanceOrchestrator
from pa_investing.finance.registry import SkillRegistry
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataset,
    HistoricalInstrumentRef,
    ProviderAttempt,
)


class WorkingSkill:
    metadata = SkillMetadata(
        skill_id="working.v1",
        name="Working",
        description="Returns one deterministic finding.",
        execution_mode=ExecutionMode.DETERMINISTIC,
        min_bars=1,
    )

    def run(
        self,
        request: AnalysisRequest,
        dataset: HistoricalDataset,
    ) -> SkillResult:
        return SkillResult(
            skill_id=self.metadata.skill_id,
            status=SkillStatus.SUCCESS,
            metrics={"close": dataset.bars[-1].close},
            findings=[
                Finding(
                    code="condition_present",
                    severity=FindingSeverity.WATCH,
                    direction=Direction.BULLISH,
                    summary="The condition is present.",
                )
            ],
        )


class FailingSkill:
    metadata = SkillMetadata(
        skill_id="failing.v1",
        name="Failing",
        description="Raises to test failure isolation.",
        execution_mode=ExecutionMode.DETERMINISTIC,
        min_bars=1,
    )

    def run(
        self,
        request: AnalysisRequest,
        dataset: HistoricalDataset,
    ) -> SkillResult:
        raise RuntimeError("calculation exploded")


def _dataset() -> HistoricalDataset:
    return HistoricalDataset(
        dataset_id="dataset-1",
        series_key="research|ADBE|NASDAQ|USD|all",
        provider="yahoo",
        provider_symbol="ADBE",
        provider_exchange="NASDAQ",
        currency="USD",
        fetched_at=datetime(2026, 7, 15, tzinfo=UTC),
        bars=[
            DailyBar(
                trading_date=date(2026, 7, 15),
                open=Decimal("99"),
                high=Decimal("102"),
                low=Decimal("98"),
                close=Decimal("101"),
                volume=Decimal("1000"),
                adjustment_mode=AdjustmentMode.ALL,
            )
        ],
    )


def _request(**updates: object) -> AnalysisRequest:
    values: dict[str, object] = {
        "instrument": HistoricalInstrumentRef(
            scope=InstrumentScope.RESEARCH,
            display_symbol="ADBE",
            asset_class="equity",
            currency="USD",
            exchange="NASDAQ",
            provider_symbols={"yahoo": "ADBE"},
        ),
        "as_of": date(2026, 7, 15),
    }
    values.update(updates)
    return AnalysisRequest(**values)


def test_registry_rejects_duplicate_skills() -> None:
    registry = SkillRegistry()
    registry.register(WorkingSkill())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(WorkingSkill())


def test_orchestrator_expands_bundle_and_isolates_skill_failure() -> None:
    registry = SkillRegistry()
    registry.register(WorkingSkill())
    registry.register(FailingSkill())
    registry.register_bundle(
        "test_bundle.v1",
        ("working.v1", "failing.v1"),
    )

    result = FinanceOrchestrator(registry).run(
        _request(bundle="test_bundle.v1"),
        _dataset(),
    )

    assert result.status is AnalysisStatus.PARTIAL
    assert [item.status for item in result.skill_results] == [
        SkillStatus.SUCCESS,
        SkillStatus.FAILED,
    ]
    assert result.skill_results[1].error_code == "skill_execution_failed"
    assert result.summary == [
        "[WATCH] Working: The condition is present.",
        "[WARNING] Failing analysis unavailable.",
    ]


def test_explicit_skill_ids_override_bundle_and_summary_is_reproducible() -> None:
    registry = SkillRegistry()
    registry.register(WorkingSkill())
    registry.register(FailingSkill())
    registry.register_bundle("test_bundle.v1", ("failing.v1",))
    orchestrator = FinanceOrchestrator(registry)
    request = _request(
        bundle="test_bundle.v1",
        skill_ids=("working.v1",),
    )

    first = orchestrator.run(request, _dataset())
    second = orchestrator.run(request, _dataset())

    assert first.status is AnalysisStatus.SUCCESS
    assert [item.skill_id for item in first.skill_results] == ["working.v1"]
    assert first.summary == second.summary


def test_orchestrator_isolates_unknown_explicit_skill() -> None:
    registry = SkillRegistry()
    registry.register(WorkingSkill())

    result = FinanceOrchestrator(registry).run(
        _request(skill_ids=("missing.v1", "working.v1")),
        _dataset(),
    )

    assert result.status is AnalysisStatus.PARTIAL
    assert result.skill_results[0].skill_id == "missing.v1"
    assert result.skill_results[0].status is SkillStatus.FAILED
    assert result.skill_results[1].status is SkillStatus.SUCCESS


def test_registry_rejects_bundle_with_unknown_skill() -> None:
    registry = SkillRegistry()

    with pytest.raises(ValueError, match="unknown finance skill"):
        registry.register_bundle("broken.v1", ("missing.v1",))


def test_orchestrator_propagates_market_data_provenance() -> None:
    registry = SkillRegistry()
    registry.register(WorkingSkill())
    registry.register_bundle("test_bundle.v1", ("working.v1",))
    attempt = ProviderAttempt(
        provider="yahoo",
        accepted=False,
        started_at=datetime(2026, 7, 15, tzinfo=UTC),
        finished_at=datetime(2026, 7, 15, tzinfo=UTC),
        error_code="request_failed",
        message="provider unavailable",
    )

    result = FinanceOrchestrator(registry).run(
        _request(bundle="test_bundle.v1"),
        _dataset(),
        stale=True,
        data_warnings=("missing expected session: 2026-07-14",),
        provider_attempts=(attempt,),
    )

    assert result.stale is True
    assert result.data_warnings == ["missing expected session: 2026-07-14"]
    assert result.provider_attempts == [attempt]
    assert result.summary[0] == "[WARNING] Market data is stale."
