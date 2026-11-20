from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from backend.app.metadata import CATEGORIES, COLORS, LOCATIONS


class RegisterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)
    locale: Literal["en", "bn"] = "en"

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value


def item_public_fields() -> set[str]:
    return {
        "id",
        "type",
        "category",
        "color",
        "brand",
        "title",
        "description",
        "location",
        "event_date",
        "status",
        "created_at",
        "updated_at",
    }


def _vocabulary(value: str, vocabulary: dict, label: str) -> str:
    normalized = value.strip().lower().replace(" ", "-")
    if normalized not in vocabulary:
        raise ValueError(f"Choose a known {label}")
    return normalized


class ItemInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: str = Field(max_length=32)
    color: str = Field(max_length=32)
    brand: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    location: str = Field(max_length=32)
    event_date: date
    private_detail: str = Field(min_length=3, max_length=1000)

    @field_validator("category")
    @classmethod
    def known_category(cls, value: str) -> str:
        return _vocabulary(value, CATEGORIES, "category")

    @field_validator("color")
    @classmethod
    def known_color(cls, value: str) -> str:
        return _vocabulary(value, COLORS, "colour")

    @field_validator("location")
    @classmethod
    def known_location(cls, value: str) -> str:
        return _vocabulary(value, LOCATIONS, "campus area")

    @field_validator("title", "description", "private_detail")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value

    @field_validator("brand")
    @classmethod
    def trim_brand(cls, value: str | None) -> str | None:
        value = (value or "").strip().casefold()
        return value or None

    @field_validator("event_date")
    @classmethod
    def plausible_date(cls, value: date) -> date:
        today = datetime.now(ZoneInfo("Asia/Dhaka")).date()
        if value > today:
            raise ValueError("The date cannot be in the future")
        return value


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "archived"]
    expected_revision: int = Field(ge=1)


class ClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=10, max_length=1000)

    @field_validator("answer")
    @classmethod
    def trim_answer(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("Describe the private detail")
        return value


class ClaimDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=1000)
    review_note: str | None = Field(default=None, max_length=1000)


class ClaimCreate(ClaimInput):
    match_id: UUID
