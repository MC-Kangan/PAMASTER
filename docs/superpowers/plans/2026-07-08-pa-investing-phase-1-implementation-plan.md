# PA Investing Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 PA investing foundation: Notion command-center schema, Python backend skeleton, PostgreSQL persistence, CSV/manual portfolio import, delayed price ingestion, basic portfolio metrics, rule-based signals, deterministic sizing, minimal analytics links, and mockable LLM summarization.

**Architecture:** The backend is the long-term system core. Notion is the first UI adapter, PostgreSQL stores structured truth, and all analytics/agent outputs are generated through Python modules with explicit interfaces. The first implementation uses fake Notion and fake LLM clients by default so the system is testable before live credentials are added.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL, Pydantic v2, pytest, httpx, pandas-free CSV parsing via standard library, Docker Compose.

## Global Constraints

- No order placement.
- No day-trading or high-frequency workflows.
- No storing secrets in Notion.
- No treating Notion as the only source of portfolio truth.
- No full custom app in phase 1.
- No formal plugin system in phase 1; use explicit Python interfaces first.
- No letting an agent framework directly control broker credentials, shell access, or database admin access.
- Read-only broker access only.
- Deterministic sizing and risk tools own numeric recommendations.
- Agent outputs must be audited.
- Notion is a UI adapter.
- PostgreSQL is the source of truth.
- Future app builders must call backend APIs instead of owning core logic.

---

## Scope Check

This plan covers only Phase 1 from the architecture spec, plus a thin Agent API skeleton required by the revised first vertical slice. It does not implement live Coinbase/IBKR connectors, Obsidian indexing, specialist agents, OpenClaw integration, or an all-in-one custom frontend. Those remain future phases.

## Planned File Structure

Create the following structure:

```text
backend/
  alembic.ini
  pyproject.toml
  README.md
  Dockerfile
  docker-compose.yml
  .env.example
  alembic/
    env.py
    versions/
  src/pa_investing/
    __init__.py
    main.py
    core/
      __init__.py
      config.py
    db/
      __init__.py
      base.py
      models.py
      session.py
      repositories.py
    domain/
      __init__.py
      models.py
      enums.py
    brokers/
      __init__.py
      csv_importer.py
      interfaces.py
    market_data/
      __init__.py
      interfaces.py
      manual_prices.py
    analytics/
      __init__.py
      metrics.py
      snapshots.py
    sizing/
      __init__.py
      models.py
    signals/
      __init__.py
      rules.py
      service.py
    notion/
      __init__.py
      schemas.py
      client.py
      sync.py
    llm/
      __init__.py
      interfaces.py
      mock.py
      summarizer.py
    workflows/
      __init__.py
      daily_review.py
      agent_api.py
    audit/
      __init__.py
      events.py
    api/
      __init__.py
      routes.py
    analytics_app/
      __init__.py
      pages.py
  tests/
    conftest.py
    fixtures/
      positions_sample.csv
      prices_sample.csv
    unit/
      test_config.py
      test_domain_models.py
      test_csv_importer.py
      test_manual_prices.py
      test_metrics.py
      test_sizing.py
      test_signals.py
      test_notion_schemas.py
      test_llm_summarizer.py
      test_agent_api.py
    integration/
      test_repositories.py
      test_daily_review_workflow.py
      test_api_routes.py
```

Responsibilities:

- `domain/`: pure business models and enums with no database or API dependencies.
- `db/`: SQLAlchemy models, sessions, and repository methods.
- `brokers/`: import account/position data from CSV first; live connectors use `BrokerConnector` later.
- `market_data/`: price-provider interface and manual/free delayed price ingestion.
- `analytics/`: NAV, PnL, exposures, and snapshot calculations.
- `signals/`: deterministic signal rules and orchestration.
- `sizing/`: deterministic sizing models.
- `notion/`: database schema definitions, fake/live client interface, sync mapping.
- `llm/`: provider interface and mock summarization implementation.
- `workflows/`: daily review and thin Agent API skeleton.
- `api/`: FastAPI routes.
- `analytics_app/`: minimal linked HTML pages for portfolio and signal detail.

---

### Task 1: Backend Project Skeleton And Tooling

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/README.md`
- Create: `backend/.env.example`
- Create: `backend/src/pa_investing/__init__.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/unit/test_config.py`

**Interfaces:**
- Produces: installable package `pa_investing`
- Produces: pytest configuration and import path used by all later tasks

- [ ] **Step 1: Write the failing config import test**

Create `backend/tests/unit/test_config.py`:

```python
from pa_investing.core.config import Settings


def test_settings_defaults_are_safe_for_local_tests() -> None:
    settings = Settings()

    assert settings.environment == "test"
    assert settings.notion_enabled is False
    assert settings.llm_provider == "mock"
    assert settings.database_url.startswith("sqlite+pysqlite://")
```

- [ ] **Step 2: Add packaging and test configuration**

Create `backend/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pa-investing"
version = "0.1.0"
description = "Personal-account investing workflow backend"
requires-python = ">=3.12"
dependencies = [
  "alembic>=1.13",
  "fastapi>=0.115",
  "httpx>=0.27",
  "pydantic>=2.8",
  "pydantic-settings>=2.4",
  "psycopg[binary]>=3.2",
  "sqlalchemy>=2.0",
  "uvicorn[standard]>=0.30",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.23",
  "ruff>=0.6",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

Create `backend/tests/conftest.py`:

```python
import os


os.environ.setdefault("PA_ENVIRONMENT", "test")
os.environ.setdefault("PA_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("PA_LLM_PROVIDER", "mock")
os.environ.setdefault("PA_NOTION_ENABLED", "false")
```

Create `backend/src/pa_investing/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

Create `backend/.env.example`:

```dotenv
PA_ENVIRONMENT=local
PA_DATABASE_URL=postgresql+psycopg://pa_investing:pa_investing@postgres:5432/pa_investing
PA_NOTION_ENABLED=false
PA_NOTION_API_KEY=
PA_LLM_PROVIDER=mock
PA_OPENAI_API_KEY=
PA_DEFAULT_BASE_CURRENCY=USD
```

Create `backend/README.md`:

````markdown
# PA Investing Backend

Phase 1 backend for the PA investing workflow. The system uses Notion as the first UI adapter, PostgreSQL as the source of truth, and Python modules for analytics, signal generation, sizing, and agent workflows.

## Local Commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```
````

- [ ] **Step 3: Run test to verify it fails before settings exist**

Run:

```bash
cd backend
pytest tests/unit/test_config.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'pa_investing.core'`.

- [ ] **Step 4: Implement minimal settings module**

Create `backend/src/pa_investing/core/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/core/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    environment: str = "test"
    database_url: str = "sqlite+pysqlite:///:memory:"
    notion_enabled: bool = False
    notion_api_key: str = ""
    llm_provider: str = "mock"
    openai_api_key: str = ""
    default_base_currency: str = "USD"
```

- [ ] **Step 5: Run test and lint**

Run:

```bash
cd backend
pytest tests/unit/test_config.py -v
ruff check .
```

Expected: one passing test and no lint errors.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/README.md backend/.env.example backend/src/pa_investing/__init__.py backend/src/pa_investing/core/__init__.py backend/src/pa_investing/core/config.py backend/tests/conftest.py backend/tests/unit/test_config.py
git commit -m "feat: scaffold PA investing backend"
```

---

### Task 2: Domain Models And Enums

**Files:**
- Create: `backend/src/pa_investing/domain/__init__.py`
- Create: `backend/src/pa_investing/domain/enums.py`
- Create: `backend/src/pa_investing/domain/models.py`
- Test: `backend/tests/unit/test_domain_models.py`

**Interfaces:**
- Produces: `AssetClass`, `SignalType`, `SignalSeverity`, `SignalStatus`
- Produces: `Instrument`, `Account`, `Position`, `PricePoint`, `PortfolioSnapshot`, `Signal`
- Consumed by: database, CSV importer, market data, analytics, sizing, signals, Notion sync

- [ ] **Step 1: Write failing domain tests**

Create `backend/tests/unit/test_domain_models.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

from pa_investing.domain.enums import AssetClass, SignalSeverity, SignalStatus, SignalType
from pa_investing.domain.models import Instrument, Position, PricePoint, Signal


def test_position_market_value_uses_latest_price() -> None:
    instrument = Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY, currency="USD")
    position = Position(
        account_id="acct-1",
        instrument=instrument,
        quantity=Decimal("10"),
        average_cost=Decimal("150"),
        latest_price=Decimal("175"),
    )

    assert position.market_value == Decimal("1750")
    assert position.unrealized_pnl == Decimal("250")


def test_signal_contains_deterministic_recommendation_fields() -> None:
    signal = Signal(
        signal_id="sig-1",
        symbol="AAPL",
        signal_type=SignalType.STOP_REFERENCE,
        severity=SignalSeverity.HIGH,
        status=SignalStatus.OPEN,
        message="Reference stop was breached.",
        deterministic_recommendation="Reduce 2 shares",
        audit_id="audit-1",
        created_at=datetime(2026, 7, 8, tzinfo=UTC),
    )

    assert signal.symbol == "AAPL"
    assert signal.deterministic_recommendation == "Reduce 2 shares"


def test_price_point_rejects_non_positive_price() -> None:
    instrument = Instrument(symbol="BTC-USD", name="Bitcoin", asset_class=AssetClass.CRYPTO, currency="USD")

    try:
        PricePoint(instrument=instrument, price=Decimal("0"), observed_at=datetime(2026, 7, 8, tzinfo=UTC))
    except ValueError as exc:
        assert "price must be positive" in str(exc)
    else:
        raise AssertionError("PricePoint accepted a non-positive price")
```

- [ ] **Step 2: Run tests to verify missing domain fails**

Run:

```bash
cd backend
pytest tests/unit/test_domain_models.py -v
```

Expected: fail with missing `pa_investing.domain`.

- [ ] **Step 3: Implement enums and Pydantic domain models**

Create `backend/src/pa_investing/domain/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/domain/enums.py`:

```python
from enum import StrEnum


class AssetClass(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    CRYPTO = "crypto"
    CASH = "cash"


class SignalType(StrEnum):
    ENTRY_LEVEL = "entry_level"
    STOP_REFERENCE = "stop_reference"
    RISK_LIMIT = "risk_limit"
    REVIEW_REQUIRED = "review_required"


class SignalSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalStatus(StrEnum):
    OPEN = "open"
    REVIEW_REQUESTED = "review_requested"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
```

Create `backend/src/pa_investing/domain/models.py`:

```python
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pa_investing.domain.enums import AssetClass, SignalSeverity, SignalStatus, SignalType


class Instrument(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    asset_class: AssetClass
    currency: str = "USD"

    @field_validator("symbol", "currency")
    @classmethod
    def uppercase_identifier(cls, value: str) -> str:
        return value.upper()


class Account(BaseModel):
    account_id: str
    name: str
    source: str
    base_currency: str = "USD"


class Position(BaseModel):
    account_id: str
    instrument: Instrument
    quantity: Decimal
    average_cost: Decimal
    latest_price: Decimal | None = None

    @property
    def market_value(self) -> Decimal:
        if self.latest_price is None:
            return Decimal("0")
        return self.quantity * self.latest_price

    @property
    def cost_basis(self) -> Decimal:
        return self.quantity * self.average_cost

    @property
    def unrealized_pnl(self) -> Decimal:
        return self.market_value - self.cost_basis


class PricePoint(BaseModel):
    instrument: Instrument
    price: Decimal
    observed_at: datetime
    provider: str = "manual"

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("price must be positive")
        return value


class PortfolioSnapshot(BaseModel):
    snapshot_id: str
    observed_at: datetime
    base_currency: str
    nav: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    unrealized_pnl: Decimal


class Signal(BaseModel):
    signal_id: str
    symbol: str
    signal_type: SignalType
    severity: SignalSeverity
    status: SignalStatus
    message: str
    deterministic_recommendation: str
    audit_id: str
    created_at: datetime
    analytics_path: str | None = None
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_domain_models.py -v
ruff check .
```

Expected: all tests pass and no lint errors.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/domain backend/tests/unit/test_domain_models.py
git commit -m "feat: add investing domain models"
```

---

### Task 3: Database Models, Session, And Repositories

**Files:**
- Create: `backend/src/pa_investing/db/__init__.py`
- Create: `backend/src/pa_investing/db/base.py`
- Create: `backend/src/pa_investing/db/models.py`
- Create: `backend/src/pa_investing/db/session.py`
- Create: `backend/src/pa_investing/db/repositories.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial_schema.py`
- Test: `backend/tests/integration/test_repositories.py`

**Interfaces:**
- Consumes: domain enums and settings
- Produces: `DatabaseSessionFactory`, `AccountRepository`, `PositionRepository`, `PriceRepository`, `SignalRepository`
- Consumed by: workflows, API routes, daily review, Notion sync

- [ ] **Step 1: Write failing repository integration test**

Create `backend/tests/integration/test_repositories.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pa_investing.db.base import Base
from pa_investing.db.repositories import AccountRepository, PositionRepository, PriceRepository
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Account, Instrument, Position, PricePoint


def test_repositories_round_trip_account_position_and_price() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        account_repo = AccountRepository(session)
        position_repo = PositionRepository(session)
        price_repo = PriceRepository(session)

        account_repo.upsert(Account(account_id="acct-1", name="Manual Account", source="csv"))
        instrument = Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY)
        position_repo.upsert(
            Position(
                account_id="acct-1",
                instrument=instrument,
                quantity=Decimal("10"),
                average_cost=Decimal("150"),
                latest_price=Decimal("175"),
            )
        )
        price_repo.upsert(
            PricePoint(
                instrument=instrument,
                price=Decimal("175"),
                observed_at=datetime(2026, 7, 8, tzinfo=UTC),
                provider="manual",
            )
        )
        session.commit()

        positions = position_repo.list_open_positions()
        prices = price_repo.latest_prices()

    assert len(positions) == 1
    assert positions[0].instrument.symbol == "AAPL"
    assert prices["AAPL"].price == Decimal("175.000000")
```

- [ ] **Step 2: Run test to verify database layer is missing**

Run:

```bash
cd backend
pytest tests/integration/test_repositories.py -v
```

Expected: fail with missing `pa_investing.db`.

- [ ] **Step 3: Implement SQLAlchemy base and models**

Create `backend/src/pa_investing/db/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/db/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

Create `backend/src/pa_investing/db/models.py`:

```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pa_investing.db.base import Base


class AccountRecord(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")


class InstrumentRecord(Base):
    __tablename__ = "instruments"

    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")


class PositionRecord(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_position_account_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    latest_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)


class PriceRecord(Base):
    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("symbol", "observed_at", "provider", name="uq_price_symbol_time_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)


class SignalRecord(Base):
    __tablename__ = "signals"

    signal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(String(1024), nullable=False)
    deterministic_recommendation: Mapped[str] = mapped_column(String(1024), nullable=False)
    audit_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    analytics_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
```

- [ ] **Step 4: Implement repositories**

Create `backend/src/pa_investing/db/repositories.py`:

```python
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from pa_investing.db.models import AccountRecord, InstrumentRecord, PositionRecord, PriceRecord, SignalRecord
from pa_investing.domain.enums import AssetClass, SignalSeverity, SignalStatus, SignalType
from pa_investing.domain.models import Account, Instrument, Position, PricePoint, Signal


def _instrument_from_record(record: InstrumentRecord) -> Instrument:
    return Instrument(
        symbol=record.symbol,
        name=record.name,
        asset_class=AssetClass(record.asset_class),
        currency=record.currency,
    )


class AccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, account: Account) -> None:
        record = self.session.get(AccountRecord, account.account_id)
        if record is None:
            record = AccountRecord(account_id=account.account_id, name=account.name, source=account.source)
            self.session.add(record)
        record.name = account.name
        record.source = account.source
        record.base_currency = account.base_currency


class PositionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, position: Position) -> None:
        self._upsert_instrument(position.instrument)
        stmt = select(PositionRecord).where(
            PositionRecord.account_id == position.account_id,
            PositionRecord.symbol == position.instrument.symbol,
        )
        record = self.session.scalar(stmt)
        if record is None:
            record = PositionRecord(account_id=position.account_id, symbol=position.instrument.symbol)
            self.session.add(record)
        record.quantity = position.quantity
        record.average_cost = position.average_cost
        record.latest_price = position.latest_price

    def list_open_positions(self) -> list[Position]:
        stmt = select(PositionRecord, InstrumentRecord).join(
            InstrumentRecord, PositionRecord.symbol == InstrumentRecord.symbol
        )
        positions: list[Position] = []
        for position_record, instrument_record in self.session.execute(stmt).all():
            positions.append(
                Position(
                    account_id=position_record.account_id,
                    instrument=_instrument_from_record(instrument_record),
                    quantity=position_record.quantity,
                    average_cost=position_record.average_cost,
                    latest_price=position_record.latest_price,
                )
            )
        return positions

    def _upsert_instrument(self, instrument: Instrument) -> None:
        record = self.session.get(InstrumentRecord, instrument.symbol)
        if record is None:
            record = InstrumentRecord(symbol=instrument.symbol, name=instrument.name)
            self.session.add(record)
        record.name = instrument.name
        record.asset_class = instrument.asset_class.value
        record.currency = instrument.currency


class PriceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, price_point: PricePoint) -> None:
        instrument = price_point.instrument
        instrument_record = self.session.get(InstrumentRecord, instrument.symbol)
        if instrument_record is None:
            instrument_record = InstrumentRecord(
                symbol=instrument.symbol,
                name=instrument.name,
                asset_class=instrument.asset_class.value,
                currency=instrument.currency,
            )
            self.session.add(instrument_record)

        stmt = select(PriceRecord).where(
            PriceRecord.symbol == instrument.symbol,
            PriceRecord.observed_at == price_point.observed_at,
            PriceRecord.provider == price_point.provider,
        )
        record = self.session.scalar(stmt)
        if record is None:
            record = PriceRecord(
                symbol=instrument.symbol,
                observed_at=price_point.observed_at,
                provider=price_point.provider,
            )
            self.session.add(record)
        record.price = price_point.price

    def latest_prices(self) -> Mapping[str, PricePoint]:
        rows = self.session.execute(
            select(PriceRecord, InstrumentRecord).join(
                InstrumentRecord,
                PriceRecord.symbol == InstrumentRecord.symbol,
            )
        ).all()
        latest: dict[str, tuple[PriceRecord, InstrumentRecord]] = {}
        for price_record, instrument_record in rows:
            current = latest.get(price_record.symbol)
            if current is None or price_record.observed_at > current[0].observed_at:
                latest[price_record.symbol] = (price_record, instrument_record)
        return {
            symbol: PricePoint(
                instrument=_instrument_from_record(instrument_record),
                price=price_record.price,
                observed_at=price_record.observed_at,
                provider=price_record.provider,
            )
            for symbol, (price_record, instrument_record) in latest.items()
        }


class SignalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, signal: Signal) -> None:
        record = self.session.get(SignalRecord, signal.signal_id)
        if record is None:
            record = SignalRecord(signal_id=signal.signal_id)
            self.session.add(record)
        record.symbol = signal.symbol
        record.signal_type = signal.signal_type.value
        record.severity = signal.severity.value
        record.status = signal.status.value
        record.message = signal.message
        record.deterministic_recommendation = signal.deterministic_recommendation
        record.audit_id = signal.audit_id
        record.created_at = signal.created_at
        record.analytics_path = signal.analytics_path

    def list_open(self) -> list[Signal]:
        rows = self.session.scalars(select(SignalRecord).where(SignalRecord.status == SignalStatus.OPEN.value)).all()
        return [
            Signal(
                signal_id=row.signal_id,
                symbol=row.symbol,
                signal_type=SignalType(row.signal_type),
                severity=SignalSeverity(row.severity),
                status=SignalStatus(row.status),
                message=row.message,
                deterministic_recommendation=row.deterministic_recommendation,
                audit_id=row.audit_id,
                created_at=row.created_at,
                analytics_path=row.analytics_path,
            )
            for row in rows
        ]
```

- [ ] **Step 5: Add session and Alembic files**

Create `backend/src/pa_investing/db/session.py`:

```python
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
```

Create `backend/alembic.ini`:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = sqlite+pysqlite:///:memory:

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

Create `backend/alembic/env.py`:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from pa_investing.core.config import Settings
from pa_investing.db.base import Base
from pa_investing.db import models  # noqa: F401

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata

settings = Settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Create `backend/alembic/versions/0001_initial_schema.py`:

```python
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
    )
    op.create_table(
        "instruments",
        sa.Column("symbol", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.String(length=64),
            sa.ForeignKey("accounts.account_id"),
            nullable=False,
        ),
        sa.Column(
            "symbol",
            sa.String(length=64),
            sa.ForeignKey("instruments.symbol"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("average_cost", sa.Numeric(24, 8), nullable=False),
        sa.Column("latest_price", sa.Numeric(24, 8), nullable=True),
        sa.UniqueConstraint("account_id", "symbol", name="uq_position_account_symbol"),
    )
    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "symbol",
            sa.String(length=64),
            sa.ForeignKey("instruments.symbol"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(24, 8), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.UniqueConstraint(
            "symbol",
            "observed_at",
            "provider",
            name="uq_price_symbol_time_provider",
        ),
    )
    op.create_table(
        "signals",
        sa.Column("signal_id", sa.String(length=64), primary_key=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
        sa.Column("deterministic_recommendation", sa.String(length=1024), nullable=False),
        sa.Column("audit_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analytics_path", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("signals")
    op.drop_table("prices")
    op.drop_table("positions")
    op.drop_table("instruments")
    op.drop_table("accounts")
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd backend
pytest tests/integration/test_repositories.py -v
ruff check .
```

Expected: repository integration test passes and no lint errors.

- [ ] **Step 7: Commit**

```bash
git add backend/src/pa_investing/db backend/alembic.ini backend/alembic backend/tests/integration/test_repositories.py
git commit -m "feat: add database schema and repositories"
```

---

### Task 4: CSV Position Importer

**Files:**
- Create: `backend/src/pa_investing/brokers/__init__.py`
- Create: `backend/src/pa_investing/brokers/interfaces.py`
- Create: `backend/src/pa_investing/brokers/csv_importer.py`
- Create: `backend/tests/fixtures/positions_sample.csv`
- Test: `backend/tests/unit/test_csv_importer.py`

**Interfaces:**
- Produces: `BrokerConnector.fetch_positions() -> list[Position]`
- Produces: `CsvPositionImporter.import_positions(path: Path) -> list[Position]`
- Consumed by: daily review workflow and repository loading

- [ ] **Step 1: Create sample CSV fixture**

Create `backend/tests/fixtures/positions_sample.csv`:

```csv
account_id,symbol,name,asset_class,currency,quantity,average_cost,latest_price
manual-pa,AAPL,Apple Inc.,equity,USD,10,150,175
manual-pa,SPY,SPDR S&P 500 ETF,etf,USD,5,500,510
manual-pa,BTC-USD,Bitcoin,crypto,USD,0.25,60000,62000
```

- [ ] **Step 2: Write failing importer tests**

Create `backend/tests/unit/test_csv_importer.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify importer missing**

Run:

```bash
cd backend
pytest tests/unit/test_csv_importer.py -v
```

Expected: fail with missing `pa_investing.brokers`.

- [ ] **Step 4: Implement importer and interface**

Create `backend/src/pa_investing/brokers/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/brokers/interfaces.py`:

```python
from abc import ABC, abstractmethod

from pa_investing.domain.models import Account, Position


class BrokerConnector(ABC):
    @abstractmethod
    def list_accounts(self) -> list[Account]:
        raise NotImplementedError

    @abstractmethod
    def fetch_positions(self) -> list[Position]:
        raise NotImplementedError
```

Create `backend/src/pa_investing/brokers/csv_importer.py`:

```python
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
                        latest_price=Decimal(row["latest_price"]) if row["latest_price"] else None,
                    )
                )
            return positions
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_csv_importer.py -v
ruff check .
```

Expected: importer tests pass and no lint errors.

- [ ] **Step 6: Commit**

```bash
git add backend/src/pa_investing/brokers backend/tests/fixtures/positions_sample.csv backend/tests/unit/test_csv_importer.py
git commit -m "feat: add CSV position importer"
```

---

### Task 5: Manual Price Provider

**Files:**
- Create: `backend/src/pa_investing/market_data/__init__.py`
- Create: `backend/src/pa_investing/market_data/interfaces.py`
- Create: `backend/src/pa_investing/market_data/manual_prices.py`
- Create: `backend/tests/fixtures/prices_sample.csv`
- Test: `backend/tests/unit/test_manual_prices.py`

**Interfaces:**
- Produces: `MarketDataProvider.get_latest_prices(symbols: set[str]) -> dict[str, PricePoint]`
- Produces: `ManualPriceProvider.from_csv(path: Path) -> ManualPriceProvider`
- Consumed by: portfolio snapshots and signal rules

- [ ] **Step 1: Create price fixture**

Create `backend/tests/fixtures/prices_sample.csv`:

```csv
symbol,name,asset_class,currency,price,observed_at
AAPL,Apple Inc.,equity,USD,175,2026-07-08T16:00:00+00:00
SPY,SPDR S&P 500 ETF,etf,USD,510,2026-07-08T16:00:00+00:00
BTC-USD,Bitcoin,crypto,USD,62000,2026-07-08T16:00:00+00:00
```

- [ ] **Step 2: Write failing price provider tests**

Create `backend/tests/unit/test_manual_prices.py`:

```python
from decimal import Decimal
from pathlib import Path

from pa_investing.market_data.manual_prices import ManualPriceProvider


def test_manual_price_provider_returns_requested_latest_prices() -> None:
    provider = ManualPriceProvider.from_csv(Path("tests/fixtures/prices_sample.csv"))

    prices = provider.get_latest_prices({"AAPL", "BTC-USD"})

    assert set(prices) == {"AAPL", "BTC-USD"}
    assert prices["AAPL"].price == Decimal("175")
    assert prices["BTC-USD"].price == Decimal("62000")


def test_manual_price_provider_reports_missing_symbols() -> None:
    provider = ManualPriceProvider.from_csv(Path("tests/fixtures/prices_sample.csv"))

    try:
        provider.get_latest_prices({"MSFT"})
    except KeyError as exc:
        assert "missing prices for symbols: MSFT" in str(exc)
    else:
        raise AssertionError("ManualPriceProvider accepted a missing symbol")
```

- [ ] **Step 3: Run tests to verify provider missing**

Run:

```bash
cd backend
pytest tests/unit/test_manual_prices.py -v
```

Expected: fail with missing `pa_investing.market_data`.

- [ ] **Step 4: Implement interface and CSV provider**

Create `backend/src/pa_investing/market_data/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/market_data/interfaces.py`:

```python
from abc import ABC, abstractmethod

from pa_investing.domain.models import PricePoint


class MarketDataProvider(ABC):
    @abstractmethod
    def get_latest_prices(self, symbols: set[str]) -> dict[str, PricePoint]:
        raise NotImplementedError
```

Create `backend/src/pa_investing/market_data/manual_prices.py`:

```python
import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, PricePoint
from pa_investing.market_data.interfaces import MarketDataProvider


class ManualPriceProvider(MarketDataProvider):
    def __init__(self, prices: dict[str, PricePoint]) -> None:
        self.prices = prices

    @classmethod
    def from_csv(cls, path: Path) -> "ManualPriceProvider":
        prices: dict[str, PricePoint] = {}
        with path.open(newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                instrument = Instrument(
                    symbol=row["symbol"],
                    name=row["name"],
                    asset_class=AssetClass(row["asset_class"]),
                    currency=row["currency"],
                )
                prices[instrument.symbol] = PricePoint(
                    instrument=instrument,
                    price=Decimal(row["price"]),
                    observed_at=datetime.fromisoformat(row["observed_at"]),
                    provider="manual",
                )
        return cls(prices)

    def get_latest_prices(self, symbols: set[str]) -> dict[str, PricePoint]:
        normalized = {symbol.upper() for symbol in symbols}
        missing = sorted(symbol for symbol in normalized if symbol not in self.prices)
        if missing:
            raise KeyError(f"missing prices for symbols: {', '.join(missing)}")
        return {symbol: self.prices[symbol] for symbol in normalized}
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_manual_prices.py -v
ruff check .
```

Expected: price provider tests pass and no lint errors.

- [ ] **Step 6: Commit**

```bash
git add backend/src/pa_investing/market_data backend/tests/fixtures/prices_sample.csv backend/tests/unit/test_manual_prices.py
git commit -m "feat: add manual price provider"
```

---

### Task 6: Portfolio Metrics And Snapshot Calculation

**Files:**
- Create: `backend/src/pa_investing/analytics/__init__.py`
- Create: `backend/src/pa_investing/analytics/metrics.py`
- Create: `backend/src/pa_investing/analytics/snapshots.py`
- Test: `backend/tests/unit/test_metrics.py`

**Interfaces:**
- Produces: `calculate_nav(positions: list[Position]) -> Decimal`
- Produces: `calculate_exposure_by_asset_class(positions: list[Position]) -> dict[AssetClass, Decimal]`
- Produces: `build_portfolio_snapshot(snapshot_id: str, positions: list[Position], observed_at: datetime, base_currency: str) -> PortfolioSnapshot`
- Consumed by: daily review workflow, Notion sync, signal rules

- [ ] **Step 1: Write failing metrics tests**

Create `backend/tests/unit/test_metrics.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

from pa_investing.analytics.metrics import calculate_exposure_by_asset_class, calculate_nav
from pa_investing.analytics.snapshots import build_portfolio_snapshot
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, Position


def _position(symbol: str, asset_class: AssetClass, quantity: str, cost: str, price: str) -> Position:
    return Position(
        account_id="manual-pa",
        instrument=Instrument(symbol=symbol, name=symbol, asset_class=asset_class),
        quantity=Decimal(quantity),
        average_cost=Decimal(cost),
        latest_price=Decimal(price),
    )


def test_calculate_nav_and_exposure() -> None:
    positions = [
        _position("AAPL", AssetClass.EQUITY, "10", "150", "175"),
        _position("SPY", AssetClass.ETF, "5", "500", "510"),
    ]

    assert calculate_nav(positions) == Decimal("4300")
    assert calculate_exposure_by_asset_class(positions) == {
        AssetClass.EQUITY: Decimal("1750"),
        AssetClass.ETF: Decimal("2550"),
    }


def test_build_portfolio_snapshot() -> None:
    positions = [_position("AAPL", AssetClass.EQUITY, "10", "150", "175")]

    snapshot = build_portfolio_snapshot(
        snapshot_id="snap-1",
        positions=positions,
        observed_at=datetime(2026, 7, 8, tzinfo=UTC),
        base_currency="USD",
    )

    assert snapshot.nav == Decimal("1750")
    assert snapshot.unrealized_pnl == Decimal("250")
    assert snapshot.gross_exposure == Decimal("1750")
```

- [ ] **Step 2: Run tests to verify analytics missing**

Run:

```bash
cd backend
pytest tests/unit/test_metrics.py -v
```

Expected: fail with missing `pa_investing.analytics`.

- [ ] **Step 3: Implement metrics and snapshot builder**

Create `backend/src/pa_investing/analytics/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/analytics/metrics.py`:

```python
from collections import defaultdict
from decimal import Decimal

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Position


def calculate_nav(positions: list[Position]) -> Decimal:
    return sum((position.market_value for position in positions), Decimal("0"))


def calculate_unrealized_pnl(positions: list[Position]) -> Decimal:
    return sum((position.unrealized_pnl for position in positions), Decimal("0"))


def calculate_exposure_by_asset_class(positions: list[Position]) -> dict[AssetClass, Decimal]:
    exposure: defaultdict[AssetClass, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in positions:
        exposure[position.instrument.asset_class] += position.market_value
    return dict(exposure)
```

Create `backend/src/pa_investing/analytics/snapshots.py`:

```python
from datetime import datetime

from pa_investing.analytics.metrics import calculate_nav, calculate_unrealized_pnl
from pa_investing.domain.models import PortfolioSnapshot, Position


def build_portfolio_snapshot(
    snapshot_id: str,
    positions: list[Position],
    observed_at: datetime,
    base_currency: str,
) -> PortfolioSnapshot:
    nav = calculate_nav(positions)
    unrealized_pnl = calculate_unrealized_pnl(positions)
    return PortfolioSnapshot(
        snapshot_id=snapshot_id,
        observed_at=observed_at,
        base_currency=base_currency,
        nav=nav,
        gross_exposure=nav,
        net_exposure=nav,
        unrealized_pnl=unrealized_pnl,
    )
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_metrics.py -v
ruff check .
```

Expected: metrics tests pass and no lint errors.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/analytics backend/tests/unit/test_metrics.py
git commit -m "feat: add portfolio metrics"
```

---

### Task 7: Deterministic Sizing And Signal Rules

**Files:**
- Create: `backend/src/pa_investing/sizing/__init__.py`
- Create: `backend/src/pa_investing/sizing/models.py`
- Create: `backend/src/pa_investing/signals/__init__.py`
- Create: `backend/src/pa_investing/signals/rules.py`
- Create: `backend/src/pa_investing/signals/service.py`
- Test: `backend/tests/unit/test_sizing.py`
- Test: `backend/tests/unit/test_signals.py`

**Interfaces:**
- Produces: `MaxNavWeightSizingModel.recommend_reduction(position: Position, portfolio_nav: Decimal) -> SizingRecommendation`
- Produces: `StopReferenceRule.evaluate(position: Position, stop_price: Decimal, portfolio_nav: Decimal) -> Signal | None`
- Consumed by: daily review workflow and LLM explanation

- [ ] **Step 1: Write failing sizing test**

Create `backend/tests/unit/test_sizing.py`:

```python
from decimal import Decimal

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, Position
from pa_investing.sizing.models import MaxNavWeightSizingModel


def test_max_nav_weight_model_recommends_share_reduction() -> None:
    position = Position(
        account_id="manual-pa",
        instrument=Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY),
        quantity=Decimal("100"),
        average_cost=Decimal("100"),
        latest_price=Decimal("200"),
    )
    model = MaxNavWeightSizingModel(max_weight=Decimal("0.10"))

    recommendation = model.recommend_reduction(position=position, portfolio_nav=Decimal("100000"))

    assert recommendation.quantity_to_reduce == Decimal("50")
    assert recommendation.message == "Reduce 50 shares to bring AAPL back to 10.00% of NAV."
```

- [ ] **Step 2: Write failing signal rule test**

Create `backend/tests/unit/test_signals.py`:

```python
from decimal import Decimal

from pa_investing.domain.enums import AssetClass, SignalSeverity, SignalType
from pa_investing.domain.models import Instrument, Position
from pa_investing.signals.rules import StopReferenceRule
from pa_investing.sizing.models import MaxNavWeightSizingModel


def test_stop_reference_rule_creates_signal_when_price_breaches_stop() -> None:
    position = Position(
        account_id="manual-pa",
        instrument=Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY),
        quantity=Decimal("100"),
        average_cost=Decimal("100"),
        latest_price=Decimal("90"),
    )
    rule = StopReferenceRule(sizing_model=MaxNavWeightSizingModel(max_weight=Decimal("0.10")))

    signal = rule.evaluate(position=position, stop_price=Decimal("95"), portfolio_nav=Decimal("100000"))

    assert signal is not None
    assert signal.symbol == "AAPL"
    assert signal.signal_type == SignalType.STOP_REFERENCE
    assert signal.severity == SignalSeverity.HIGH
    assert "stop/reference level 95" in signal.message
    assert signal.deterministic_recommendation.startswith("Reduce")
```

- [ ] **Step 3: Run tests to verify missing modules**

Run:

```bash
cd backend
pytest tests/unit/test_sizing.py tests/unit/test_signals.py -v
```

Expected: fail with missing `pa_investing.sizing`.

- [ ] **Step 4: Implement deterministic sizing**

Create `backend/src/pa_investing/sizing/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/sizing/models.py`:

```python
from decimal import Decimal, ROUND_DOWN

from pydantic import BaseModel

from pa_investing.domain.models import Position


class SizingRecommendation(BaseModel):
    symbol: str
    quantity_to_reduce: Decimal
    message: str


class MaxNavWeightSizingModel:
    def __init__(self, max_weight: Decimal) -> None:
        self.max_weight = max_weight

    def recommend_reduction(self, position: Position, portfolio_nav: Decimal) -> SizingRecommendation:
        if position.latest_price is None or portfolio_nav <= 0:
            return SizingRecommendation(
                symbol=position.instrument.symbol,
                quantity_to_reduce=Decimal("0"),
                message=f"No reduction for {position.instrument.symbol}; missing price or NAV.",
            )

        max_value = portfolio_nav * self.max_weight
        excess_value = max(position.market_value - max_value, Decimal("0"))
        quantity = (excess_value / position.latest_price).quantize(Decimal("1"), rounding=ROUND_DOWN)
        pct = (self.max_weight * Decimal("100")).quantize(Decimal("0.01"))
        return SizingRecommendation(
            symbol=position.instrument.symbol,
            quantity_to_reduce=quantity,
            message=f"Reduce {quantity} shares to bring {position.instrument.symbol} back to {pct}% of NAV.",
        )
```

- [ ] **Step 5: Implement signal rule**

Create `backend/src/pa_investing/signals/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/signals/rules.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from pa_investing.domain.enums import SignalSeverity, SignalStatus, SignalType
from pa_investing.domain.models import Position, Signal
from pa_investing.sizing.models import MaxNavWeightSizingModel


class StopReferenceRule:
    def __init__(self, sizing_model: MaxNavWeightSizingModel) -> None:
        self.sizing_model = sizing_model

    def evaluate(self, position: Position, stop_price: Decimal, portfolio_nav: Decimal) -> Signal | None:
        if position.latest_price is None or position.latest_price > stop_price:
            return None

        sizing = self.sizing_model.recommend_reduction(position=position, portfolio_nav=portfolio_nav)
        symbol = position.instrument.symbol
        return Signal(
            signal_id=f"sig-{uuid4().hex}",
            symbol=symbol,
            signal_type=SignalType.STOP_REFERENCE,
            severity=SignalSeverity.HIGH,
            status=SignalStatus.OPEN,
            message=f"{symbol} price {position.latest_price} breached stop/reference level {stop_price}.",
            deterministic_recommendation=sizing.message,
            audit_id=f"audit-{uuid4().hex}",
            created_at=datetime.now(tz=UTC),
            analytics_path=f"/analysis/signal/{symbol}",
        )
```

Create `backend/src/pa_investing/signals/service.py`:

```python
from decimal import Decimal

from pa_investing.domain.models import Position, Signal
from pa_investing.signals.rules import StopReferenceRule


class SignalService:
    def __init__(self, stop_rule: StopReferenceRule) -> None:
        self.stop_rule = stop_rule

    def evaluate_stop_rules(
        self,
        positions: list[Position],
        stop_prices: dict[str, Decimal],
        portfolio_nav: Decimal,
    ) -> list[Signal]:
        signals: list[Signal] = []
        for position in positions:
            stop_price = stop_prices.get(position.instrument.symbol)
            if stop_price is None:
                continue
            signal = self.stop_rule.evaluate(position=position, stop_price=stop_price, portfolio_nav=portfolio_nav)
            if signal is not None:
                signals.append(signal)
        return signals
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_sizing.py tests/unit/test_signals.py -v
ruff check .
```

Expected: sizing and signal tests pass and no lint errors.

- [ ] **Step 7: Commit**

```bash
git add backend/src/pa_investing/sizing backend/src/pa_investing/signals backend/tests/unit/test_sizing.py backend/tests/unit/test_signals.py
git commit -m "feat: add deterministic sizing and signal rules"
```

---

### Task 8: Notion Schema Mapping And Fake Client

**Files:**
- Create: `backend/src/pa_investing/notion/__init__.py`
- Create: `backend/src/pa_investing/notion/schemas.py`
- Create: `backend/src/pa_investing/notion/client.py`
- Create: `backend/src/pa_investing/notion/sync.py`
- Test: `backend/tests/unit/test_notion_schemas.py`

**Interfaces:**
- Produces: `NotionPagePayload`
- Produces: `NotionClient.upsert_page(database_name: str, external_id: str, payload: NotionPagePayload) -> str`
- Produces: `NotionSync.build_signal_payload(signal: Signal) -> NotionPagePayload`
- Consumed by: daily review workflow

- [ ] **Step 1: Write failing Notion mapping test**

Create `backend/tests/unit/test_notion_schemas.py`:

```python
from datetime import UTC, datetime

from pa_investing.domain.enums import SignalSeverity, SignalStatus, SignalType
from pa_investing.domain.models import Signal
from pa_investing.notion.client import FakeNotionClient
from pa_investing.notion.sync import NotionSync


def test_notion_sync_writes_signal_payload_to_fake_client() -> None:
    signal = Signal(
        signal_id="sig-1",
        symbol="AAPL",
        signal_type=SignalType.STOP_REFERENCE,
        severity=SignalSeverity.HIGH,
        status=SignalStatus.OPEN,
        message="AAPL breached stop/reference level.",
        deterministic_recommendation="Reduce 10 shares",
        audit_id="audit-1",
        created_at=datetime(2026, 7, 8, tzinfo=UTC),
        analytics_path="/analysis/signal/sig-1",
    )
    client = FakeNotionClient()
    sync = NotionSync(client=client)

    notion_page_id = sync.sync_signal(signal)

    assert notion_page_id == "fake-Signals-sig-1"
    stored = client.pages["Signals"]["sig-1"]
    assert stored.properties["Symbol"] == "AAPL"
    assert stored.properties["Status"] == "open"
    assert stored.properties["Analytics Link"] == "/analysis/signal/sig-1"
```

- [ ] **Step 2: Run tests to verify Notion layer missing**

Run:

```bash
cd backend
pytest tests/unit/test_notion_schemas.py -v
```

Expected: fail with missing `pa_investing.notion`.

- [ ] **Step 3: Implement Notion schema and fake client**

Create `backend/src/pa_investing/notion/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/notion/schemas.py`:

```python
from pydantic import BaseModel


class NotionPagePayload(BaseModel):
    title: str
    properties: dict[str, str]
    body: str
```

Create `backend/src/pa_investing/notion/client.py`:

```python
from abc import ABC, abstractmethod

from pa_investing.notion.schemas import NotionPagePayload


class NotionClient(ABC):
    @abstractmethod
    def upsert_page(self, database_name: str, external_id: str, payload: NotionPagePayload) -> str:
        raise NotImplementedError


class FakeNotionClient(NotionClient):
    def __init__(self) -> None:
        self.pages: dict[str, dict[str, NotionPagePayload]] = {}

    def upsert_page(self, database_name: str, external_id: str, payload: NotionPagePayload) -> str:
        self.pages.setdefault(database_name, {})[external_id] = payload
        return f"fake-{database_name}-{external_id}"
```

Create `backend/src/pa_investing/notion/sync.py`:

```python
from pa_investing.domain.models import Signal
from pa_investing.notion.client import NotionClient
from pa_investing.notion.schemas import NotionPagePayload


class NotionSync:
    def __init__(self, client: NotionClient) -> None:
        self.client = client

    def build_signal_payload(self, signal: Signal) -> NotionPagePayload:
        return NotionPagePayload(
            title=f"{signal.symbol} {signal.signal_type.value}",
            properties={
                "Symbol": signal.symbol,
                "Signal Type": signal.signal_type.value,
                "Severity": signal.severity.value,
                "Status": signal.status.value,
                "Recommendation": signal.deterministic_recommendation,
                "Audit ID": signal.audit_id,
                "Analytics Link": signal.analytics_path or "",
            },
            body=f"{signal.message}\n\nRecommendation: {signal.deterministic_recommendation}",
        )

    def sync_signal(self, signal: Signal) -> str:
        payload = self.build_signal_payload(signal)
        return self.client.upsert_page("Signals", signal.signal_id, payload)
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_notion_schemas.py -v
ruff check .
```

Expected: Notion schema tests pass and no lint errors.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/notion backend/tests/unit/test_notion_schemas.py
git commit -m "feat: add Notion sync adapter"
```

---

### Task 9: LLM Summarization Interface With Mock Provider

**Files:**
- Create: `backend/src/pa_investing/llm/__init__.py`
- Create: `backend/src/pa_investing/llm/interfaces.py`
- Create: `backend/src/pa_investing/llm/mock.py`
- Create: `backend/src/pa_investing/llm/summarizer.py`
- Test: `backend/tests/unit/test_llm_summarizer.py`

**Interfaces:**
- Produces: `LLMProvider.summarize_note(text: str) -> NoteSummary`
- Produces: `NoteSummarizer.summarize(text: str) -> NoteSummary`
- Consumed by: notes inbox ingestion and daily review

- [ ] **Step 1: Write failing summarizer test**

Create `backend/tests/unit/test_llm_summarizer.py`:

```python
from pa_investing.llm.mock import MockLLMProvider
from pa_investing.llm.summarizer import NoteSummarizer


def test_mock_summarizer_limits_summary_length_and_keeps_source_excerpt() -> None:
    text = "Apple reported strong services revenue. " * 40
    summarizer = NoteSummarizer(provider=MockLLMProvider(max_bullets=3))

    summary = summarizer.summarize(text)

    assert len(summary.bullets) == 3
    assert summary.source_excerpt.startswith("Apple reported strong services")
    assert summary.token_budget_note == "mock summary generated without external LLM call"
```

- [ ] **Step 2: Run tests to verify LLM module missing**

Run:

```bash
cd backend
pytest tests/unit/test_llm_summarizer.py -v
```

Expected: fail with missing `pa_investing.llm`.

- [ ] **Step 3: Implement LLM provider interface and mock**

Create `backend/src/pa_investing/llm/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/llm/interfaces.py`:

```python
from abc import ABC, abstractmethod

from pydantic import BaseModel


class NoteSummary(BaseModel):
    bullets: list[str]
    source_excerpt: str
    token_budget_note: str


class LLMProvider(ABC):
    @abstractmethod
    def summarize_note(self, text: str) -> NoteSummary:
        raise NotImplementedError
```

Create `backend/src/pa_investing/llm/mock.py`:

```python
from pa_investing.llm.interfaces import LLMProvider, NoteSummary


class MockLLMProvider(LLMProvider):
    def __init__(self, max_bullets: int = 5) -> None:
        self.max_bullets = max_bullets

    def summarize_note(self, text: str) -> NoteSummary:
        sentences = [sentence.strip() for sentence in text.split(".") if sentence.strip()]
        bullets = sentences[: self.max_bullets]
        while len(bullets) < self.max_bullets:
            bullets.append("No additional distinct claim found in captured text")
        return NoteSummary(
            bullets=bullets,
            source_excerpt=text[:240],
            token_budget_note="mock summary generated without external LLM call",
        )
```

Create `backend/src/pa_investing/llm/summarizer.py`:

```python
from pa_investing.llm.interfaces import LLMProvider, NoteSummary


class NoteSummarizer:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def summarize(self, text: str) -> NoteSummary:
        normalized = " ".join(text.split())
        return self.provider.summarize_note(normalized)
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_llm_summarizer.py -v
ruff check .
```

Expected: summarizer tests pass and no lint errors.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/llm backend/tests/unit/test_llm_summarizer.py
git commit -m "feat: add mockable LLM summarization"
```

---

### Task 10: Daily Review Workflow And Agent API Skeleton

**Files:**
- Create: `backend/src/pa_investing/workflows/__init__.py`
- Create: `backend/src/pa_investing/workflows/daily_review.py`
- Create: `backend/src/pa_investing/workflows/agent_api.py`
- Create: `backend/src/pa_investing/audit/__init__.py`
- Create: `backend/src/pa_investing/audit/events.py`
- Test: `backend/tests/unit/test_agent_api.py`
- Test: `backend/tests/integration/test_daily_review_workflow.py`

**Interfaces:**
- Produces: `AgentAPI.run_daily_review(positions: list[Position], stop_prices: dict[str, Decimal]) -> DailyReviewResult`
- Produces: `DailyReviewWorkflow.run(...) -> DailyReviewResult`
- Consumed by: API routes and future specialist agents

- [ ] **Step 1: Write failing Agent API unit test**

Create `backend/tests/unit/test_agent_api.py`:

```python
from decimal import Decimal

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, Position
from pa_investing.workflows.agent_api import AgentAPI


def test_agent_api_daily_review_returns_snapshot_and_signals() -> None:
    positions = [
        Position(
            account_id="manual-pa",
            instrument=Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY),
            quantity=Decimal("100"),
            average_cost=Decimal("100"),
            latest_price=Decimal("90"),
        )
    ]
    api = AgentAPI()

    result = api.run_daily_review(positions=positions, stop_prices={"AAPL": Decimal("95")})

    assert result.snapshot.nav == Decimal("9000")
    assert len(result.signals) == 1
    assert result.signals[0].symbol == "AAPL"
```

- [ ] **Step 2: Write failing workflow integration test**

Create `backend/tests/integration/test_daily_review_workflow.py`:

```python
from decimal import Decimal
from pathlib import Path

from pa_investing.brokers.csv_importer import CsvPositionImporter
from pa_investing.notion.client import FakeNotionClient
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.daily_review import DailyReviewWorkflow


def test_daily_review_workflow_imports_positions_generates_signal_and_syncs_notion() -> None:
    positions = CsvPositionImporter().import_positions(path=Path("tests/fixtures/positions_sample.csv"))
    notion_client = FakeNotionClient()
    workflow = DailyReviewWorkflow(notion_sync=NotionSync(client=notion_client))

    result = workflow.run(positions=positions, stop_prices={"AAPL": Decimal("180")})

    assert result.snapshot.nav > Decimal("0")
    assert len(result.signals) == 1
    assert "sig-" in next(iter(notion_client.pages["Signals"]))
```

- [ ] **Step 3: Run tests to verify workflows missing**

Run:

```bash
cd backend
pytest tests/unit/test_agent_api.py tests/integration/test_daily_review_workflow.py -v
```

Expected: fail with missing `pa_investing.workflows`.

- [ ] **Step 4: Implement audit event and workflow result models**

Create `backend/src/pa_investing/workflows/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/audit/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/audit/events.py`:

```python
from datetime import datetime

from pydantic import BaseModel


class AuditEvent(BaseModel):
    audit_id: str
    event_type: str
    created_at: datetime
    message: str
```

Create `backend/src/pa_investing/workflows/agent_api.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel

from pa_investing.analytics.snapshots import build_portfolio_snapshot
from pa_investing.domain.models import PortfolioSnapshot, Position, Signal
from pa_investing.signals.rules import StopReferenceRule
from pa_investing.signals.service import SignalService
from pa_investing.sizing.models import MaxNavWeightSizingModel


class DailyReviewResult(BaseModel):
    snapshot: PortfolioSnapshot
    signals: list[Signal]


class AgentAPI:
    def __init__(self) -> None:
        sizing_model = MaxNavWeightSizingModel(max_weight=Decimal("0.10"))
        self.signal_service = SignalService(stop_rule=StopReferenceRule(sizing_model=sizing_model))

    def run_daily_review(self, positions: list[Position], stop_prices: dict[str, Decimal]) -> DailyReviewResult:
        snapshot = build_portfolio_snapshot(
            snapshot_id=f"snap-{uuid4().hex}",
            positions=positions,
            observed_at=datetime.now(tz=UTC),
            base_currency="USD",
        )
        signals = self.signal_service.evaluate_stop_rules(
            positions=positions,
            stop_prices=stop_prices,
            portfolio_nav=snapshot.nav,
        )
        return DailyReviewResult(snapshot=snapshot, signals=signals)
```

- [ ] **Step 5: Implement daily review workflow**

Create `backend/src/pa_investing/workflows/daily_review.py`:

```python
from decimal import Decimal

from pa_investing.domain.models import Position
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.agent_api import AgentAPI, DailyReviewResult


class DailyReviewWorkflow:
    def __init__(self, notion_sync: NotionSync) -> None:
        self.notion_sync = notion_sync
        self.agent_api = AgentAPI()

    def run(self, positions: list[Position], stop_prices: dict[str, Decimal]) -> DailyReviewResult:
        result = self.agent_api.run_daily_review(positions=positions, stop_prices=stop_prices)
        for signal in result.signals:
            self.notion_sync.sync_signal(signal)
        return result
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd backend
pytest tests/unit/test_agent_api.py tests/integration/test_daily_review_workflow.py -v
ruff check .
```

Expected: workflow tests pass and no lint errors.

- [ ] **Step 7: Commit**

```bash
git add backend/src/pa_investing/workflows backend/src/pa_investing/audit backend/tests/unit/test_agent_api.py backend/tests/integration/test_daily_review_workflow.py
git commit -m "feat: add daily review agent workflow"
```

---

### Task 11: FastAPI Routes And Minimal Analytics Pages

**Files:**
- Create: `backend/src/pa_investing/main.py`
- Create: `backend/src/pa_investing/api/__init__.py`
- Create: `backend/src/pa_investing/api/routes.py`
- Create: `backend/src/pa_investing/analytics_app/__init__.py`
- Create: `backend/src/pa_investing/analytics_app/pages.py`
- Test: `backend/tests/integration/test_api_routes.py`

**Interfaces:**
- Produces: `create_app() -> FastAPI`
- Produces: `GET /health`
- Produces: `GET /analysis/portfolio`
- Produces: `GET /analysis/signal/{signal_id}`

- [ ] **Step 1: Write failing API route tests**

Create `backend/tests/integration/test_api_routes.py`:

```python
from fastapi.testclient import TestClient

from pa_investing.main import create_app


def test_health_route() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analysis_signal_page_contains_signal_id() -> None:
    client = TestClient(create_app())

    response = client.get("/analysis/signal/sig-123")

    assert response.status_code == 200
    assert "sig-123" in response.text
    assert "Signal Analysis" in response.text
```

- [ ] **Step 2: Run tests to verify API missing**

Run:

```bash
cd backend
pytest tests/integration/test_api_routes.py -v
```

Expected: fail with missing `pa_investing.main`.

- [ ] **Step 3: Implement analytics HTML helpers and routes**

Create `backend/src/pa_investing/analytics_app/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/analytics_app/pages.py`:

```python
def portfolio_page() -> str:
    return """
    <html>
      <head><title>Portfolio Analysis</title></head>
      <body>
        <h1>Portfolio Analysis</h1>
        <p>Phase 1 analytics cockpit link target.</p>
      </body>
    </html>
    """


def signal_page(signal_id: str) -> str:
    return f"""
    <html>
      <head><title>Signal Analysis</title></head>
      <body>
        <h1>Signal Analysis</h1>
        <p>Signal ID: {signal_id}</p>
      </body>
    </html>
    """
```

Create `backend/src/pa_investing/api/__init__.py`:

```python
__all__ = []
```

Create `backend/src/pa_investing/api/routes.py`:

```python
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from pa_investing.analytics_app.pages import portfolio_page, signal_page

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/analysis/portfolio", response_class=HTMLResponse)
def portfolio_analysis() -> str:
    return portfolio_page()


@router.get("/analysis/signal/{signal_id}", response_class=HTMLResponse)
def signal_analysis(signal_id: str) -> str:
    return signal_page(signal_id)
```

Create `backend/src/pa_investing/main.py`:

```python
from fastapi import FastAPI

from pa_investing.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="PA Investing Backend")
    app.include_router(router)
    return app


app = create_app()
```

- [ ] **Step 4: Run API tests**

Run:

```bash
cd backend
pytest tests/integration/test_api_routes.py -v
ruff check .
```

Expected: API tests pass and no lint errors.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/main.py backend/src/pa_investing/api backend/src/pa_investing/analytics_app backend/tests/integration/test_api_routes.py
git commit -m "feat: add API and analytics link pages"
```

---

### Task 12: Docker Compose, Local Runbook, And Full Verification

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/docker-compose.yml`
- Modify: `backend/README.md`
- Test: full test suite and Docker config validation

**Interfaces:**
- Produces: local development service `backend-api`
- Produces: local PostgreSQL service `postgres`

- [ ] **Step 1: Add Dockerfile**

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "pa_investing.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Add Docker Compose**

Create `backend/docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: pa_investing
      POSTGRES_PASSWORD: pa_investing
      POSTGRES_DB: pa_investing
    ports:
      - "5432:5432"
    volumes:
      - pa_postgres_data:/var/lib/postgresql/data

  backend-api:
    build: .
    environment:
      PA_ENVIRONMENT: local
      PA_DATABASE_URL: postgresql+psycopg://pa_investing:pa_investing@postgres:5432/pa_investing
      PA_NOTION_ENABLED: "false"
      PA_LLM_PROVIDER: mock
    ports:
      - "8000:8000"
    depends_on:
      - postgres

volumes:
  pa_postgres_data:
```

- [ ] **Step 3: Update README runbook**

Append to `backend/README.md`:

````markdown
## Docker

```bash
docker compose up --build
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Phase 1 Verification

```bash
pytest
ruff check .
```
````

- [ ] **Step 4: Run local verification**

Run:

```bash
cd backend
pytest
ruff check .
docker compose config
```

Expected: all tests pass, no lint errors, Docker Compose config renders successfully.

- [ ] **Step 5: Commit**

```bash
git add backend/Dockerfile backend/docker-compose.yml backend/README.md
git commit -m "chore: add Docker deployment scaffold"
```

---

## Final Verification Before Handoff

Run:

```bash
cd backend
pytest
ruff check .
docker compose config
git status --short
```

Expected:

- `pytest` passes.
- `ruff check .` reports no issues.
- `docker compose config` exits successfully.
- `git status --short` is empty after the final commit.

## Coverage Against Spec

- Notion command center: Task 8 creates schema mapping and fake sync.
- Python backend skeleton: Tasks 1, 3, 11, 12.
- PostgreSQL schema: Task 3.
- CSV/manual import: Task 4.
- Free/delayed prices: Task 5 manual provider, suitable for delayed/end-of-day CSV import.
- NAV/PnL/exposure/risk base: Task 6.
- Rule-based signals: Task 7.
- Deterministic sizing: Task 7.
- Notion sync: Task 8 and Task 10.
- Agent API skeleton: Task 10.
- Minimal analytics link target: Task 11.
- LLM summarization interface: Task 9.
- Docker/NAS deployment foundation: Task 12.
