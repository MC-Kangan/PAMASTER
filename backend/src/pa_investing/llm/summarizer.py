from pa_investing.llm.interfaces import LLMProvider, NoteSummary


class NoteSummarizer:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def summarize(self, text: str) -> NoteSummary:
        normalized = " ".join(text.split())
        return self.provider.summarize_note(normalized)
