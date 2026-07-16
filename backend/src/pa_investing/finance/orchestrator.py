from pa_investing.finance.models import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisStatus,
    SkillResult,
    SkillStatus,
)
from pa_investing.finance.registry import SkillRegistry
from pa_investing.market_data.history.models import HistoricalDataset


class FinanceOrchestrator:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def run(
        self,
        request: AnalysisRequest,
        dataset: HistoricalDataset,
    ) -> AnalysisResult:
        skill_ids = (
            request.skill_ids if request.skill_ids else self.registry.resolve_bundle(request.bundle)
        )
        results: list[SkillResult] = []
        summary: list[str] = []
        for skill_id in skill_ids:
            skill = self.registry.get(skill_id)
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
            skill_results=results,
            summary=summary,
        )
