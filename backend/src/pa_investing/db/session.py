from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pa_investing.core.config import Settings


class DatabaseSessionFactory:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_engine(settings.database_url)
        self.session_factory = sessionmaker(bind=self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session
