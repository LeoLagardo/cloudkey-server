import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """
    High-performance in-memory sliding-window rate limiter for FastAPI routes.
    Tracks client request timestamps per (route_key, client_ip).
    """

    def __init__(self):
        # Key: f"{route_tag}:{client_ip}" -> List[float] of request timestamps
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    def check(self, request: Request, key: str, max_requests: int, window_seconds: int = 60) -> None:
        client_ip = self._get_client_ip(request)
        cache_key = f"{key}:{client_ip}"
        now = time.time()
        window_start = now - window_seconds

        # Clean old timestamps
        history = self._requests[cache_key]
        self._requests[cache_key] = [ts for ts in history if ts > window_start]

        if len(self._requests[cache_key]) >= max_requests:
            retry_after = int(window_seconds - (now - self._requests[cache_key][0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds}s.",
                headers={"Retry-After": str(max(1, retry_after))},
            )

        self._requests[cache_key].append(now)


rate_limiter = SlidingWindowRateLimiter()


def rate_limit(key: str, max_requests: int = 60, window_seconds: int = 60):
    """
    FastAPI dependency factory for rate limiting.
    Usage:
        @router.get("/search", dependencies=[Depends(rate_limit("public_search", 60, 60))])
    """
    async def _dependency(request: Request):
        rate_limiter.check(request, key=key, max_requests=max_requests, window_seconds=window_seconds)

    return _dependency

