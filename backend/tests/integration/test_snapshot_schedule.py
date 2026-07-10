from datetime import time
from decimal import Decimal

from pa_investing.workflows.snapshot_schedule import (
    SCHEDULED_SNAPSHOT_TIMES,
    SnapshotScheduleRunner,
)


def test_snapshot_schedule_defines_four_fixed_run_times() -> None:
    assert (
        time(hour=0, minute=0),
        time(hour=6, minute=0),
        time(hour=12, minute=0),
        time(hour=18, minute=0),
    ) == SCHEDULED_SNAPSHOT_TIMES


def test_snapshot_schedule_triggers_snapshot_capable_workflow() -> None:
    observed_stop_prices: list[dict[str, Decimal]] = []

    class FakeWorkflow:
        def run(self, stop_prices: dict[str, Decimal]) -> str:
            observed_stop_prices.append(stop_prices)
            return "ok"

    runner = SnapshotScheduleRunner(workflow=FakeWorkflow())

    result = runner.run_once(stop_prices={"SPGI": Decimal("470")})

    assert result == "ok"
    assert observed_stop_prices == [{"SPGI": Decimal("470")}]
