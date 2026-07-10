import argparse
import os
from collections.abc import Sequence

import httpx

DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
SCHEDULED_SNAPSHOT_TIMEOUT_SECONDS = 300.0


def run_scheduled_snapshot(
    *,
    base_url: str = DEFAULT_BACKEND_URL,
    transport: httpx.BaseTransport | None = None,
) -> None:
    workflow_api_token = os.environ.get("PA_WORKFLOW_API_TOKEN", "")
    if not workflow_api_token.strip():
        raise RuntimeError("PA_WORKFLOW_API_TOKEN is required")

    with httpx.Client(
        transport=transport,
        timeout=SCHEDULED_SNAPSHOT_TIMEOUT_SECONDS,
    ) as client:
        response = client.post(
            f"{base_url.rstrip('/')}/workflows/refresh-and-sync",
            json={"stop_prices": {}},
            headers={"Authorization": f"Bearer {workflow_api_token}"},
        )
        response.raise_for_status()

    print(f"Scheduled snapshot completed: snapshot_id={response.json()['snapshot_id']}")


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BACKEND_URL)
    args = parser.parse_args(argv)
    run_scheduled_snapshot(base_url=args.base_url, transport=transport)


if __name__ == "__main__":
    main()
