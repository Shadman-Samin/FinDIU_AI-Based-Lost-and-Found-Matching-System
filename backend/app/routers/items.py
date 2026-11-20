from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.db import get_session, lifecycle_lock
from backend.app.dependencies import get_current_user
from backend.app.errors import AppError, ServiceFailure
from backend.app.image_features import FEATURE_VERSION, image_features
from backend.app.image_utils import MAX_BYTES, prepare_image
from backend.app.lifecycle import editable, invalidate, lock_items, visible_matches
from backend.app.models import Item, ItemStatus, ItemType, Match, Role, User, utcnow
from backend.app.schemas import ItemInput, StatusUpdate, item_public_fields

router = APIRouter(prefix="/api/v1/items", tags=["items"])

TRUTHY = {"on", "true", "1", "yes"}


def _serialize(item: Item, storage, include_private: bool = False) -> dict:
    data = {field: getattr(item, field) for field in sorted(item_public_fields())}
    data["id"] = str(item.id)
    data["event_date"] = item.event_date.isoformat()
    data["created_at"] = item.created_at.isoformat()
    data["updated_at"] = item.updated_at.isoformat()
    data["revision"] = item.revision
    data["type"] = getattr(item.type, "value", item.type)
    data["status"] = getattr(item.status, "value", item.status)
    if item.image_path:
        try:
            data["image_url"] = storage.signed_url(item.image_path)
        except ServiceFailure:
            data["image_url"] = None
    if include_private:
        data["private_detail"] = item.private_detail
        data["content_revision"] = item.content_revision
        data["embed_status"] = item.embed_status
        data["embedding_model"] = item.embedding_model
        data["match_pending"] = item.match_pending
        data["embed_last_error_code"] = item.embed_last_error_code
        data["semantic_consent"] = item.semantic_consent
    return data


def _can_view(item: Item, user: User) -> bool:
    return item.user_id == user.id or user.role == Role.ADMIN


@router.post("", status_code=201)
def create_item(
    request: Request,
    type: Literal["lost", "found"] | None = Query(None),
    report_type: Literal["lost", "found"] | None = Form(None, alias="type"),
    category: str = Form(...),
    color: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    location: str = Form(...),
    event_date: str = Form(...),
    private_detail: str = Form(...),
    brand: str = Form(""),
    consent: str = Form(...),
    semantic_consent: bool = Form(False),
    image: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    settings = request.app.state.settings
    if type and report_type and type != report_type:
        raise AppError(422, "validation_error", "Report types must agree.")
    type = report_type or type
    if type is None:
        raise AppError(422, "validation_error", "Report type is required.")
    if consent.strip().lower() not in TRUTHY:
        raise AppError(422, "consent_required", "Confirm the privacy notice to continue.")
    request.app.state.limiter.check(f"report:{user.id}", settings.report_limit, 3600)
    try:
        payload = ItemInput(
            category=category,
            color=color,
            brand=brand,
            title=title,
            description=description,
            location=location,
            event_date=event_date,
            private_detail=private_detail,
        )
    except ValidationError as error:
        raise AppError(
            422,
            "validation_error",
            "Check the highlighted fields.",
            fields=[
                {"field": ".".join(map(str, e["loc"])), "code": e["type"]} for e in error.errors()
            ],
        ) from None

    storage = request.app.state.storage
    image_key = None
    features = None
    if image is not None and image.filename:
        raw = image.file.read(MAX_BYTES + 1)
        prepared = prepare_image(raw)
        features = image_features(prepared)
        image_key = f"{user.id}/{uuid4().hex}.jpg"
        storage.put(image_key, prepared)

    item = Item(
        type=ItemType(type),
        user_id=user.id,
        category=payload.category,
        color=payload.color,
        brand=payload.brand,
        title=payload.title,
        description=payload.description,
        location=payload.location,
        event_date=payload.event_date,
        private_detail=payload.private_detail,
        image_path=image_key,
        image_features=features,
        feature_version=FEATURE_VERSION,
        embed_status="pending" if semantic_consent else "ready",
        consent_version=settings.consent_version,
        semantic_consent=semantic_consent,
        consented_at=utcnow(),
    )
    try:
        session.add(item)
        session.commit()
    except Exception:
        session.rollback()
        if image_key:
            storage.delete(image_key)
        raise
    return _serialize(item, storage, include_private=True)


@router.get("")
def list_items(
    request: Request,
    mine: bool = Query(False),
    type: Literal["lost", "found"] | None = Query(None),
    category: str | None = Query(None, max_length=32),
    location: str | None = Query(None, max_length=32),
    status: ItemStatus | None = Query(None),
    q: str | None = Query(None, max_length=80),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    query = select(Item).where(Item.user_id == user.id)
    mine = True
    if type:
        query = query.where(Item.type == ItemType(type))
    if category:
        query = query.where(Item.category == category)
    if location:
        query = query.where(Item.location == location)
    if status:
        query = query.where(Item.status == status.value)
    if q and q.strip():
        search = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Item.title.ilike(pattern, escape="\\"),
                Item.description.ilike(pattern, escape="\\"),
                Item.brand.ilike(pattern, escape="\\"),
            )
        )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    status_counts = {member.value: 0 for member in ItemStatus}
    for value, count in session.execute(
        select(Item.status, func.count()).where(Item.user_id == user.id).group_by(Item.status)
    ):
        status_counts[getattr(value, "value", value)] = count
    query = query.order_by(Item.created_at.desc(), Item.id).limit(limit + 1).offset(offset)
    rows = session.scalars(query).all()
    has_more = len(rows) > limit
    storage = request.app.state.storage
    items = rows[:limit]
    counts: dict = {}
    if mine and items:
        ids = [item.id for item in items]
        for column in (Match.lost_id, Match.found_id):
            for item_id, match_count in session.execute(
                select(column, func.count())
                .where(Match.valid.is_(True), column.in_(ids))
                .group_by(column)
            ):
                counts[item_id] = counts.get(item_id, 0) + match_count
    payload = []
    for item in items:
        data = _serialize(item, storage, include_private=True)
        if mine:
            data["analysis"] = (
                "pending" if item.match_pending and item.status == "active" else "ready"
            )
            data["matches_count"] = counts.get(item.id, 0)
        payload.append(data)
    return {
        "items": payload,
        "limit": limit,
        "offset": offset,
        "total": total,
        "next_offset": offset + limit if has_more else None,
        "counts": status_counts,
    }


@router.get("/{item_id}")
def get_item(
    item_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = session.get(Item, item_id)
    if item is None or not _can_view(item, user):
        raise AppError(404, "not_found", "Item not found.")
    include_private = item.user_id == user.id or user.role == Role.ADMIN
    return _serialize(item, request.app.state.storage, include_private=include_private)


@router.post("/{item_id}/archive")
def archive_item(
    item_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lifecycle_lock(session)
    rows = lock_items(session, [item_id])
    item = rows[0] if rows else None
    if item is None or (item.user_id != user.id and user.role != Role.ADMIN):
        raise AppError(404, "not_found", "Item not found.")
    editable(session, item)
    item.status = ItemStatus.ARCHIVED
    item.revision += 1
    item.match_pending = False
    item.embed_lease_token = None
    invalidate(session, [item.id])
    session.commit()
    return _serialize(item, request.app.state.storage, include_private=True)


@router.patch("/{item_id}")
async def edit_item(
    item_id: UUID,
    request: Request,
    expected_revision: int | None = Form(None, ge=1),
    category: str | None = Form(None),
    color: str | None = Form(None),
    brand: str | None = Form(None),
    title: str | None = Form(None),
    description: str | None = Form(None),
    location: str | None = Form(None),
    event_date: str | None = Form(None),
    private_detail: str | None = Form(None),
    consent: str | None = Form(None),
    semantic_consent: bool | None = Form(None),
    remove_image: bool = Form(False),
    image: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    # Keep the shipped JSON archive contract, but never allow reactivation.
    legacy = None
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            legacy = StatusUpdate.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise AppError(422, "validation_error", "Check the highlighted fields.") from None
        expected_revision = legacy.expected_revision
    lifecycle_lock(session)
    rows = lock_items(session, [item_id])
    item = rows[0] if rows else None
    if item is None or not _can_view(item, user):
        raise AppError(404, "not_found", "Item not found.")
    if expected_revision is None:
        raise AppError(422, "validation_error", "expected_revision is required.")
    if item.revision != expected_revision:
        raise AppError(409, "stale_revision", "This report changed. Reload and try again.")
    if semantic_consent is not None and user.id != item.user_id:
        raise AppError(
            403, "forbidden", "Only the report owner can change external processing consent."
        )
    editable(session, item)
    if legacy:
        if legacy.status != "archived":
            raise AppError(409, "lifecycle_conflict", "Archival is terminal.")
        return archive_item(item_id, request, user, session)
    changes = {
        "category": category,
        "color": color,
        "brand": brand,
        "title": title,
        "description": description,
        "location": location,
        "event_date": event_date,
        "private_detail": private_detail,
    }
    try:
        payload = ItemInput.model_validate(
            {
                key: value if value is not None else getattr(item, key)
                for key, value in changes.items()
            }
        )
    except ValidationError as error:
        raise AppError(
            422,
            "validation_error",
            "Check the highlighted fields.",
            fields=[
                {"field": ".".join(map(str, e["loc"])), "code": e["type"]} for e in error.errors()
            ],
        ) from None
    values = payload.model_dump()
    matching_changed = (
        any(getattr(item, key) != value for key, value in values.items() if key != "private_detail")
        or bool(image and image.filename)
        or remove_image
        or (semantic_consent is not None and semantic_consent != item.semantic_consent)
    )
    if matching_changed and (consent or "").lower() not in TRUTHY:
        raise AppError(422, "consent_required", "Confirm AI processing consent to continue.")
    if remove_image and image and image.filename:
        raise AppError(422, "validation_error", "Choose replacement or removal, not both.")
    storage = request.app.state.storage
    old_key, new_key = item.image_path, None
    features = item.image_features
    if image and image.filename:
        prepared = prepare_image(image.file.read(MAX_BYTES + 1))
        features = image_features(prepared)
        new_key = f"{user.id}/{uuid4().hex}.jpg"
        storage.put(new_key, prepared)
    try:
        for key, value in values.items():
            setattr(item, key, value)
        if new_key or remove_image:
            item.image_path = new_key
            item.image_features = features if new_key else None
            item.feature_version = FEATURE_VERSION
        item.revision += 1
        if matching_changed:
            if semantic_consent is not None:
                item.semantic_consent = bool(semantic_consent)
            item.content_revision += 1
            item.text_embedding = item.image_embedding = None
            item.embedded_revision = None
            item.embedding_model = item.embedding_dimensions = None
            item.embed_status = "pending" if item.semantic_consent else "ready"
            item.embed_attempts = 0
            item.embed_lease_until = item.embed_lease_token = None
            item.embed_next_attempt_at = item.embed_last_error_code = None
            item.match_pending = True
            item.consent_version = request.app.state.settings.consent_version
            item.consented_at = utcnow()
            invalidate(session, [item.id])
        session.commit()
    except Exception:
        session.rollback()
        if new_key:
            storage.delete(new_key)
        raise
    if old_key and (new_key or remove_image):
        storage.delete(old_key)
    return _serialize(item, storage, include_private=True)


@router.get("/{item_id}/image")
def item_image(
    item_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = session.get(Item, item_id)
    allowed = item is not None and _can_view(item, user)
    if item and not allowed:
        own_ids = select(Item.id).where(Item.user_id == user.id)
        allowed = (
            session.scalar(
                visible_matches()
                .where(
                    or_(
                        (Match.lost_id == item_id) & Match.found_id.in_(own_ids),
                        (Match.found_id == item_id) & Match.lost_id.in_(own_ids),
                    )
                )
                .limit(1)
            )
            is not None
        )
    if not allowed or not item.image_path:
        raise AppError(404, "not_found", "Image not found.")
    response.headers["Cache-Control"] = "no-store"
    return {"url": request.app.state.storage.signed_url(item.image_path), "expires_in": 300}
