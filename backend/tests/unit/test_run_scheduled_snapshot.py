import json

import httpx
import pytest

from pa_investing.scripts.run_scheduled_snapshot import main, run_scheduled_snapshot


def test_run_scheduled_snapshot_posts_empty_stop_prices_to_default_backend(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PA_WORKFLOW_API_TOKEN", "scheduled-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "http://127.0.0.1:8000/workflows/refresh-and-sync"
        assert json.loads(request.content) == {"stop_prices": {}}
        assert request.headers["Authorization"] == "Bearer scheduled-secret"
        assert request.extensions["timeout"] == {
            "connect": 300.0,
            "read": 300.0,
            "write": 300.0,
            "pool": 300.0,
        }
        return httpx.Response(
            200,
            json={"snapshot_id": "snapshot-1", "nav": "12500", "signal_count": 2},
        )

    run_scheduled_snapshot(transport=httpx.MockTransport(handler))

    assert capsys.readouterr().out == "Scheduled snapshot completed: snapshot_id=snapshot-1\n"


def test_main_uses_explicit_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PA_WORKFLOW_API_TOKEN", "scheduled-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://host.example:9000/workflows/refresh-and-sync"
        return httpx.Response(200, json={"snapshot_id": "snapshot-2"})

    main(
        ["--base-url", "http://host.example:9000/"],
        transport=httpx.MockTransport(handler),
    )


def test_run_scheduled_snapshot_fails_for_non_success_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PA_WORKFLOW_API_TOKEN", "scheduled-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "service unavailable"})

    with pytest.raises(httpx.HTTPStatusError):
        run_scheduled_snapshot(transport=httpx.MockTransport(handler))


def test_run_scheduled_snapshot_requires_workflow_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PA_WORKFLOW_API_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="PA_WORKFLOW_API_TOKEN is required"):
        run_scheduled_snapshot(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
