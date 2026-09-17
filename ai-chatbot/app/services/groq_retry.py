"""
Groq API Reliability & Retry Service.

Provides exponential backoff retries using `tenacity` for temporary Groq API errors
(RateLimits 429, Timeouts, Network errors, 5xx Server errors), while excluding
permanent client errors (400 Bad Requests, 401 Auth errors, 403 Forbidden, 404 Not Found).
"""
import sys
import logging
from typing import Callable, Any, TypeVar
import groq
import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
    before_sleep_log,
)

logger = logging.getLogger("groq_retry")
T = TypeVar("T")

# Permanent client error types that MUST NOT be retried
PERMANENT_GROQ_ERRORS = (
    groq.BadRequestError,
    groq.AuthenticationError,
    groq.PermissionDeniedError,
    groq.NotFoundError,
    groq.UnprocessableEntityError,
)

# Temporary error types that SHOULD be retried
TEMPORARY_GROQ_ERRORS = (
    groq.RateLimitError,
    groq.APITimeoutError,
    groq.APIConnectionError,
    groq.InternalServerError,
    httpx.TimeoutException,
    httpx.NetworkError,
    ConnectionError,
    TimeoutError,
)


def is_retryable_groq_error(exc: Exception) -> bool:
    """Predicate function determining if a Groq API exception is transient/retryable.
    
    Returns:
        True if exception is temporary (rate limit, timeout, 5xx server error, connection drop).
        False if exception is permanent (invalid credentials, bad payload format, 4xx client error).
    """
    if isinstance(exc, PERMANENT_GROQ_ERRORS):
        return False
    if isinstance(exc, TEMPORARY_GROQ_ERRORS):
        return True
    if isinstance(exc, groq.APIStatusError):
        status = getattr(exc, "status_code", 0)
        if status == 429 or status >= 500:
            return True
        if 400 <= status < 500:
            return False
    return False


def _log_retry_failure(retry_state):
    """Log retry attempts for diagnostic tracking."""
    exc = retry_state.outcome.exception()
    attempt = retry_state.attempt_number
    sec = retry_state.next_action.sleep
    logger.warning(
        f"[Groq Retry] Temporary Groq API error on attempt {attempt}/3 (retrying in {sec:.2f}s): {exc}"
    )


# Tenacity decorator configured for 3 retry attempts with exponential backoff & random jitter
groq_retry_decorator = retry(
    retry=retry_if_exception(is_retryable_groq_error),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(min=1.0, max=10.0),
    before_sleep=_log_retry_failure,
    reraise=True,
)


def call_groq_with_retry(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute a Groq API synchronous function call with tenacity exponential backoff retries.
    
    Usage:
        completion = call_groq_with_retry(
            client.chat.completions.create,
            messages=messages,
            model="groq/compound-mini"
        )
    """
    @groq_retry_decorator
    def _wrapped():
        return func(*args, **kwargs)

    return _wrapped()


async def call_groq_async_with_retry(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Execute a Groq API asynchronous function call with tenacity exponential backoff retries."""
    
    @retry(
        retry=retry_if_exception(is_retryable_groq_error),
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(min=1.0, max=10.0),
        before_sleep=_log_retry_failure,
        reraise=True,
    )
    async def _wrapped_async():
        return await func(*args, **kwargs)

    return await _wrapped_async()
