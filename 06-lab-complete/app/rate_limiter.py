"""Sliding window rate limiter — 10 req/min per API key bucket."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings

_windows: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str) -> None:
    now = time.time()
    window = _windows[key]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
            headers={"Retry-After": "60"},
        )
    window.append(now)
