import threading
import time
from collections import deque

from backend.app.errors import AppError


class Limiter:
    def __init__(self):
        self._buckets: dict[str, tuple[deque, float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float, *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            expired = [name for name, (_, expiry) in self._buckets.items() if expiry <= now]
            for name in expired:
                del self._buckets[name]
            if key not in self._buckets and len(self._buckets) >= 10000:
                raise AppError(429, "rate_limited", "Please try again later.")
            events, _ = self._buckets.get(key, (deque(), now + window))
            while events and events[0] <= now - window:
                events.popleft()
            if len(events) >= limit:
                raise AppError(429, "rate_limited", "Too many attempts. Please try again later.")
            events.append(now)
            self._buckets[key] = events, now + window
