from pa_investing.llm.mock import MockLLMProvider
from pa_investing.llm.summarizer import NoteSummarizer


def test_mock_summarizer_limits_summary_length_and_keeps_source_excerpt() -> None:
    text = "Apple reported strong services revenue. " * 40
    summarizer = NoteSummarizer(provider=MockLLMProvider(max_bullets=3))

    summary = summarizer.summarize(text)

    assert len(summary.bullets) == 3
    assert summary.source_excerpt.startswith("Apple reported strong services")
    assert summary.token_budget_note == "mock summary generated without external LLM call"
