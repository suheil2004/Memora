"""Local single-user authentication and lightweight abuse controls."""

from __future__ import annotations

import os
import secrets
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from fastapi import HTTPException


@dataclass(frozen=True, slots=True)
class LocalSecurityConfig:
    token: str
    user_id: str
    retrieval_limit: int = 60
    retrieval_window_seconds: int = 60
    import_limit: int = 10
    import_window_seconds: int = 600

    @classmethod
    def from_environment(cls) -> "LocalSecurityConfig":
        return cls(
            token=os.environ.get("MEMORA_LOCAL_TOKEN", ""),
            user_id=os.environ.get("MEMORA_USER_ID", "demo-user").strip(),
            retrieval_limit=_positive_int("MEMORA_RETRIEVAL_RATE_LIMIT", 60),
            retrieval_window_seconds=_positive_int("MEMORA_RETRIEVAL_RATE_WINDOW_SECONDS", 60),
            import_limit=_positive_int("MEMORA_IMPORT_RATE_LIMIT", 10),
            import_window_seconds=_positive_int("MEMORA_IMPORT_RATE_WINDOW_SECONDS", 600),
        )

    def validate(self) -> None:
        if len(self.token) < 32:
            raise HTTPException(status_code=503, detail="Memora local authentication is not configured")
        if not self.user_id:
            raise HTTPException(status_code=503, detail="Memora local user is not configured")

    def authenticate(self, authorization: str | None) -> str:
        self.validate()
        if authorization is None:
            raise _unauthorized()
        scheme, separator, credential = authorization.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not credential or " " in credential:
            raise _unauthorized()
        if not secrets.compare_digest(credential, self.token):
            raise _unauthorized()
        return self.user_id


class InMemoryRateLimiter:
    """Per-process fixed-window protection for the local single-user MVP."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True


def enforce_rate_limit(
    limiter: InMemoryRateLimiter,
    key: str,
    *,
    limit: int,
    window_seconds: int,
) -> None:
    if not limiter.allow(key, limit=limit, window_seconds=window_seconds):
        raise HTTPException(
            status_code=429,
            detail="Too many Memora requests. Wait briefly and try again.",
            headers={"Retry-After": str(window_seconds)},
        )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Memora authentication failed",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _positive_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value
