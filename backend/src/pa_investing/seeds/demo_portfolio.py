from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session

from pa_investing.brokers.csv_importer import CsvPositionImporter
from pa_investing.db.repositories import AccountRepository, PositionRepository
from pa_investing.domain.models import Account

DEMO_ACCOUNT_ID = "pa-demo"
DEMO_ACCOUNT_NAME = "Demo Portfolio"
DEMO_ACCOUNT_SOURCE = "seed"


class SeedResult(BaseModel):
    account_id: str
    positions_loaded: int


def seed_demo_portfolio(session: Session, csv_path: Path) -> SeedResult:
    importer = CsvPositionImporter()
    positions = importer.import_positions(csv_path)

    AccountRepository(session).upsert(
        Account(
            account_id=DEMO_ACCOUNT_ID,
            name=DEMO_ACCOUNT_NAME,
            source=DEMO_ACCOUNT_SOURCE,
        )
    )

    position_repository = PositionRepository(session)
    for position in positions:
        position_repository.upsert(position)

    return SeedResult(
        account_id=DEMO_ACCOUNT_ID,
        positions_loaded=len(positions),
    )
