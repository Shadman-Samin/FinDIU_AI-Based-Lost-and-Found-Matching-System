from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(repr=False)
    jwt_secret: SecretStr
    jwt_issuer: str = "findiu"
    jwt_audience: str = "findiu-web"
    allowed_origins: list[str] = ["http://localhost:5500"]
    frontend_url: str = "http://localhost:5500"
    internal_tick_token: SecretStr = SecretStr("")
    supabase_url: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")
    storage_bucket: str = "findiu-images"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_embedding_model: str = "gemini-embedding-2"
    matching_mode: Literal["local", "hybrid"] = "local"
    embedding_provider: Literal["gemini", "local"] = "gemini"
    storage_provider: Literal["supabase", "local"] = "supabase"
    embedding_dimensions: int = Field(default=768, ge=128, le=3072)
    brevo_api_key: SecretStr = SecretStr("")
    brevo_sender_email: str = ""
    match_threshold: float = Field(default=0.75, ge=0, le=1)
    date_window_days: int = Field(default=30, ge=1, le=365)
    public_base_url: str = "http://localhost:8000"
    upload_dir: str = "var/uploads"
    consent_version: str = "2026-11-19-local-hybrid"
    login_limit: int = 5
    registration_limit: int = 3
    report_limit: int = 10
    claim_limit: int = 10

    @property
    def semantic_enabled(self) -> bool:
        return (
            self.matching_mode == "hybrid"
            and self.embedding_provider == "gemini"
            and bool(self.gemini_api_key.get_secret_value())
        )

    @field_validator("jwt_secret")
    @classmethod
    def secure_signing_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        return value

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: str) -> str:
        from sqlalchemy.engine import make_url

        if make_url(value).get_backend_name() != "postgresql":
            raise ValueError("DATABASE_URL must point to PostgreSQL")
        return value
