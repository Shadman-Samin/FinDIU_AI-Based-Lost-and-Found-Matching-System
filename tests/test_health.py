import pytest
from fastapi.testclient import TestClient


def make_settings(**overrides):
    from backend.app.config import Settings

    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused:unused@127.0.0.1:1/findiu_dev",
        jwt_secret="test-only-secret-with-at-least-32-characters",
        storage_provider="local",
        **overrides,
    )


def test_health_does_not_require_provider_calls():
    from backend.app.main import create_app

    with TestClient(create_app(make_settings())) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_failure_does_not_expose_database_credentials():
    from backend.app.main import create_app

    with TestClient(create_app(make_settings())) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "unused" not in response.text


def test_cors_rejects_unknown_origins():
    from backend.app.main import create_app

    with TestClient(
        create_app(make_settings(allowed_origins=["https://findiu.example"]))
    ) as client:
        response = client.options(
            "/health",
            headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "GET"},
        )
    assert "access-control-allow-origin" not in response.headers


def test_core_settings_require_a_long_signing_secret():
    from pydantic import ValidationError

    from backend.app.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql://localhost/findiu", jwt_secret="short")


@pytest.mark.parametrize(
    "test_url,production_url",
    [
        ("postgresql://localhost/findiu", None),
        ("postgresql://localhost/findiu_test", "postgresql+psycopg://localhost/findiu_test"),
        (
            "postgresql://alice:one@localhost/findiu_test",
            "postgresql://bob:two@localhost:5432/findiu_test",
        ),
        ("sqlite:///findiu_test", None),
    ],
)
def test_unsafe_test_database_is_refused(test_url, production_url):
    from backend.app.db import validate_test_database

    with pytest.raises(ValueError):
        validate_test_database(test_url, production_url)


def test_dedicated_postgres_database_is_accepted():
    from backend.app.db import validate_test_database

    assert (
        validate_test_database("postgresql://localhost/findiu_test", None).database == "findiu_test"
    )
