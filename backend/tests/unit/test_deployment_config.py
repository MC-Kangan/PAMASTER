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


def test_compose_forwards_required_nas_provider_configuration() -> None:
    compose_text = (BACKEND_ROOT / "docker-compose.yml").read_text()

    assert 'PA_IBKR_FLEX_TOKEN: "${PA_IBKR_FLEX_TOKEN:-}"' in compose_text
    assert 'PA_IBKR_FLEX_QUERY_ID: "${PA_IBKR_FLEX_QUERY_ID:-}"' in compose_text
    assert 'PA_IBKR_FLEX_BASE_URL: "${PA_IBKR_FLEX_BASE_URL:-' in compose_text
    assert 'PA_TWELVE_DATA_API_KEY: "${PA_TWELVE_DATA_API_KEY:-}"' in compose_text
    assert 'PA_WORKFLOW_API_TOKEN: "${PA_WORKFLOW_API_TOKEN:-}"' in compose_text


def test_compose_has_health_checks_and_restart_policies() -> None:
    compose_text = (BACKEND_ROOT / "docker-compose.yml").read_text()

    assert compose_text.count("restart: unless-stopped") == 2
    assert compose_text.count("healthcheck:") == 2
    assert "condition: service_healthy" in compose_text
    assert "pg_isready" in compose_text
    assert 'http://127.0.0.1:8000/health' in compose_text


def test_docker_build_context_excludes_secrets_and_runtime_data() -> None:
    ignored_paths = {
        line.strip()
        for line in (BACKEND_ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert ".env" in ignored_paths
    assert "backups/" in ignored_paths
    assert "*.db" in ignored_paths
    assert "__pycache__/" in ignored_paths
