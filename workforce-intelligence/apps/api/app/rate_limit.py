"""Rate limiting with a Redis backend and an in-memory fallback.

If ``REDIS_URL`` is set and reachable, a shared fixed-window counter is kept in
Redis (correct across processes/nodes). Otherwise, or on any Redis error, it
falls back to a per-process in-memory counter. Fail-open on backend errors so a
Redis outage never takes the API down.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

from app.config import get_settings


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))

    def allow(self, key: str) -> bool:
        s = get_settings()
        window = s.rate_limit_window_seconds
        limit = s.rate_limit_requests
        now = time.monotonic()
        with self._lock:
            count, window_start = self._buckets[key]
            if now - window_start >= window:
                self._buckets[key] = (1, now)
                return True
            if count >= limit:
                return False
            self._buckets[key] = (count + 1, window_start)
            return True


class RedisRateLimiter:
    def __init__(self) -> None:
        self._fallback = InMemoryRateLimiter()
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        s = get_settings()
        if not s.redis_url:
            return
        try:
            import redis

            self._client = redis.Redis.from_url(s.redis_url, socket_timeout=0.25)
        except Exception:
            self._client = None

    def allow(self, key: str) -> bool:
        if self._client is None:
            return self._fallback.allow(key)
        s = get_settings()
        try:
            rkey = f"rl:{key}"
            count = self._client.incr(rkey)
            if count == 1:
                self._client.expire(rkey, s.rate_limit_window_seconds)
            return int(count) <= s.rate_limit_requests
        except Exception:
            # Fail open to the in-memory limiter on any Redis error.
            return self._fallback.allow(key)


def _build():
    return RedisRateLimiter() if get_settings().redis_url else InMemoryRateLimiter()


limiter = _build()
