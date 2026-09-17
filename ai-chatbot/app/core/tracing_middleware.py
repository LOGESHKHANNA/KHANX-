"""
Production Correlation-ID Request Tracing Middleware & Logging Context.

Assigns or preserves a unique `X-Correlation-ID` header for every HTTP request,
attaches it to request state and thread-local ContextVar, and exposes it in logs/responses.
"""
import uuid
import logging
from contextvars import ContextVar
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

HEADER_CORRELATION_ID = "X-Correlation-ID"

# Context Variable for storing Correlation ID per request task context
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id_ctx", default="")


def get_correlation_id() -> str:
    """Retrieve the correlation ID of the current request context."""
    return correlation_id_ctx.get() or ""


class CorrelationIDLogFilter(logging.Filter):
    """Logging filter that injects `correlation_id` into all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        cid = get_correlation_id()
        record.correlation_id = cid if cid else "-"
        return True


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware that preserves or assigns an `X-Correlation-ID` header for request tracing."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Check for incoming correlation ID in headers
        header_val = (
            request.headers.get("x-correlation-id")
            or request.headers.get("X-Correlation-ID")
            or request.headers.get("x-request-id")
        )

        # Preserve client-supplied correlation ID or generate a new UUIDv4
        correlation_id = header_val.strip() if header_val and header_val.strip() else str(uuid.uuid4())

        # Attach to request state & context variable
        request.state.correlation_id = correlation_id
        token = correlation_id_ctx.set(correlation_id)

        try:
            response = await call_next(request)
            # Ensure response header is populated
            response.headers[HEADER_CORRELATION_ID] = correlation_id
            return response
        finally:
            correlation_id_ctx.reset(token)
