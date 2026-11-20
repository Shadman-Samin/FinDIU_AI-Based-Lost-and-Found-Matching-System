from fastapi import APIRouter, Request

from backend.app.metadata import CATEGORIES, COLORS, LOCATIONS, as_options

router = APIRouter(prefix="/api/v1/metadata", tags=["metadata"])


@router.get("")
def metadata(request: Request):
    return {
        "categories": as_options(CATEGORIES),
        "colors": as_options(COLORS),
        "locations": as_options(LOCATIONS),
        "consent_version": request.app.state.settings.consent_version,
        "matching_mode": request.app.state.settings.matching_mode,
        "semantic_enabled": request.app.state.settings.semantic_enabled,
    }
