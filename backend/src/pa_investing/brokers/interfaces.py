from abc import ABC, abstractmethod

from pa_investing.domain.models import Account, Position


class BrokerConnector(ABC):
    @abstractmethod
    def list_accounts(self) -> list[Account]:
        raise NotImplementedError

    @abstractmethod
    def fetch_positions(self) -> list[Position]:
        raise NotImplementedError
