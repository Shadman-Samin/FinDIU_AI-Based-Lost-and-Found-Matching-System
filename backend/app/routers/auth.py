from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.auth import create_token, hash_password, verify_password
from backend.app.db import get_session
from backend.app.errors import AppError
from backend.app.limits import Limiter
from backend.app.models import User
from backend.app.schemas import RegisterInput

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_limiter(request: Request) -> Limiter:
    if not hasattr(request.app.state, "limiter"):
        request.app.state.limiter = Limiter()
    return request.app.state.limiter


@router.post("/register", status_code=201)
def register(payload: RegisterInput, request: Request, session: Session = Depends(get_session)):
    client = request.client.host if request.client else "unknown"
    get_limiter(request).check(
        f"registration:{client}", request.app.state.settings.registration_limit, 3600
    )
    existing = session.scalar(select(User).where(User.email == str(payload.email)))
    if existing:
        raise AppError(409, "email_in_use", "An account already exists for this email.")
    user = User(
        name=payload.name,
        email=str(payload.email),
        password_hash=hash_password(payload.password.get_secret_value()),
        locale=payload.locale,
    )
    session.add(user)
    session.commit()
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "locale": user.locale,
    }


@router.post("/login")
def login(payload: dict, request: Request, session: Session = Depends(get_session)):
    email = payload.get("email", "")
    password = payload.get("password", "")
    if not isinstance(email, str) or not isinstance(password, str):
        raise AppError(401, "invalid_credentials", "Email or password is incorrect.")
    client = request.client.host if request.client else "unknown"
    get_limiter(request).check(f"login:{client}", request.app.state.settings.login_limit, 60)
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not verify_password(user.password_hash, password):
        raise AppError(401, "invalid_credentials", "Email or password is incorrect.")
    return {
        "access_token": create_token(user.id, request.app.state.settings),
        "token_type": "bearer",
        "expires_in": 3600,
    }
