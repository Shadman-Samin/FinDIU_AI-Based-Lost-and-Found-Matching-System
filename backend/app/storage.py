"""Private image storage with short-lived signed URLs.

Supabase Storage is used in deployment. When no Supabase credentials are
configured (local demo, automated tests) images are written to disk and served
through an HMAC-signed, expiring URL — the access model stays identical:
the bucket is private, URLs leak nothing and cannot be enumerated.
"""

import hashlib
import hmac
import re
import time
from pathlib import Path

import httpx

from backend.app.config import Settings
from backend.app.errors import AppError, ServiceFailure

SIGNED_URL_TTL = 300
KEY_PATTERN = re.compile(r"^[0-9a-f-]{36}/[0-9a-f]{32}\.jpg$")


class LocalStorage:
    def __init__(self, root: Path, secret: str, base_url: str):
        self.root = root
        self._secret = secret.encode()
        self.base_url = base_url.rstrip("/")

    def put(self, key: str, data: bytes) -> None:
        if not KEY_PATTERN.match(key):
            raise ValueError("Unsafe storage key")
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(target)

    def signed_url(self, key: str) -> str:
        expires = int(time.time()) + SIGNED_URL_TTL
        signature = self._sign(key, expires)
        return f"{self.base_url}/api/v1/media/{key}?expires={expires}&signature={signature}"

    def read(self, key: str, expires: int, signature: str) -> Path:
        if not KEY_PATTERN.match(key) or expires < time.time():
            raise AppError(404, "not_found", "Image not found.")
        if not hmac.compare_digest(self._sign(key, expires), signature):
            raise AppError(404, "not_found", "Image not found.")
        path = self.root / key
        if not path.is_file():
            raise AppError(404, "not_found", "Image not found.")
        return path

    def delete(self, key: str) -> None:
        try:
            (self.root / key).unlink(missing_ok=True)
        except OSError:
            # Cleanup is best effort; a committed replacement must remain successful.
            pass

    def read_bytes(self, key: str) -> bytes:
        if not KEY_PATTERN.match(key):
            raise ServiceFailure("image_missing")
        path = self.root / key
        if not path.is_file():
            raise ServiceFailure("image_missing")
        return path.read_bytes()

    def _sign(self, key: str, expires: int) -> str:
        return hmac.new(self._secret, f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()


class SupabaseStorage:
    def __init__(self, url: str, service_key: str, bucket: str):
        self.base = f"{url.rstrip('/')}/storage/v1"
        self.bucket = bucket
        self._headers = {"Authorization": f"Bearer {service_key}"}

    def put(self, key: str, data: bytes) -> None:
        try:
            response = httpx.post(
                f"{self.base}/object/{self.bucket}/{key}",
                content=data,
                headers={**self._headers, "Content-Type": "image/jpeg", "x-upsert": "false"},
                timeout=10,
            )
        except httpx.HTTPError:
            raise ServiceFailure("storage_unavailable", retryable=True) from None
        if response.status_code >= 400:
            raise ServiceFailure("storage_rejected", retryable=response.status_code >= 500)

    def signed_url(self, key: str) -> str:
        try:
            response = httpx.post(
                f"{self.base}/object/sign/{self.bucket}/{key}",
                json={"expiresIn": SIGNED_URL_TTL},
                headers=self._headers,
                timeout=10,
            )
            response.raise_for_status()
            return f"{self.base}{response.json()['signedURL']}"
        except (httpx.HTTPError, KeyError, ValueError):
            raise ServiceFailure("storage_unavailable", retryable=True) from None

    def delete(self, key: str) -> None:
        try:
            httpx.delete(
                f"{self.base}/object/{self.bucket}/{key}", headers=self._headers, timeout=10
            )
        except httpx.HTTPError:
            pass

    def read_bytes(self, key: str) -> bytes:
        try:
            response = httpx.get(
                f"{self.base}/object/{self.bucket}/{key}", headers=self._headers, timeout=10
            )
            response.raise_for_status()
        except httpx.HTTPError:
            raise ServiceFailure("image_missing") from None
        return response.content


def build_storage(settings: Settings):
    if settings.storage_provider == "supabase":
        if not settings.supabase_url or not settings.supabase_service_role_key.get_secret_value():
            raise ServiceFailure("storage_not_configured")
        return SupabaseStorage(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
            settings.storage_bucket,
        )
    return LocalStorage(
        Path(settings.upload_dir),
        settings.jwt_secret.get_secret_value(),
        settings.public_base_url,
    )
