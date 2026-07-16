
from pa_investing.finance.models import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisStatus,
    SkillResult,
    SkillStatus,
)
from pa_investing.finance.registry import SkillRegistry
from pa_investing.market_data.history.models import (
    HistoricalDataset,
    ProviderAttempt,
)


class FinanceOrchestrator:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def run(
        self,
        request: AnalysisRequest,
        dataset: HistoricalDataset,
        *,
        stale: bool = False,
        data_warnings: tuple[str, ...] = (),
        provider_attempts: tuple[ProviderAttempt, ...] = (),
    ) -> AnalysisResult:
        skill_ids = (
            request.skill_ids if request.skill_ids else self.registry.resolve_bundle(request.bundle)
        )
        results: list[SkillResult] = []
        summary: list[str] = []
        if stale:
            summary.append("[WARNING] Market data is stale.")
        summary.extend(
            f"[WARNING] Market data: {warning}" for warning in data_warnings
        )
        for skill_id in skill_ids:
            try:
                skill = self.registry.get(skill_id)
            except KeyError as exc:
                results.append(
                    SkillResult(
                        skill_id=skill_id,
                        status=SkillStatus.FAILED,
                        error_code="skill_not_registered",
                        error_message=str(exc),
                    )
                )
                summary.append(f"[WARNING] {skill_id} analysis unavailable.")
                continue
            try:
                result = skill.run(request, dataset)
            except Exception as exc:
                result = SkillResult(
                    skill_id=skill.metadata.skill_id,
                    status=SkillStatus.FAILED,
                    error_code="skill_execution_failed",
                    error_message=str(exc),
                )
            results.append(result)
            for finding in result.findings:
                summary.append(
                    f"[{finding.severity.value.upper()}] {skill.metadata.name}: {finding.summary}"
                )
            for warning in result.warnings:
                summary.append(f"[WARNING] {skill.metadata.name}: {warning}")
            if result.status is SkillStatus.FAILED:
                summary.append(f"[WARNING] {skill.metadata.name} analysis unavailable.")

        statuses = {result.status for result in results}
        if statuses == {SkillStatus.SUCCESS}:
            status = AnalysisStatus.SUCCESS
        elif statuses == {SkillStatus.FAILED}:
            status = AnalysisStatus.FAILED
        else:
            status = AnalysisStatus.PARTIAL
        return AnalysisResult(
            status=status,
            instrument=request.instrument,
            as_of=request.as_of,
            dataset_id=dataset.dataset_id,
            provider=dataset.provider,
            completed_through=(
                dataset.bars[-1].trading_date if dataset.bars else None
            ),
            stale=stale,
            data_warnings=list(data_warnings),
            provider_attempts=list(provider_attempts),
            skill_results=results,
            summary=summary,
        )
