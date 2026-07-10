from pathlib import Path

from pa_investing.core.config import Settings
from pa_investing.db.session import DatabaseSessionFactory
from pa_investing.seeds.demo_portfolio import SeedResult, seed_demo_portfolio


def default_demo_csv_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "positions_demo_portfolio.csv"
    )


def main(
    settings: Settings | None = None,
    csv_path: Path | None = None,
    session_factory: DatabaseSessionFactory | None = None,
) -> SeedResult:
    resolved_settings = settings or Settings()
    resolved_csv_path = csv_path or default_demo_csv_path()
    resolved_session_factory = session_factory or DatabaseSessionFactory(resolved_settings)

    with resolved_session_factory.session() as session:
        result = seed_demo_portfolio(session=session, csv_path=resolved_csv_path)
        session.commit()

    print(
        f"Seeded demo portfolio {result.account_id} with {result.positions_loaded} positions"
    )
    return result


if __name__ == "__main__":
    main()
