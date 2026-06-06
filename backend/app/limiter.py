"""Simple in-memory rate limiter — no Redis, no external dependencies."""
import time
from collections import defaultdict
from fastapi import Request, HTTPException, status


class RateLimiter:
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls: dict = defaultdict(list)

    def __call__(self, request: Request):
        key = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window
        self._calls[key] = [t for t in self._calls[key] if t > window_start]
        if len(self._calls[key]) >= self.max_calls:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Te veel pogingen. Probeer later opnieuw.",
            )
        self._calls[key].append(now)


login_limiter = RateLimiter(max_calls=10, window_seconds=60)
