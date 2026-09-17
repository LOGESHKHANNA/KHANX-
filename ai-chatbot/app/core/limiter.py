"""
KHANX API Rate Limiter
======================
Centralised slowapi limiter used across all routers.
Key strategy: per-IP for anonymous/guest endpoints;
               per-IP for authenticated endpoints as baseline
               (Supabase already locks out brute-force on auth side).

Limits applied:
  - Guest chat (stream + non-streaming): 20 req/min per IP
  - Authenticated chat stream:           30 req/min per IP
  - File upload:                         10 req/min per IP
  - Login endpoint:                       5 req/min per IP  (brute-force guard)
  - Signup endpoint:                     10 req/hour per IP
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from datetime import datetime, timezone

from app.core.config import settings
import logging

logger = logging.getLogger("khanx.limiter")

# Initialize Limiter with Redis storage backend if REDIS_URL is configured, with safe fallback to in-memory storage
limiter_storage_uri = settings.REDIS_URL.strip() if getattr(settings, "REDIS_URL", None) else None

try:
    if limiter_storage_uri:
        limiter = Limiter(key_func=get_remote_address, storage_uri=limiter_storage_uri)
        logger.info(f"Rate Limiter initialized with Redis storage backend ({limiter_storage_uri})")
    else:
        limiter = Limiter(key_func=get_remote_address)
        logger.info("Rate Limiter initialized with in-memory storage backend")
except Exception as err:
    logger.warning(f"Failed to initialize Redis rate limiter storage ({err}). Falling back to in-memory storage.")
    limiter = Limiter(key_func=get_remote_address)



def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom 429 handler that returns a clear, user-friendly JSON message.
    Differentiates between auth endpoints and general API rate limits.
    """
    path = request.url.path.lower()
    is_auth = "/auth/login" in path or "/auth/signup" in path

    if is_auth:
        message = "Too many login attempts. Please try again later."
    else:
        message = "Too many requests. Please slow down and try again."

    # Parse retry-after from the slowapi exception detail (e.g. "5 per 1 minute")
    retry_after = 60  # default fallback
    detail_str = str(getattr(exc, "detail", ""))
    if "minute" in detail_str:
        retry_after = 60
    elif "hour" in detail_str:
        retry_after = 3600

    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": message,
            "detail": detail_str,
            "retry_after": retry_after,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Retry-After": str(retry_after)},
    )
