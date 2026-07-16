import argparse
import csv
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from pa_investing.core.config import Settings
from pa_investing.db.repositories import MarketDataMappingRepository
from pa_investing.db.session import DatabaseSessionFactory
from pa_investing.domain.models import MarketDataMapping

REQUIRED_COLUMNS = {
    "instrument_id",
    "provider",
    "provider_symbol",
    "expected_currency",
}


def import_market_data_mappings(
    path: Path,
    *,
    settings: Settings | None = None,
    session_factory: Callable[[], object] | None = None,
) -> int:
    resolved_settings = settings or Settings()
    resolved_session_factory = (
        session_factory or DatabaseSessionFactory(resolved_settings).session
    )
    mappings = _read_mappings(path)

    with resolved_session_factory() as session:
        repository = MarketDataMappingRepository(session)
        for mapping in mappings:
            repository.upsert(mapping)
        session.commit()

    return len(mappings)


def _read_mappings(path: Path) -> list[MarketDataMapping]:
    with path.open(newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                "mapping CSV is missing columns: " + ", ".join(sorted(missing))
            )

        mappings: list[MarketDataMapping] = []
        for row_number, row in enumerate(reader, start=2):
            try:
                mappings.append(
                    MarketDataMapping(
                        instrument_id=row["instrument_id"].strip(),
                        provider=row["provider"].strip(),
                        provider_symbol=row["provider_symbol"].strip(),
                        provider_exchange=(row.get("provider_exchange") or "").strip()
                        or None,
                        expected_currency=row["expected_currency"].strip(),
                        price_multiplier=Decimal(
                            (row.get("price_multiplier") or "1").strip()
                        ),
                        enabled=_parse_enabled(row.get("enabled")),
                    )
                )
            except (ArithmeticError, ValidationError, ValueError) as error:
                raise ValueError(
                    f"invalid market-data mapping on CSV row {row_number}: {error}"
                ) from error
    return mappings


def _parse_enabled(value: str | None) -> bool:
    normalized = (value or "true").strip().lower()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    raise ValueError("enabled must be true/false, yes/no, or 1/0")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import provider-specific market-data mappings from CSV."
    )
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    count = import_market_data_mappings(args.path)
    print(f"Imported {count} market-data mappings")


if __name__ == "__main__":
    main()
