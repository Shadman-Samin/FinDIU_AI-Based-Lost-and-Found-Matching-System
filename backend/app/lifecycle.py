from sqlalchemy import or_, select
from sqlalchemy.orm import aliased

from backend.app.errors import AppError
from backend.app.models import Claim, Item, Match, utcnow


def lock_items(session, ids):
    return session.scalars(
        select(Item)
        .where(Item.id.in_(ids))
        .order_by(Item.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()


def current_match(match, lost, found):
    return (
        match.valid
        and lost.type == "lost"
        and found.type == "found"
        and lost.user_id != found.user_id
        and match.lost_revision == lost.content_revision
        and match.found_revision == found.content_revision
    )


def visible_matches():
    lost, found = aliased(Item), aliased(Item)
    return (
        select(Match)
        .join(lost, Match.lost_id == lost.id)
        .join(found, Match.found_id == found.id)
        .where(
            Match.valid.is_(True),
            Match.lost_revision == lost.content_revision,
            Match.found_revision == found.content_revision,
            lost.user_id != found.user_id,
            lost.type == "lost",
            found.type == "found",
        )
    )


def editable(session, item):
    pending = session.scalar(
        select(Claim.id)
        .join(Match, Claim.match_id == Match.id)
        .where(Claim.status == "pending", or_(Match.lost_id == item.id, Match.found_id == item.id))
        .limit(1)
    )
    if item.status != "active" or pending:
        raise AppError(409, "lifecycle_conflict", "This report cannot be changed now.")


def invalidate(session, ids, except_match=None):
    query = select(Match).where(or_(Match.lost_id.in_(ids), Match.found_id.in_(ids)))
    if except_match:
        query = query.where(Match.id != except_match)
    for match in session.scalars(query):
        match.valid = False
        if match.notify_status != "sent":
            match.notify_status = "cancelled"
        match.notify_lease_token = None
        match.notify_lease_until = None
        match.updated_at = utcnow()
