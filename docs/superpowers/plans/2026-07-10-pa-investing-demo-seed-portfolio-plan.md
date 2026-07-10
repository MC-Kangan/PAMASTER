# PA Investing Demo Seed Portfolio Implementation Plan

**Goal:** Add the smallest repeatable demo data-loading flow for the first MVP so a realistic starter portfolio can be loaded into PostgreSQL, refreshed with live prices, and surfaced in Notion.

**Architecture:** This plan keeps PostgreSQL as the source of truth and uses a repo-managed CSV plus a small CLI seed command to populate one demo account. It reuses the existing CSV importer and repository upsert behavior instead of adding a new admin API or separate demo-only persistence path.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, Pydantic v2, pytest, existing repository layer, existing CSV importer, CLI execution via `python -m`.

## Global Constraints

- No order placement.
- No broker connectivity.
- No new API route for seeding.
- No multi-account orchestration in this slice.
- No exchange-aware security master yet.
- Keep the seed flow idempotent.
- Keep seed logic separate from price refresh and Notion sync.

---

## Scope Check

This plan implements the design documented in [2026-07-10-pa-investing-demo-seed-portfolio-design.md](/Users/chenkangan/Documents/PAMASTER/docs/superpowers/specs/2026-07-10-pa-investing-demo-seed-portfolio-design.md). It covers only:

- one demo portfolio CSV fixture;
- one CLI seed command;
- one seeding service or helper layer;
- focused tests for import, idempotent seeding, and rerun behavior;
- backend runbook updates for the demo flow.

It does not implement broker ingestion, multi-account setup, richer instrument metadata, or new app UI.

## Planned File Structure

```text
backend/
  README.md
  src/pa_investing/
    brokers/
      csv_importer.py
    db/
      repositories.py
      session.py
    scripts/
      seed_demo_portfolio.py
    seeds/
      demo_portfolio.py
  tests/
    fixtures/
      positions_demo_portfolio.csv
    integration/
      test_demo_portfolio_seed.py
    unit/
      test_csv_importer.py
```

## Task 1: Add Demo Portfolio Fixture Coverage

**Files:**
- Create: `backend/tests/fixtures/positions_demo_portfolio.csv`
- Modify: `backend/tests/unit/test_csv_importer.py`

**Interfaces:**
- Produces: a versioned demo portfolio CSV fixture for `pa-demo`
- Consumes: `CsvPositionImporter.import_positions(path: Path) -> list[Position]`

- [ ] **Step 1: Write failing importer test for the new fixture**

Add a focused test asserting the new fixture imports the agreed symbols and asset classes:

```python
def test_csv_position_importer_maps_demo_portfolio_fixture() -> None:
    importer = CsvPositionImporter()

    positions = importer.import_positions(
        Path("tests/fixtures/positions_demo_portfolio.csv")
    )

    assert [position.instrument.symbol for position in positions] == [
        "SPGI",
        "ASML",
        "SAP",
        "SGLN",
        "SMH",
    ]
```

- [ ] **Step 2: Run focused importer tests**

Run: `cd backend && ./.venv/bin/pytest tests/unit/test_csv_importer.py -v`

Expected: FAIL because the fixture does not exist yet.

- [ ] **Step 3: Add the demo fixture**

Create `positions_demo_portfolio.csv` with:

- one account id: `pa-demo`
- starter symbols: `SPGI`, `ASML`, `SAP`, `SGLN`, `SMH`
- asset classes:
  - `equity` for `SPGI`, `ASML`, `SAP`
  - `etf` for `SGLN`, `SMH`
- sensible placeholder prices and quantities

- [ ] **Step 4: Re-run focused importer tests**

Run: `cd backend && ./.venv/bin/pytest tests/unit/test_csv_importer.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fixtures/positions_demo_portfolio.csv backend/tests/unit/test_csv_importer.py
git commit -m "test: add demo portfolio CSV fixture"
```

## Task 2: Implement Demo Portfolio Seeding Service

**Files:**
- Create: `backend/src/pa_investing/seeds/demo_portfolio.py`
- Create: `backend/tests/integration/test_demo_portfolio_seed.py`

**Interfaces:**
- Produces: `seed_demo_portfolio(session: Session, csv_path: Path) -> SeedResult`
- Consumes: `CsvPositionImporter`
- Consumes: `AccountRepository`
- Consumes: `PositionRepository`

- [ ] **Step 1: Write failing integration tests for seeding**

Add tests covering:

```python
def test_seed_demo_portfolio_loads_account_and_positions() -> None:
    ...


def test_seed_demo_portfolio_is_idempotent_on_rerun() -> None:
    ...


def test_seed_demo_portfolio_overwrites_existing_position_values() -> None:
    ...
```

The tests should use an in-memory SQLite database and verify:

- `pa-demo` account exists;
- one position per symbol exists;
- rerunning does not duplicate rows;
- changed CSV values overwrite existing quantity or cost.

- [ ] **Step 2: Run focused seed integration tests**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_demo_portfolio_seed.py -v`

Expected: FAIL because the seeding module does not exist yet.

- [ ] **Step 3: Implement the seeding helper**

Create a small helper that:

- imports the CSV using `CsvPositionImporter`;
- upserts `Account(account_id="pa-demo", name="Demo Portfolio", source="seed")`;
- upserts each imported position;
- returns a small result object with counts, for example:

```python
class SeedResult(BaseModel):
    account_id: str
    positions_loaded: int
```

- [ ] **Step 4: Re-run focused seed integration tests**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_demo_portfolio_seed.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/seeds/demo_portfolio.py backend/tests/integration/test_demo_portfolio_seed.py
git commit -m "feat: add demo portfolio seeding service"
```

## Task 3: Add CLI Seed Command

**Files:**
- Create: `backend/src/pa_investing/scripts/seed_demo_portfolio.py`
- Modify: `backend/src/pa_investing/db/session.py` if a small helper is needed
- Test: extend `backend/tests/integration/test_demo_portfolio_seed.py` or add a focused CLI-oriented test if practical

**Interfaces:**
- Produces: `python -m pa_investing.scripts.seed_demo_portfolio`
- Consumes: `get_settings()`
- Consumes: `DatabaseSessionFactory`
- Consumes: `seed_demo_portfolio(session, csv_path)`

- [ ] **Step 1: Write a failing CLI-oriented test or entrypoint test**

Prefer a small test that exercises the command entrypoint function directly rather than shelling out:

```python
def test_seed_demo_portfolio_command_returns_summary(capsys: CaptureFixture[str]) -> None:
    ...
```

Assert that:

- the command completes without error;
- output includes `pa-demo`;
- output includes the number of positions loaded.

- [ ] **Step 2: Run focused CLI tests**

Run the smallest relevant test target, for example:

`cd backend && ./.venv/bin/pytest tests/integration/test_demo_portfolio_seed.py -v`

Expected: FAIL because the script entrypoint does not exist yet.

- [ ] **Step 3: Implement the CLI command**

Add a script that:

- resolves the repo fixture path;
- builds a DB session factory from settings;
- runs the seeding helper;
- commits the session;
- prints a short summary like:

```text
Seeded demo portfolio pa-demo with 5 positions
```

- [ ] **Step 4: Re-run focused CLI tests**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_demo_portfolio_seed.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/scripts/seed_demo_portfolio.py backend/src/pa_investing/db/session.py backend/tests/integration/test_demo_portfolio_seed.py
git commit -m "feat: add demo portfolio seed CLI"
```

## Task 4: Update Demo Runbook And Full Verification

**Files:**
- Modify: `backend/README.md`

**Interfaces:**
- Produces: documented MVP demo sequence from empty DB to seeded portfolio to refresh workflow

- [ ] **Step 1: Update the backend runbook**

Add the demo sequence:

```bash
alembic upgrade head
python -m pa_investing.scripts.seed_demo_portfolio
curl -X POST http://localhost:8000/workflows/refresh-and-sync \
  -H "Content-Type: application/json" \
  -d '{"stop_prices": {"SPGI": "470", "ASML": "900", "SAP": "240", "SGLN": "22", "SMH": "250"}}'
```

Document that:

- the seed command loads placeholder prices;
- the refresh workflow is expected to replace them with provider marks where supported;
- Notion output should be checked in `Signals` and `Daily Review`.

- [ ] **Step 2: Run full verification**

Run:

```bash
cd backend
./.venv/bin/pytest
./.venv/bin/ruff check .
git status --short
```

Expected:

- all tests pass;
- Ruff is clean;
- git status is clean after the final commit.

- [ ] **Step 3: Commit**

```bash
git add backend/README.md
git commit -m "docs: add demo seed runbook"
```

## Self-Review

Spec coverage:

- demo CSV fixture is covered by Task 1;
- idempotent seed behavior is covered by Tasks 2 and 3;
- one-account MVP scope is preserved throughout;
- runbook updates are covered by Task 4.

Placeholder scan:

- no `TODO` or `TBD` placeholders remain;
- starter symbols are explicitly listed.

Type consistency:

- the plan reuses existing `Position`, `Account`, and repository abstractions;
- the seed helper is kept separate from the refresh workflow;
- the CLI layer stays thin and orchestration-only.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-10-pa-investing-demo-seed-portfolio-plan.md`.

Recommended next step: implement Task 1 first with TDD, then continue task-by-task until the demo seed path is complete.
