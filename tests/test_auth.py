from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from pydantic import ValidationError
from test_health import make_settings


def test_passwords_are_hashed_and_wrong_password_rejected():
    from backend.app.auth import hash_password, verify_password

    stored = hash_password("a-password-for-testing")
    assert stored != "a-password-for-testing"
    assert verify_password(stored, "a-password-for-testing")
    assert not verify_password(stored, "incorrect-password")
    assert not verify_password("corrupted-hash", "a-password-for-testing")


def test_token_contains_only_required_identity_claims():
    from backend.app.auth import create_token, decode_token

    settings = make_settings()
    user_id = uuid4()
    token = create_token(user_id, settings)
    assert decode_token(token, settings) == user_id
    payload = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=settings.jwt_audience,
    )
    assert "role" not in payload
    assert payload["exp"] - payload["iat"] == 3600


@pytest.mark.parametrize(
    "invalid", ["expired", "audience", "issuer", "algorithm", "subject", "missing_exp"]
)
def test_invalid_token_is_rejected(invalid):
    from backend.app.auth import decode_token
    from backend.app.errors import AppError

    settings = make_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(hours=1),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    algorithm = "HS256"
    if invalid == "expired":
        payload["exp"] = now - timedelta(seconds=1)
    elif invalid == "audience":
        payload["aud"] = "some-other-app"
    elif invalid == "issuer":
        payload["iss"] = "some-other-issuer"
    elif invalid == "algorithm":
        algorithm = "HS384"
    elif invalid == "subject":
        payload["sub"] = "not-a-user-id"
    else:
        del payload["exp"]
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=algorithm)
    with pytest.raises(AppError) as error:
        decode_token(token, settings)
    assert error.value.status == 401


def test_registration_rejects_chosen_role_and_normalizes_email():
    from backend.app.schemas import RegisterInput

    valid = {
        "name": " Demo User ",
        "email": "  Person@Example.COM ",
        "password": "a-password-for-testing",
    }
    user = RegisterInput(**valid)
    assert user.email == "person@example.com"
    assert user.name == "Demo User"
    with pytest.raises(ValidationError):
        RegisterInput(**valid, role="admin")
    with pytest.raises(ValidationError):
        RegisterInput(**(valid | {"name": "   "}))


def test_limiter_recovers_after_window():
    from backend.app.errors import AppError
    from backend.app.limits import Limiter

    limiter = Limiter()
    for _ in range(5):
        limiter.check("login:127.0.0.1", 5, 60, now=10)
    with pytest.raises(AppError) as error:
        limiter.check("login:127.0.0.1", 5, 60, now=11)
    assert error.value.status == 429
    limiter.check("login:127.0.0.1", 5, 60, now=71)
