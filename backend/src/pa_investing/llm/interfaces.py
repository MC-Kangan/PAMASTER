from abc import ABC, abstractmethod

from pydantic import BaseModel


class NoteSummary(BaseModel):
    bullets: list[str]
    source_excerpt: str
    token_budget_note: str


class LLMProvider(ABC):
    @abstractmethod
    def summarize_note(self, text: str) -> NoteSummary:
        raise NotImplementedError
