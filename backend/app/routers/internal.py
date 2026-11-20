import hmac

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.db import get_session
from backend.app.errors import AppError
from backend.app.notifications import build_notifier
from backend.app.processing import run_tick
from backend.app.providers import build_embedder

router = APIRouter(prefix="/internal", tags=["operations"])


def _authorize(request: Request) -> None:
    expected = request.app.state.settings.internal_tick_token.get_secret_value()
    if not expected:
        raise AppError(503, "tick_disabled", "Background processing is not configured.")
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip(), expected):
        raise AppError(401, "unauthorized", "Invalid tick credentials.")


@router.post("/tick")
def tick(request: Request, session: Session = Depends(get_session)):
    _authorize(request)
    state = request.app.state
    settings = state.settings
    if not settings.semantic_enabled:
        state.embedder = None
    elif getattr(state, "embedder", None) is None:
        state.embedder = build_embedder(settings)
    if getattr(state, "notifier", None) is None:
        state.notifier = build_notifier(settings)
    result = run_tick(session, settings, state.embedder, state.storage, state.notifier)
    return {
        "status": "ok",
        "matching_mode": settings.matching_mode,
        "semantic_enabled": settings.semantic_enabled,
        **result,
    }
