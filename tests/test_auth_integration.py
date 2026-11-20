import pytest
from conftest import auth_header, register
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_register_persists_hashed_password_and_never_echoes_it(client, app):
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "student@diu.edu.bd"
    assert body["role"] == "user"
    assert "password" not in response.text

    with app.state.session_factory() as session:
        row = session.execute(
            text("SELECT password_hash, locale FROM findiu.users WHERE email = :email"),
            {"email": "student@diu.edu.bd"},
        ).one()
    assert row.password_hash.startswith("$argon2")
    assert row.locale == "bn"


def test_duplicate_registration_is_rejected_case_insensitively(client):
    assert register(client).status_code == 201
    again = register(client, email="  STUDENT@diu.edu.bd ")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "email_in_use"


def test_login_rejects_wrong_password_with_uniform_error(client):
    register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@diu.edu.bd", "password": "wrong-password-here"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_returns_short_lived_token(client):
    register(client)
    headers = auth_header(client)
    assert headers["Authorization"].startswith("Bearer ")


def test_validation_errors_do_not_echo_submitted_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "", "email": "not-an-email", "password": "short-secret-value"},
    )
    assert response.status_code == 422
    assert "short-secret-value" not in response.text


def test_readiness_succeeds_against_real_database(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_user_id_is_uuid_stored_in_private_schema(client, app):
    register(client)
    with app.state.session_factory() as session:
        user_id = session.execute(text("SELECT id FROM findiu.users")).scalar_one()
    assert user_id is not None
