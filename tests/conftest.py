"""PostgreSQL-backed fixtures.

Integration tests are skipped unless TEST_DATABASE_URL points at a dedicated
database whose name ends in ``_test``. There is deliberately no SQLite fallback:
row locks, advisory locks, JSONB and ``timestamptz`` are part of the behaviour
under test.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
TEST_SECRET = "test-only-secret-with-at-least-32-characters"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("set TEST_DATABASE_URL to a PostgreSQL database ending in _test")

    from backend.app.db import validate_test_database

    url = validate_test_database(raw, os.environ.get("DATABASE_URL"))
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> str:
    from alembic import command
    from alembic.config import Config

    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    config.attributes["database_url"] = test_database_url
    command.upgrade(config, "head")
    return test_database_url


@pytest.fixture
def app_settings(migrated_database: str, tmp_path):
    from backend.app.config import Settings

    return Settings(
        _env_file=None,
        database_url=migrated_database,
        jwt_secret=TEST_SECRET,
        upload_dir=str(tmp_path / "uploads"),
        public_base_url="http://testserver",
        embedding_provider="local",
        storage_provider="local",
        brevo_api_key="",
        brevo_sender_email="",
        gemini_api_key="",
        supabase_url="",
        supabase_service_role_key="",
        internal_tick_token="test-tick-token",
    )


@pytest.fixture
def app(app_settings):
    from backend.app.main import create_app

    application = create_app(app_settings)
    with application.state.session_factory() as session:
        session.execute(
            text("TRUNCATE findiu.claims, findiu.matches, findiu.items, findiu.users CASCADE")
        )
        session.commit()
    return application


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


def register(client, email="student@diu.edu.bd", password="correct-horse-battery"):
    return client.post(
        "/api/v1/auth/register",
        json={"name": "Student", "email": email, "password": password, "locale": "bn"},
    )


def auth_header(client, email="student@diu.edu.bd", password="correct-horse-battery"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
