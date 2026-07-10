from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent


def test_backend_env_file_is_ignored_by_git() -> None:
    ignored_paths = {
        line.strip()
        for line in (REPOSITORY_ROOT / ".gitignore").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "backend/.env" in ignored_paths


def test_compose_keeps_database_private_and_api_on_loopback_by_default() -> None:
    compose_text = (BACKEND_ROOT / "docker-compose.yml").read_text()
    postgres_service = compose_text.split("  backend-api:", maxsplit=1)[0]

    assert "ports:" not in postgres_service
    assert '${PA_BIND_ADDRESS:-127.0.0.1}:8000:8000' in compose_text
