import time
import asyncio
from collections import defaultdict
from typing import Dict, List, Optional
from fastapi import Request, HTTPException, status
from app.core.config import settings


class RateLimiterStorage:
    """
    In-memory rate limiter storage with timestamp tracking and window pruning.
    Thread-safe and async-compatible.
    """
    def __init__(self):
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_rate_limited(self, key: str, times: int, seconds: int) -> tuple[bool, int, int]:
        """
        Check if key exceeds `times` requests within `seconds` window.
        Returns tuple: (is_limited: bool, remaining_requests: int, retry_after_seconds: int)
        """
        async with self._lock:
            now = time.time()
            cutoff = now - seconds
            
            # Prune timestamps outside window
            timestamps = [ts for ts in self._requests[key] if ts > cutoff]
            self._requests[key] = timestamps

            if len(timestamps) >= times:
                oldest_in_window = timestamps[0]
                retry_after = max(1, int(oldest_in_window + seconds - now))
                remaining = 0
                return True, remaining, retry_after

            # Record current request
            timestamps.append(now)
            self._requests[key] = timestamps
            remaining = max(0, times - len(timestamps))
            return False, remaining, 0

    async def reset(self, key: Optional[str] = None):
        """Reset storage for a specific key or all keys."""
        async with self._lock:
            if key:
                self._requests.pop(key, None)
            else:
                self._requests.clear()


# Global storage instance
rate_limiter_storage = RateLimiterStorage()


class RateLimiter:
    """
    FastAPI dependency for endpoint Rate Limiting.
    Protects API endpoints against DDoS attacks and unauthorized AI token exhaustion.
    """
    def __init__(
        self,
        times: int = 10,
        seconds: int = 60,
        prefix: str = "api",
        enabled: Optional[bool] = None,
    ):
        self.times = times
        self.seconds = seconds
        self.prefix = prefix
        self.enabled = enabled if enabled is not None else getattr(settings, "RATE_LIMITING_ENABLED", True)

    async def __call__(self, request: Request):
        if not self.enabled:
            return

        # Determine identifier: Client IP or Authorization Bearer header hash / User identifier
        client_ip = request.client.host if request.client else "127.0.0.1"
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # Use auth token suffix to scope per user session
            user_id_part = auth_header[-16:]
            key = f"rl:{self.prefix}:{client_ip}:{user_id_part}"
        else:
            key = f"rl:{self.prefix}:{client_ip}"

        is_limited, remaining, retry_after = await rate_limiter_storage.is_rate_limited(
            key=key, times=self.times, seconds=self.seconds
        )

        if is_limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.times} requests per {self.seconds} seconds allowed. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(self.times), "X-RateLimit-Remaining": "0"},
            )


def reset_rate_limiter_storage():
    """Utility to reset rate limiter storage between unit tests."""
    asyncio.run(rate_limiter_storage.reset())
