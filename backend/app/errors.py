import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from fastapi import Request
from fastapi.responses import JSONResponse


def retry_after_seconds(value):
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0, min(seconds, 86400)) if math.isfinite(seconds) else None


class ServiceFailure(Exception):
    def __init__(self, code: str, retryable: bool = False, retry_after: float | None = None):
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after
        super().__init__(code)


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, fields=None):
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields
        super().__init__(code)


def app_error_handler(request: Request, error: AppError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if error.status == 401 else None
    body = {"code": error.code, "message": error.message}
    if error.fields is not None:
        body["fields"] = error.fields
    return JSONResponse(
        status_code=error.status,
        content={"error": body},
        headers=headers,
    )
