from pa_investing.finance.models import FinanceSkill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, FinanceSkill] = {}
        self._bundles: dict[str, tuple[str, ...]] = {}

    def register(self, skill: FinanceSkill) -> None:
        skill_id = skill.metadata.skill_id
        if skill_id in self._skills:
            raise ValueError(f"skill already registered: {skill_id}")
        self._skills[skill_id] = skill

    def register_bundle(
        self,
        name: str,
        skill_ids: tuple[str, ...],
    ) -> None:
        normalized = name.strip().lower()
        if normalized in self._bundles:
            raise ValueError(f"bundle already registered: {normalized}")
        self._bundles[normalized] = tuple(
            skill_id.strip().lower() for skill_id in skill_ids
        )

    def get(self, skill_id: str) -> FinanceSkill:
        normalized = skill_id.strip().lower()
        try:
            return self._skills[normalized]
        except KeyError as exc:
            raise KeyError(f"unknown finance skill: {normalized}") from exc

    def resolve_bundle(self, name: str) -> tuple[str, ...]:
        normalized = name.strip().lower()
        try:
            return self._bundles[normalized]
        except KeyError as exc:
            raise KeyError(f"unknown finance bundle: {normalized}") from exc
