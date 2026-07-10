from datetime import time
from decimal import Decimal
from typing import Protocol, TypeVar

T = TypeVar("T")


class SnapshotCapableWorkflow(Protocol[T]):
    def run(self, stop_prices: dict[str, Decimal]) -> T:
        ...


SCHEDULED_SNAPSHOT_TIMES = (
    time(hour=0, minute=0),
    time(hour=6, minute=0),
    time(hour=12, minute=0),
    time(hour=18, minute=0),
)


class SnapshotScheduleRunner:
    def __init__(self, workflow: SnapshotCapableWorkflow[T]) -> None:
        self.workflow = workflow

    def run_once(self, stop_prices: dict[str, Decimal] | None = None) -> T:
        return self.workflow.run(stop_prices=stop_prices or {})
