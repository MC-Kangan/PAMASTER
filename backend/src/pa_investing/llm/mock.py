from pa_investing.llm.interfaces import LLMProvider, NoteSummary


class MockLLMProvider(LLMProvider):
    def __init__(self, max_bullets: int = 5) -> None:
        self.max_bullets = max_bullets

    def summarize_note(self, text: str) -> NoteSummary:
        sentences = [sentence.strip() for sentence in text.split(".") if sentence.strip()]
        bullets = sentences[: self.max_bullets]
        while len(bullets) < self.max_bullets:
            bullets.append("No additional distinct claim found in captured text")
        return NoteSummary(
            bullets=bullets,
            source_excerpt=text[:240],
            token_budget_note="mock summary generated without external LLM call",
        )
