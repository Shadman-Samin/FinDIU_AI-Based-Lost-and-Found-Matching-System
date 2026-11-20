from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.db import get_session, lifecycle_lock
from backend.app.dependencies import get_current_user
from backend.app.errors import AppError
from backend.app.lifecycle import current_match, invalidate, lock_items, visible_matches
from backend.app.models import Claim, ClaimStatus, Item, ItemStatus, Match, Role, User, utcnow
from backend.app.routers.items import _serialize
from backend.app.schemas import ClaimCreate, ClaimDecision, ClaimInput

router = APIRouter(prefix="/api/v1", tags=["matches"])


def _public(item: Item, storage) -> dict:
    return _serialize(item, storage)


def _participant(match: Match, lost: Item, found: Item, user: User) -> bool:
    if user.role == Role.ADMIN:
        return True
    return user.id in {lost.user_id, found.user_id}


@router.get("/items/{item_id}/matches")
def matches_for_item(
    item_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    item = session.get(Item, item_id)
    if item is None or (item.user_id != user.id and user.role != Role.ADMIN):
        raise AppError(404, "not_found", "Item not found.")
    query = visible_matches()
    query = query.where(
        Match.valid.is_(True), or_(Match.lost_id == item.id, Match.found_id == item.id)
    )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    matches = session.scalars(
        query.order_by(Match.score.desc(), Match.id).limit(limit).offset(offset)
    ).all()
    results = [match_detail(match, request, user, session) for match in matches]
    return {"items": results, "matches": results, "limit": limit, "offset": offset, "total": total}


@router.post("/matches/{match_id}/claims", status_code=201)
def submit_claim(
    match_id: UUID,
    payload: ClaimInput,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lifecycle_lock(session)
    match = session.get(Match, match_id)
    if match is None or not match.valid:
        raise AppError(404, "not_found", "Match not found.")
    lock_items(session, [match.lost_id, match.found_id])
    session.refresh(match)
    lost = session.get(Item, match.lost_id)
    found = session.get(Item, match.found_id)
    if lost is None or found is None or lost.user_id != user.id:
        raise AppError(404, "not_found", "Match not found.")
    if not current_match(match, lost, found) or lost.status != "active" or found.status != "active":
        raise AppError(409, "lifecycle_conflict", "This candidate is no longer claimable.")
    request.app.state.limiter.check(
        f"claim:{user.id}", request.app.state.settings.claim_limit, 3600
    )
    existing = session.scalar(
        select(Claim).where(Claim.match_id == match.id, Claim.claimant_id == user.id)
    )
    if existing is not None:
        raise AppError(409, "claim_exists", "You already submitted a claim for this match.")
    claim = Claim(match_id=match.id, claimant_id=user.id, answer=payload.answer)
    session.add(claim)
    session.commit()
    return {
        "id": str(claim.id),
        "status": claim.status,
        "message": "Your claim is with the review desk. You will be contacted after verification.",
    }


@router.get("/claims/mine")
def my_claims(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    result = list_claims(limit, offset, user, session)
    result["claims"] = [{**claim, "note": claim["review_note"]} for claim in result["items"]]
    return result


@router.get("/admin/claims")
def review_queue(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    status: Literal["pending", "approved", "rejected", "returned"] | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "You do not have access to this resource.")
    counts = {"pending": 0, "approved": 0, "returned": 0, "rejected": 0}
    for value, returned_at in session.execute(select(Claim.status, Claim.returned_at)):
        key = getattr(value, "value", value)
        if key == "approved" and returned_at is not None:
            counts["returned"] += 1
        else:
            counts[key] = counts.get(key, 0) + 1
    query = select(Claim)
    if status == "returned":
        query = query.where(Claim.returned_at.is_not(None))
    elif status == "approved":
        query = query.where(Claim.status == status, Claim.returned_at.is_(None))
    elif status:
        query = query.where(Claim.status == status)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    claims = session.scalars(
        query.order_by(Claim.created_at, Claim.id).limit(limit).offset(offset)
    ).all()
    storage = request.app.state.storage
    results = []
    for claim in claims:
        match = session.get(Match, claim.match_id)
        lost = session.get(Item, match.lost_id)
        found = session.get(Item, match.found_id)
        claimant = session.get(User, claim.claimant_id)
        results.append(
            {
                "id": str(claim.id),
                "status": getattr(claim.status, "value", claim.status),
                "answer": claim.answer,
                "review_note": claim.review_note,
                "returned_at": claim.returned_at,
                "match_id": str(claim.match_id),
                "created_at": claim.created_at.isoformat(),
                "claimant": {"name": claimant.name, "email": claimant.email},
                "match": {
                    "id": str(match.id),
                    "score": match.score,
                    "text_sim": match.text_sim,
                    "image_sim": match.image_sim,
                    "attr_score": match.attr_score,
                    "evidence": match.evidence,
                    "scoring_version": match.scoring_version,
                    "threshold": (match.evidence or {}).get("threshold"),
                    "lost": _serialize(lost, storage),
                    "found": _serialize(found, storage),
                    "lost_title": lost.title,
                    "found_title": found.title,
                    "lost_private_detail": lost.private_detail,
                    "found_private_detail": found.private_detail,
                },
            }
        )
    return {
        "items": results,
        "claims": results,
        "limit": limit,
        "offset": offset,
        "total": total,
        "counts": counts,
    }


@router.patch("/admin/claims/{claim_id}")
@router.post("/admin/claims/{claim_id}/review")
def decide_claim(
    claim_id: UUID,
    payload: ClaimDecision,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "You do not have access to this resource.")
    lifecycle_lock(session)
    claim = session.get(Claim, claim_id)
    if claim is None:
        raise AppError(404, "not_found", "Claim not found.")
    match = session.get(Match, claim.match_id)
    lock_items(session, [match.lost_id, match.found_id])
    session.refresh(claim)
    session.refresh(match)
    if claim.status != "pending":
        raise AppError(409, "lifecycle_conflict", "This claim has already been reviewed.")
    lost = session.get(Item, match.lost_id)
    found = session.get(Item, match.found_id)
    claim.reviewed_by = user.id
    claim.reviewed_at = utcnow()
    claim.review_note = payload.review_note if payload.review_note is not None else payload.note
    if payload.action == "approve":
        if (
            not current_match(match, lost, found)
            or lost.status != "active"
            or found.status != "active"
            or claim.claimant_id != lost.user_id
        ):
            raise AppError(409, "lifecycle_conflict", "This claim can no longer be approved.")
        claim.status = ClaimStatus.APPROVED.value
        lost.status = ItemStatus.RESERVED.value
        found.status = ItemStatus.RESERVED.value
        lost.revision += 1
        found.revision += 1
        others = session.scalars(
            select(Claim).where(
                Claim.match_id.in_(
                    select(Match.id).where(
                        or_(
                            Match.lost_id.in_([lost.id, found.id]),
                            Match.found_id.in_([lost.id, found.id]),
                        )
                    )
                ),
                Claim.id != claim.id,
                Claim.status == ClaimStatus.PENDING.value,
            )
        ).all()
        for other in others:
            other.status = ClaimStatus.REJECTED.value
            other.reviewed_by = user.id
            other.reviewed_at = utcnow()
            other.review_note = "Another claim involving this report was approved."
        invalidate(session, [lost.id, found.id], except_match=match.id)
        for item in (lost, found):
            item.match_pending = False
            item.embed_lease_token = None
        if match.notify_status != "sent":
            match.notify_status = "cancelled"
            match.notify_lease_token = None
    else:
        claim.status = ClaimStatus.REJECTED.value
    session.commit()
    return {"id": str(claim.id), "status": claim.status}


@router.post("/admin/items/{item_id}/returned")
def mark_returned(
    item_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "You do not have access to this resource.")
    lifecycle_lock(session)
    item = session.get(Item, item_id)
    if item is None:
        raise AppError(404, "not_found", "Item not found.")
    claim = session.scalar(
        select(Claim)
        .join(Match, Claim.match_id == Match.id)
        .where(Claim.status == "approved", or_(Match.lost_id == item.id, Match.found_id == item.id))
    )
    if claim is None:
        raise AppError(409, "lifecycle_conflict", "An approved claim is required.")
    return confirm_return(claim.id, user, session)


@router.post("/admin/claims/{claim_id}/return")
def confirm_return(
    claim_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    if user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "You do not have access to this resource.")
    lifecycle_lock(session)
    claim = session.get(Claim, claim_id)
    if claim is None:
        raise AppError(404, "not_found", "Claim not found.")
    match = session.get(Match, claim.match_id)
    items = lock_items(session, [match.lost_id, match.found_id])
    session.refresh(claim)
    if claim.returned_at is None:
        if claim.status != "approved" or any(item.status != "reserved" for item in items):
            raise AppError(409, "lifecycle_conflict", "An approved, reserved pair is required.")
        for item in items:
            item.status = "returned"
            item.revision += 1
        claim.returned_at = utcnow()
        claim.returned_by = user.id
        session.commit()
    return {
        "id": str(claim.id),
        "status": claim.status,
        "returned_at": claim.returned_at,
        "returned_by": str(claim.returned_by),
        "lost_id": str(match.lost_id),
        "found_id": str(match.found_id),
    }


def match_detail(match, request, user, session):
    lost, found = session.get(Item, match.lost_id), session.get(Item, match.found_id)
    if not current_match(match, lost, found) or not _participant(match, lost, found, user):
        raise AppError(404, "not_found", "Match not found.")
    existing = session.scalar(
        select(Claim.id).where(Claim.match_id == match.id, Claim.claimant_id == user.id)
    )
    return {
        "id": str(match.id),
        "lost": _public(lost, request.app.state.storage),
        "found": _public(found, request.app.state.storage),
        "score": match.score,
        "text_sim": match.text_sim,
        "image_sim": match.image_sim,
        "attr_score": match.attr_score,
        "scoring_version": match.scoring_version,
        "evidence": match.evidence,
        "threshold": (match.evidence or {}).get("threshold"),
        "can_claim": user.id == lost.user_id
        and lost.status == found.status == "active"
        and existing is None,
    }


@router.get("/matches/{match_id}")
def get_match(
    match_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    match = session.get(Match, match_id)
    if match is None:
        raise AppError(404, "not_found", "Match not found.")
    return match_detail(match, request, user, session)


@router.get("/matches")
def list_matches(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    own = select(Item.id).where(Item.user_id == user.id)
    query = visible_matches().where(or_(Match.lost_id.in_(own), Match.found_id.in_(own)))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(Match.score.desc(), Match.id).limit(limit).offset(offset))
    return {
        "items": [match_detail(row, request, user, session) for row in rows],
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.post("/claims", status_code=201)
def create_claim(
    payload: ClaimCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return submit_claim(payload.match_id, payload, request, user, session)


@router.get("/claims")
def list_claims(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    query = select(Claim).where(Claim.claimant_id == user.id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(Claim.created_at.desc(), Claim.id).limit(limit).offset(offset)
    )
    return {
        "items": [
            {
                "id": str(c.id),
                "match_id": str(c.match_id),
                "answer": c.answer,
                "status": c.status,
                "review_note": c.review_note,
                "returned_at": c.returned_at,
                "created_at": c.created_at,
            }
            for c in rows
        ],
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.get("/admin/items")
def admin_items(
    request: Request,
    status: ItemStatus | None = None,
    type: str | None = None,
    category: str | None = None,
    embed_status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "You do not have access to this resource.")
    query = select(Item)
    for name, value in {
        "status": status,
        "type": type,
        "category": category,
        "embed_status": embed_status,
    }.items():
        if value is not None:
            query = query.where(getattr(Item, name) == value)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(Item.created_at.desc(), Item.id).limit(limit).offset(offset)
    )
    return {
        "items": [_serialize(row, request.app.state.storage, True) for row in rows],
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.get("/admin/matches")
def admin_matches(
    notify_status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "You do not have access to this resource.")
    query = select(Match)
    if notify_status:
        query = query.where(Match.notify_status == notify_status)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(Match.created_at.desc(), Match.id).limit(limit).offset(offset)
    )
    items = []
    for match in rows:
        lost, found = session.get(Item, match.lost_id), session.get(Item, match.found_id)
        items.append(
            {
                "id": str(match.id),
                "score": match.score,
                "notify_status": match.notify_status,
                "notify_last_error_code": match.notify_last_error_code,
                "notified_at": match.notified_at,
                "lost_title": lost.title,
                "found_title": found.title,
            }
        )
    return {"items": items, "limit": limit, "offset": offset, "total": total}


@router.post("/admin/items/{item_id}/retry")
def retry_item(
    item_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    if user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "You do not have access to this resource.")
    lifecycle_lock(session)
    rows = lock_items(session, [item_id])
    if not rows:
        raise AppError(404, "not_found", "Item not found.")
    item = rows[0]
    if item.status != "active" or item.embed_status != "failed" or not item.semantic_consent:
        raise AppError(409, "lifecycle_conflict", "Only failed active work can be retried.")
    item.embed_status, item.embed_attempts = "pending", 0
    item.embed_next_attempt_at = item.embed_lease_until = item.embed_lease_token = None
    item.embed_last_error_code = None
    session.commit()
    return {"id": str(item.id), "embed_status": item.embed_status}


@router.post("/admin/matches/{match_id}/retry")
def retry_match(
    match_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    if user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "You do not have access to this resource.")
    lifecycle_lock(session)
    match = session.get(Match, match_id)
    if match is None:
        raise AppError(404, "not_found", "Match not found.")
    lock_items(session, [match.lost_id, match.found_id])
    session.refresh(match)
    lost, found = session.get(Item, match.lost_id), session.get(Item, match.found_id)
    if (
        not current_match(match, lost, found)
        or lost.status != "active"
        or found.status != "active"
        or match.notify_status != "failed"
        or match.notified_at
    ):
        raise AppError(409, "lifecycle_conflict", "Only failed valid notifications can be retried.")
    match.notify_status, match.notify_attempts = "pending", 0
    match.notify_next_attempt_at = match.notify_lease_until = match.notify_lease_token = None
    match.notify_last_error_code = None
    session.commit()
    return {"id": str(match.id), "notify_status": match.notify_status}
