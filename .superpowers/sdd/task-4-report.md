# Task 4 Report: CSV Position Importer

## What I implemented

- Added `pa_investing.brokers` as a new package.
- Added `BrokerConnector` in `backend/src/pa_investing/brokers/interfaces.py` with `list_accounts()` and `fetch_positions()`.
- Added `CsvPositionImporter` in `backend/src/pa_investing/brokers/csv_importer.py` to read CSV rows into `Position` objects.
- Added the fixture CSV at `backend/tests/fixtures/positions_sample.csv`.
- Added unit tests in `backend/tests/unit/test_csv_importer.py` for row mapping and missing-column validation.

## What I tested and test results

- Focused unit test: `./.venv/bin/pytest tests/unit/test_csv_importer.py -v`
  - Result: 2 passed
- Lint: `./.venv/bin/ruff check .`
  - Result: All checks passed

## TDD Evidence

### RED

Command:

```bash
cd backend
./.venv/bin/pytest tests/unit/test_csv_importer.py -v
```

Relevant failing output before implementation:

```text
E   ModuleNotFoundError: No module named 'pa_investing.brokers'
```

Why this was expected: the broker package and importer did not exist yet, so test collection could not import `CsvPositionImporter`.

### GREEN

Command:

```bash
cd backend
./.venv/bin/pytest tests/unit/test_csv_importer.py -v
```

Relevant passing output after implementation:

```text
tests/unit/test_csv_importer.py::test_csv_position_importer_maps_rows_to_positions PASSED
tests/unit/test_csv_importer.py::test_csv_position_importer_rejects_missing_columns PASSED
```

## Files changed

- `backend/src/pa_investing/brokers/__init__.py`
- `backend/src/pa_investing/brokers/interfaces.py`
- `backend/src/pa_investing/brokers/csv_importer.py`
- `backend/tests/fixtures/positions_sample.csv`
- `backend/tests/unit/test_csv_importer.py`
- `.superpowers/sdd/task-4-report.md`

## Self-review findings

- The importer stays inside Task 4 scope and does not add live broker connectivity or any later-task logic.
- CSV column validation is explicit and fails fast with a clear error message.
- The test fixture matches the brief exactly and exercises the intended `Position` mapping.

## Any issues or concerns

- The importer assumes the CSV values are already clean and correctly formatted beyond the required columns and decimal parsing.
- `latest_price` is treated as optional if blank, which is slightly more permissive than the sample fixture but keeps the importer tolerant of missing live values without expanding scope.
