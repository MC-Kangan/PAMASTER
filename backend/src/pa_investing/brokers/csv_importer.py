import csv
from decimal import Decimal
from pathlib import Path

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, Position


class CsvPositionImporter:
    required_columns = {
        "account_id",
        "symbol",
        "name",
        "asset_class",
        "currency",
        "quantity",
        "average_cost",
        "latest_price",
    }

    def import_positions(self, path: Path) -> list[Position]:
        with path.open(newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            fieldnames = set(reader.fieldnames or [])
            missing = self.required_columns - fieldnames
            if missing:
                missing_list = ", ".join(sorted(missing))
                raise ValueError(f"missing required columns: {missing_list}")

            positions: list[Position] = []
            for row in reader:
                instrument = Instrument(
                    symbol=row["symbol"],
                    name=row["name"],
                    asset_class=AssetClass(row["asset_class"]),
                    currency=row["currency"],
                )
                positions.append(
                    Position(
                        account_id=row["account_id"],
                        instrument=instrument,
                        quantity=Decimal(row["quantity"]),
                        average_cost=Decimal(row["average_cost"]),
                        latest_price=(
                            Decimal(row["latest_price"]) if row["latest_price"] else None
                        ),
                    )
                )
            return positions
