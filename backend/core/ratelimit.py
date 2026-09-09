"""Basic in-memory rate limiting for sensitive routes (auth + payments).

Sliding-window counter keyed by client IP + route bucket. This is deliberately
lightweight (single-instance, in-process) — enough to blunt brute-force logins
and welcome-bonus registration abuse. For multi-instance production, swap the
store for Redis.
"""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# bucket_prefix -> (max_requests, window_seconds)
RULES = {
    "/api/auth/login": (10, 60),
    "/api/auth/register": (5, 60),
    "/api/auth/otp": (10, 60),
    "/api/payments": (30, 60),
}

_hits: dict = defaultdict(deque)


def _rule_for(path: str):
    for prefix, rule in RULES.items():
        if path.startswith(prefix):
            return prefix, rule
    return None, None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        prefix, rule = _rule_for(path)
        if rule is None:
            return await call_next(request)

        max_req, window = rule
        client_ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                     or (request.client.host if request.client else "unknown"))
        key = f"{client_ip}:{prefix}"
        now = time.time()
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= max_req:
            retry = int(window - (now - q[0])) + 1
            return JSONResponse(
                {"detail": "Too many requests. Please slow down and try again shortly."},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        q.append(now)
        return await call_next(request)
