from fastapi.testclient import TestClient

from pa_investing.main import create_app


def test_health_route() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_portfolio_analysis_page() -> None:
    client = TestClient(create_app())

    response = client.get("/analysis/portfolio")

    assert response.status_code == 200
    assert "Portfolio Analysis" in response.text


def test_analysis_signal_page_contains_signal_id() -> None:
    client = TestClient(create_app())

    response = client.get("/analysis/signal/sig-123")

    assert response.status_code == 200
    assert "sig-123" in response.text
    assert "Signal Analysis" in response.text


def test_analysis_signal_page_escapes_signal_id_html() -> None:
    client = TestClient(create_app())

    response = client.get("/analysis/signal/<sig&123>")

    assert response.status_code == 200
    assert "Signal ID: &lt;sig&amp;123&gt;" in response.text
