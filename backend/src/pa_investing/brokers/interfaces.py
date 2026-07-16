from abc import ABC, abstractmethod

from pa_investing.domain.models import (
    Account,
    BrokerReconciliation,
    Position,
    Transaction,
)


class BrokerConnector(ABC):
    @abstractmethod
    def list_accounts(self) -> list[Account]:
        raise NotImplementedError

    @abstractmethod
    def fetch_positions(self) -> list[Position]:
        raise NotImplementedError

    def fetch_transactions(self) -> list[Transaction]:
        return []

    def fetch_reconciliations(self) -> list[BrokerReconciliation]:
        return []
