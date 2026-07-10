from decimal import Decimal
from pathlib import Path

from pa_investing.brokers.csv_importer import CsvPositionImporter
from pa_investing.domain.enums import AssetClass


def test_csv_position_importer_maps_rows_to_positions() -> None:
    importer = CsvPositionImporter()

    positions = importer.import_positions(Path("tests/fixtures/positions_sample.csv"))

    assert len(positions) == 3
    assert positions[0].account_id == "manual-pa"
    assert positions[0].instrument.symbol == "AAPL"
    assert positions[0].instrument.asset_class == AssetClass.EQUITY
    assert positions[0].quantity == Decimal("10")
    assert positions[0].latest_price == Decimal("175")


def test_csv_position_importer_rejects_missing_columns(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.csv"
    bad_file.write_text("symbol,quantity\nAAPL,10\n")
    importer = CsvPositionImporter()

    try:
        importer.import_positions(bad_file)
    except ValueError as exc:
        assert "missing required columns" in str(exc)
    else:
        raise AssertionError("CsvPositionImporter accepted a malformed file")


def test_csv_position_importer_maps_demo_portfolio_fixture() -> None:
    importer = CsvPositionImporter()

    positions = importer.import_positions(
        Path("tests/fixtures/positions_demo_portfolio.csv")
    )

    assert [position.account_id for position in positions] == ["pa-demo"] * 5
    assert [position.instrument.symbol for position in positions] == [
        "SPGI",
        "ASML",
        "SAP",
        "SGLN",
        "SMH",
    ]
    assert [position.instrument.asset_class for position in positions] == [
        AssetClass.EQUITY,
        AssetClass.EQUITY,
        AssetClass.EQUITY,
        AssetClass.ETF,
        AssetClass.ETF,
    ]
