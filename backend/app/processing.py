"""Durable embedding, matching and notification work driven by /internal/tick.

Every step is claimed with row locks (SKIP LOCKED) and short leases so a slow
provider call cannot hold the whole queue. Failures are recorded and retried
with backoff instead of being lost.
"""

from datetime import timedelta
from random import uniform
from time import monotonic
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.db import lifecycle_lock
from backend.app.errors import ServiceFailure
from backend.app.image_features import FEATURE_VERSION, image_features
from backend.app.image_utils import prepare_image
from backend.app.lifecycle import current_match, lock_items
from backend.app.matcher import SCORING_VERSION, score_pair
from backend.app.models import (
    Claim,
    Item,
    ItemStatus,
    Match,
    NotifyStatus,
    User,
    WorkStatus,
    utcnow,
)
from backend.app.providers import validate_vector

LEASE = timedelta(seconds=120)
RETRY_MINUTES = (1, 5, 15, 60, 240)
MAX_ATTEMPTS = 6


def _value(member) -> str:
    return getattr(member, "value", member)


def _embedding_text(item: Item) -> str:
    parts = [
        item.title,
        item.description,
        item.category,
        item.color,
        item.brand or "",
        item.location,
    ]
    return " | ".join(part for part in parts if part)


def _row(item: Item) -> dict:
    return {
        "title": item.title,
        "description": item.description,
        "image_features": item.image_features if item.feature_version == FEATURE_VERSION else None,
        "embedding_model": item.embedding_model,
        "embedding_dimensions": item.embedding_dimensions,
        "embedded_revision": item.embedded_revision,
        "content_revision": item.content_revision,
        "text_embedding": item.text_embedding,
        "image_embedding": item.image_embedding,
        "color": item.color,
        "brand": item.brand,
        "location": item.location,
        "event_date": item.event_date,
    }


def _embedding_authorized(session, item_id, token, revision):
    authorized = (
        session.scalar(
            select(Item.id).where(
                Item.id == item_id,
                Item.semantic_consent.is_(True),
                Item.status == "active",
                Item.content_revision == revision,
                Item.embed_lease_token == token,
                Item.embed_lease_until > utcnow(),
            )
        )
        is not None
    )
    session.rollback()
    return authorized


def process_embeddings(session: Session, settings, embedder, storage, limit=5, budget=None):
    if embedder is None:
        return 0
    if budget is not None and monotonic() + 10 > budget:
        return 0
    now = utcnow()
    due = (Item.embed_next_attempt_at.is_(None)) | (Item.embed_next_attempt_at <= now)
    condition = ((Item.embed_status == WorkStatus.PENDING.value) & due) | (
        (Item.embed_status == WorkStatus.PROCESSING.value) & (Item.embed_lease_until < now)
    )
    token = uuid4()
    claimed = (
        select(Item.id)
        .where(condition, Item.status == "active", Item.semantic_consent.is_(True))
        .order_by(Item.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    ids = session.scalars(
        update(Item)
        .where(Item.id.in_(claimed))
        .values(
            embed_status=WorkStatus.PROCESSING.value,
            embed_attempts=Item.embed_attempts + 1,
            embed_lease_token=token,
            embed_lease_until=now + LEASE,
        )
        .returning(Item.id)
    ).all()
    session.commit()

    processed = 0
    for item_id in ids:
        if budget is not None and monotonic() + 10 > budget:
            break
        item = session.get(Item, item_id)
        if item is None or item.embed_lease_token != token:
            continue
        revision = item.content_revision
        text_input, image_path = _embedding_text(item), item.image_path
        reusable = (
            item.embedded_revision == revision
            and item.embedding_model == embedder.model
            and item.embedding_dimensions == embedder.dimensions
        )
        text_vector = item.text_embedding if reusable else None
        image_vector = item.image_embedding if reusable else None
        attempts = item.embed_attempts
        session.rollback()
        error = None
        try:
            if text_vector is None:
                if not _embedding_authorized(session, item_id, token, revision):
                    continue
                text_vector = validate_vector(embedder.embed_text(text_input), embedder.dimensions)
            if image_path and image_vector is None:
                if not _embedding_authorized(session, item_id, token, revision):
                    continue
                if budget is not None and monotonic() + 10 > budget:
                    raise ServiceFailure("processing_budget", retryable=True)
                image_bytes = storage.read_bytes(image_path)
                if not _embedding_authorized(session, item_id, token, revision):
                    continue
                if budget is not None and monotonic() + 10 > budget:
                    raise ServiceFailure("processing_budget", retryable=True)
                image_vector = validate_vector(
                    embedder.embed_image(image_bytes), embedder.dimensions
                )
        except ServiceFailure as failure:
            error = failure
        rows = lock_items(session, [item_id])
        item = rows[0] if rows else None
        if (
            item is None
            or item.embed_lease_token != token
            or item.content_revision != revision
            or item.embed_lease_until <= utcnow()
            or item.status != "active"
            or not item.semantic_consent
        ):
            session.rollback()
            continue
        if text_vector is not None:
            item.text_embedding, item.image_embedding = text_vector, image_vector
            item.embedding_model, item.embedding_dimensions = embedder.model, embedder.dimensions
            item.embedded_revision = revision
            item.match_pending = True
        item.embed_status = "ready"
        item.embed_last_error_code = item.embed_next_attempt_at = None
        if error:
            item.embed_last_error_code = error.code
            if error.retryable and attempts < MAX_ATTEMPTS:
                delay = RETRY_MINUTES[min(attempts, len(RETRY_MINUTES)) - 1] * 60
                item.embed_status = WorkStatus.PENDING.value
                item.embed_next_attempt_at = utcnow() + timedelta(
                    seconds=max(delay, error.retry_after or 0) + uniform(0, 10)
                )
            else:
                item.embed_status = WorkStatus.FAILED.value
        item.embed_lease_token = None
        item.embed_lease_until = None
        session.commit()
        processed += 1
    return processed


def _candidate_filter(item: Item, settings):
    window = timedelta(days=settings.date_window_days)
    opposite = "found" if _value(item.type) == "lost" else "lost"
    return (
        Item.id != item.id,
        Item.type == opposite,
        Item.status == ItemStatus.ACTIVE.value,
        Item.user_id != item.user_id,
        Item.category == item.category,
        Item.event_date.between(item.event_date, item.event_date + window)
        if item.type == "lost"
        else Item.event_date.between(item.event_date - window, item.event_date),
    )


def match_item(session: Session, item: Item, settings) -> int:
    if item.status != "active":
        return 0
    candidates = session.scalars(select(Item).where(*_candidate_filter(item, settings))).all()
    created = 0
    for other in candidates:
        first, second = (item, other) if _value(item.type) == "lost" else (other, item)
        existing = session.scalar(
            select(Match).where(Match.lost_id == first.id, Match.found_id == second.id)
        )
        if (
            existing is not None
            and session.scalar(select(Claim.id).where(Claim.match_id == existing.id).limit(1))
            is not None
        ):
            continue
        scores = score_pair(
            _row(first), _row(second), settings.date_window_days, mode=settings.matching_mode
        )
        scores["evidence"]["threshold"] = settings.match_threshold
        scores["evidence"]["date_window_days"] = settings.date_window_days
        valid = scores["score"] >= settings.match_threshold
        if existing is None:
            if not valid:
                continue
            session.add(
                Match(
                    lost_id=first.id,
                    found_id=second.id,
                    lost_revision=first.content_revision,
                    found_revision=second.content_revision,
                    text_sim=scores["text_sim"],
                    image_sim=scores["image_sim"],
                    attr_score=scores["attr_score"],
                    score=scores["score"],
                    scoring_version=SCORING_VERSION,
                    evidence=scores["evidence"],
                    valid=True,
                    notification_key=f"{first.id}:{second.id}",
                )
            )
            created += 1
        else:
            existing.lost_revision = first.content_revision
            existing.found_revision = second.content_revision
            existing.text_sim = scores["text_sim"]
            existing.image_sim = scores["image_sim"]
            existing.attr_score = scores["attr_score"]
            existing.score = scores["score"]
            existing.scoring_version = SCORING_VERSION
            existing.evidence = scores["evidence"]
            existing.valid = valid
            if not valid and existing.notify_status != "sent":
                existing.notify_status = NotifyStatus.CANCELLED.value
                existing.notify_lease_token = existing.notify_lease_until = None
            if valid and existing.notify_status == "cancelled" and existing.notified_at is None:
                existing.notify_status = "pending"
                existing.notify_attempts = 0
                existing.notify_next_attempt_at = existing.notify_last_error_code = None
    return created


def process_matches(session: Session, settings, limit=5, budget=None) -> int:
    if budget is not None and monotonic() > budget:
        return 0
    # Serialize the small, entirely local scan with lifecycle writes. No network calls here.
    lifecycle_lock(session)
    # Freeze candidate vectors too: an image retry may otherwise change a score mid-scan.
    session.scalars(
        select(Item)
        .where(Item.status == "active")
        .order_by(Item.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    claimed = (
        select(Item.id)
        .where(
            Item.match_pending.is_(True),
            Item.status == "active",
        )
        .order_by(Item.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    ids = session.scalars(claimed).all()

    created = 0
    for item_id in ids:
        if budget is not None and monotonic() > budget:
            break
        item = session.get(Item, item_id)
        if item is None:
            continue
        try:
            created += match_item(session, item, settings)
            item.match_pending = False
        except Exception:
            session.rollback()
            raise
    session.commit()
    return created


def backfill_features(session: Session, storage, limit=100) -> dict:
    rows = session.execute(
        select(Item.id, Item.content_revision, Item.image_path)
        .where(
            Item.status == "active",
            (Item.feature_version != FEATURE_VERSION)
            | (Item.image_path.is_not(None) & Item.image_features.is_(None)),
        )
        .order_by(Item.created_at, Item.id)
        .limit(limit)
    ).all()
    session.rollback()
    result = {"processed": 0, "failed": 0}
    for item_id, revision, path in rows:
        try:
            features = image_features(prepare_image(storage.read_bytes(path))) if path else None
        except ServiceFailure:
            result["failed"] += 1
            continue
        items = lock_items(session, [item_id])
        item = items[0] if items else None
        if (
            item is None
            or item.status != "active"
            or item.content_revision != revision
            or item.image_path != path
        ):
            session.rollback()
            continue
        item.image_features = features
        item.feature_version = FEATURE_VERSION
        item.match_pending = True
        session.commit()
        result["processed"] += 1
    return result


def process_notifications(session: Session, settings, notifier, limit=10, budget=None) -> int:
    if notifier is None or (budget is not None and monotonic() + 10 > budget):
        return 0
    now = utcnow()
    due = (Match.notify_next_attempt_at.is_(None)) | (Match.notify_next_attempt_at <= now)
    condition = ((Match.notify_status == NotifyStatus.PENDING.value) & due) | (
        (Match.notify_status == NotifyStatus.PROCESSING.value) & (Match.notify_lease_until < now)
    )
    token = uuid4()
    claimed = (
        select(Match.id)
        .where(condition, Match.valid.is_(True))
        .order_by(Match.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    ids = session.scalars(
        update(Match)
        .where(Match.id.in_(claimed))
        .values(
            notify_status=NotifyStatus.PROCESSING.value,
            notify_attempts=Match.notify_attempts + 1,
            notify_lease_token=token,
            notify_lease_until=now + LEASE,
        )
        .returning(Match.id)
    ).all()
    session.commit()

    sent = 0
    for match_id in ids:
        if budget is not None and monotonic() + 10 > budget:
            break
        match = session.get(Match, match_id)
        if match is None or match.notify_lease_token != token:
            continue
        lost = session.get(Item, match.lost_id)
        found = session.get(Item, match.found_id)
        owner = session.get(User, lost.user_id) if lost else None
        if (
            lost is None
            or found is None
            or owner is None
            or not current_match(match, lost, found)
            or lost.status != "active"
            or found.status != "active"
        ):
            match.notify_status = "cancelled"
            match.notify_lease_token = match.notify_lease_until = None
            session.commit()
            continue
        email, name, locale = owner.email, owner.name, owner.locale
        attempts = match.notify_attempts
        # Detach public snapshots before ending the read transaction.
        session.expunge(lost)
        session.expunge(found)
        session.rollback()
        error = None
        try:
            notifier.send_match(email, name, lost, found, str(match_id), locale=locale)
        except ServiceFailure as failure:
            error = failure
        match = session.scalar(
            select(Match)
            .where(Match.id == match_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            match.notify_lease_token != token
            or match.notify_lease_until <= utcnow()
            or not match.valid
        ):
            session.rollback()
            continue
        if error:
            match.notify_last_error_code = error.code
            if error.retryable and attempts < MAX_ATTEMPTS:
                delay = RETRY_MINUTES[min(attempts, len(RETRY_MINUTES)) - 1] * 60
                match.notify_status = "pending"
                match.notify_next_attempt_at = utcnow() + timedelta(
                    seconds=max(delay, error.retry_after or 0) + uniform(0, 10)
                )
            else:
                match.notify_status = "failed"
        else:
            match.notify_status = "sent"
            match.notified_at = utcnow()
            match.notify_last_error_code = None
            sent += 1
        match.notify_lease_token = None
        match.notify_lease_until = None
        session.commit()
    return sent


def run_tick(session: Session, settings, embedder, storage, notifier, budget_seconds=45) -> dict:
    budget = monotonic() + budget_seconds
    # Local matches are committed before any optional provider can consume the budget.
    created = process_matches(session, settings, 5, budget)
    embedded = process_embeddings(session, settings, embedder, storage, 5, budget)
    if embedded:
        created += process_matches(session, settings, 5, budget)
    return {
        "embedded": embedded,
        "matches_created": created,
        "notifications_sent": process_notifications(session, settings, notifier, 10, budget),
    }
