"""
Comprehensive Unit Test Suite for Groq API Tenacity Retry System.

Tests:
1. Classification of temporary vs permanent Groq errors in `is_retryable_groq_error`.
2. Automatic retry with exponential backoff on temporary failures (RateLimit, Timeout, Connection, 503 ServerError).
3. Immediate non-retrying fail-fast on permanent client errors (400 BadRequest, 401 AuthError, 403 Forbidden).
4. Successful response delivery on recovered retry attempt.

Usage:
    cd ai-chatbot
    python test_groq_retry.py
"""
import os
import sys
import unittest
from unittest.mock import MagicMock
import httpx
import groq

sys.path.insert(0, os.path.dirname(__file__))

from app.services.groq_retry import is_retryable_groq_error, call_groq_with_retry

passed = 0
failed = 0
errors = []

def _report(name: str, success: bool, detail: str = ""):
    global passed, failed
    if success:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        errors.append((name, detail))
        print(f"  ❌ {name}: {detail}")

def test_exception_classification():
    print("\n── Phase 1: Temporary vs Permanent Exception Classification ──")
    
    mock_request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
    
    # 1. Temporary retryable errors
    rate_limit_err = groq.RateLimitError(
        message="Rate limit exceeded",
        response=httpx.Response(429, request=mock_request),
        body={}
    )
    _report("RateLimitError (429) identified as retryable", is_retryable_groq_error(rate_limit_err) is True)

    timeout_err = groq.APITimeoutError(request=mock_request)
    _report("APITimeoutError identified as retryable", is_retryable_groq_error(timeout_err) is True)

    conn_err = groq.APIConnectionError(request=mock_request)
    _report("APIConnectionError identified as retryable", is_retryable_groq_error(conn_err) is True)

    server_err = groq.InternalServerError(
        message="Internal server error",
        response=httpx.Response(503, request=mock_request),
        body={}
    )
    _report("InternalServerError (503) identified as retryable", is_retryable_groq_error(server_err) is True)

    # 2. Permanent non-retryable errors
    bad_req_err = groq.BadRequestError(
        message="Invalid parameters",
        response=httpx.Response(400, request=mock_request),
        body={}
    )
    _report("BadRequestError (400) identified as permanent (non-retryable)", is_retryable_groq_error(bad_req_err) is False)

    auth_err = groq.AuthenticationError(
        message="Invalid API Key",
        response=httpx.Response(401, request=mock_request),
        body={}
    )
    _report("AuthenticationError (401) identified as permanent (non-retryable)", is_retryable_groq_error(auth_err) is False)

    forbidden_err = groq.PermissionDeniedError(
        message="Permission denied",
        response=httpx.Response(403, request=mock_request),
        body={}
    )
    _report("PermissionDeniedError (403) identified as permanent (non-retryable)", is_retryable_groq_error(forbidden_err) is False)


def test_retry_on_temporary_failure_and_recovery():
    print("\n── Phase 2: Retry on Temporary Failure & Recovery ──")
    mock_request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
    
    attempts = 0
    def transient_failure_func():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise groq.RateLimitError(
                message="Rate limit exceeded",
                response=httpx.Response(429, request=mock_request),
                body={}
            )
        return "Success Output"

    res = call_groq_with_retry(transient_failure_func)
    _report("Retries on transient 429 and succeeds on 3rd attempt", res == "Success Output" and attempts == 3, f"Attempts: {attempts}")


def test_immediate_fail_on_permanent_error():
    print("\n── Phase 3: Immediate Fail-Fast on Permanent 4xx Error ──")
    mock_request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
    
    attempts = 0
    def bad_request_func():
        nonlocal attempts
        attempts += 1
        raise groq.BadRequestError(
            message="Invalid parameters in payload",
            response=httpx.Response(400, request=mock_request),
            body={}
        )

    raised_correct = False
    try:
        call_groq_with_retry(bad_request_func)
    except groq.BadRequestError:
        raised_correct = True
    except Exception as e:
        print("Wrong exception:", type(e))

    _report("Fails fast on BadRequestError (400) without retrying (only 1 attempt made)", raised_correct and attempts == 1, f"Attempts: {attempts}")


def main():
    print("=" * 65)
    print("  KHANX Groq API Tenacity Retry System — Test Suite")
    print("=" * 65)
    
    test_exception_classification()
    test_retry_on_temporary_failure_and_recovery()
    test_immediate_fail_on_permanent_error()
    
    print("\n" + "=" * 65)
    print(f"  Results: {passed}/{passed + failed} passed, {failed} failed")
    if errors:
        for name, detail in errors:
            print(f"    ❌ {name}: {detail}")
    print("=" * 65)
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
