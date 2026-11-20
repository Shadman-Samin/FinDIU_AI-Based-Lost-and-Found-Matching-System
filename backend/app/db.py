from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker


def validate_test_database(test_url: str, production_url: str | None) -> URL:
    candidate = make_url(test_url)
    if candidate.get_backend_name() != "postgresql" or not (candidate.database or "").endswith(
        "_test"
    ):
        raise ValueError("Tests require a dedicated PostgreSQL database ending in _test")

    def identity(url: URL) -> tuple:
        host = (url.host or "localhost").lower()
        if host in {"localhost", "127.0.0.1", "::1"}:
            host = "loopback"
        return host, url.port or 5432, url.database

    if production_url and identity(candidate) == identity(make_url(production_url)):
        raise ValueError("Test and application databases must be different")
    return candidate.set(drivername="postgresql+psycopg")


def create_session_factory(url: str):
    engine = create_engine(
        make_url(url).set(drivername="postgresql+psycopg"),
        pool_size=3,
        max_overflow=2,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 3,
            "options": "-c timezone=UTC -c statement_timeout=15000",
        },
    )
    return engine, sessionmaker(engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def lifecycle_lock(session: Session) -> None:
    # Serialized lifecycle writes are sufficient for the small demonstration dataset.
    session.execute(text("SELECT pg_advisory_xact_lock(6071101)"))
