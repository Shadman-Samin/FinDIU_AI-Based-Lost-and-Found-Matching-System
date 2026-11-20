import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class ItemType(str, enum.Enum):
    LOST = "lost"
    FOUND = "found"


class ItemStatus(str, enum.Enum):
    ACTIVE = "active"
    RESERVED = "reserved"
    RETURNED = "returned"
    ARCHIVED = "archived"


class WorkStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class NotifyStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ClaimStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(Timestamped, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        CheckConstraint("locale IN ('en', 'bn')", name="ck_users_locale"),
        CheckConstraint("email = lower(trim(email))", name="ck_users_email_normalized"),
        {"schema": "findiu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[Role] = mapped_column(String(16), default=Role.USER, nullable=False)
    locale: Mapped[str] = mapped_column(String(2), default="en", nullable=False)
    items: Mapped[list["Item"]] = relationship(back_populates="owner")


class Item(Timestamped, Base):
    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint("type IN ('lost', 'found')", name="ck_items_type"),
        CheckConstraint(
            "status IN ('active', 'reserved', 'returned', 'archived')", name="ck_items_status"
        ),
        CheckConstraint("revision >= 1 AND content_revision >= 1", name="ck_items_revisions"),
        CheckConstraint(
            "embed_status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_items_embed_status",
        ),
        CheckConstraint("embed_attempts >= 0", name="ck_items_attempts"),
        CheckConstraint("feature_version >= 0", name="ck_items_feature_version"),
        Index("ix_items_eligibility", "status", "type", "category", "event_date"),
        Index("ix_items_due", "embed_status", "embed_next_attempt_at", "embed_lease_until"),
        {"schema": "findiu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[ItemType] = mapped_column(String(8), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findiu.users.id"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    color: Mapped[str] = mapped_column(String(32), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(String(32), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    private_detail: Mapped[str] = mapped_column(String(1000), nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(512))
    image_features: Mapped[dict | None] = mapped_column(JSONB)
    feature_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="0", nullable=False
    )
    status: Mapped[ItemStatus] = mapped_column(
        String(16), default=ItemStatus.ACTIVE, nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    embedded_revision: Mapped[int | None] = mapped_column(Integer)
    text_embedding: Mapped[list[float] | None] = mapped_column(JSONB)
    image_embedding: Mapped[list[float] | None] = mapped_column(JSONB)
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    embed_status: Mapped[WorkStatus] = mapped_column(
        String(16), default=WorkStatus.PENDING, nullable=False, index=True
    )
    embed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embed_next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embed_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embed_lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    embed_last_error_code: Mapped[str | None] = mapped_column(String(80))
    match_pending: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    semantic_consent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    owner: Mapped[User] = relationship(back_populates="items")


class Match(Timestamped, Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("lost_id", "found_id", name="uq_matches_pair"),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_matches_score"),
        CheckConstraint(
            "text_sim BETWEEN -1.000000001 AND 1.000000001 AND (image_sim IS NULL OR image_sim BETWEEN -1.000000001 AND 1.000000001) AND attr_score BETWEEN 0 AND 1.000000001",
            name="ck_matches_components",
        ),
        CheckConstraint(
            "notify_status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')",
            name="ck_matches_notify_status",
        ),
        CheckConstraint("notify_attempts >= 0", name="ck_matches_attempts"),
        CheckConstraint("lost_id <> found_id", name="ck_matches_distinct_items"),
        Index("ix_matches_due", "notify_status", "notify_next_attempt_at", "notify_lease_until"),
        {"schema": "findiu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lost_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findiu.items.id"), nullable=False, index=True
    )
    found_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findiu.items.id"), nullable=False, index=True
    )
    lost_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    found_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    text_sim: Mapped[float] = mapped_column(nullable=False)
    image_sim: Mapped[float | None] = mapped_column()
    attr_score: Mapped[float] = mapped_column(nullable=False)
    score: Mapped[float] = mapped_column(nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSONB)
    valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    notify_status: Mapped[NotifyStatus] = mapped_column(
        String(16), default=NotifyStatus.PENDING, nullable=False
    )
    notify_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notify_next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notify_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notify_lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notify_last_error_code: Mapped[str | None] = mapped_column(String(80))
    notification_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Claim(Timestamped, Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("match_id", "claimant_id", name="uq_claims_match_claimant"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_claims_status"),
        {"schema": "findiu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findiu.matches.id"), nullable=False, index=True
    )
    claimant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findiu.users.id"), nullable=False, index=True
    )
    answer: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[ClaimStatus] = mapped_column(
        String(16), default=ClaimStatus.PENDING, nullable=False, index=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("findiu.users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(String(1000))
    returned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("findiu.users.id"))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
