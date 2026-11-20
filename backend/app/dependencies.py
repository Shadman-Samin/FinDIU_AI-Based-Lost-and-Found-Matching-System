from fastapi import Depends, Request
from sqlalchemy.orm import Session

from backend.app.auth import decode_token
from backend.app.db import get_session
from backend.app.errors import AppError
from backend.app.models import Role, User


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AppError(401, "unauthorized", "Please sign in again.")
    user_id = decode_token(token.strip(), request.app.state.settings)
    user = session.get(User, user_id)
    if user is None:
        raise AppError(401, "unauthorized", "Please sign in again.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "You do not have access to this resource.")
    return user
