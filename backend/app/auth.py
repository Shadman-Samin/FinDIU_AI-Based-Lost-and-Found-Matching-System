from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from backend.app.config import Settings
from backend.app.errors import AppError

_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return _hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def create_token(user_id: UUID, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(hours=1),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_token(token: str, settings: Settings) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "iat", "exp", "iss", "aud"]},
        )
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        raise AppError(401, "unauthorized", "Please sign in again.") from None
