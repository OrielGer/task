"""Lightweight in-memory fixed-window rate limiter.

Adequate for development and single-process deployments. For multi-process /
multi-node production, back this with Redis (REDIS_URL is already configured).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

from app.config import get_settings


class RateLimiter:
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


limiter = RateLimiter()
