"""
Unit Test Suite for Production Tracing (Correlation-ID) & Health Readiness Probes.

Tests:
1. Auto-generation of `X-Correlation-ID` header when missing.
2. Preservation of custom client-provided `X-Correlation-ID`.
3. `/health/ready` readiness checks for Database, Redis, Vector Store, and Groq API.
4. `/health/liveness` probe response.
5. Presence of `X-Correlation-ID` in HTTP response headers.

Usage:
    cd ai-chatbot
    python test_tracing_and_health.py
"""
import os
import sys
import uuid
import unittest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

from app.main import app

client = TestClient(app)

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


def test_correlation_id_auto_generation():
    print("\n── Phase 1: Auto-Generation of X-Correlation-ID ──")
    res = client.get("/health/liveness")
    
    _report("Status code 200 OK", res.status_code == 200)
    
    cid_header = res.headers.get("X-Correlation-ID")
    _report("X-Correlation-ID header present in response", bool(cid_header))
    
    # Validate UUID format
    is_valid_uuid = False
    if cid_header:
        try:
            val = uuid.UUID(cid_header)
            is_valid_uuid = True
        except ValueError:
            is_valid_uuid = False
    _report("X-Correlation-ID is valid UUID4 string", is_valid_uuid, f"Header: {cid_header}")
    
    data = res.json()
    _report("Payload contains correlation_id field matching header", data.get("correlation_id") == cid_header)


def test_correlation_id_preservation():
    print("\n── Phase 2: Preservation of Client-Provided Correlation ID ──")
    custom_cid = "custom-trace-id-9988776655"
    headers = {"X-Correlation-ID": custom_cid}
    
    res = client.get("/health/liveness", headers=headers)
    _report("Status code 200 OK", res.status_code == 200)
    
    res_cid = res.headers.get("X-Correlation-ID")
    _report("Preserved custom X-Correlation-ID in response header", res_cid == custom_cid, f"Got: {res_cid}")
    
    data = res.json()
    _report("Payload correlation_id matches custom ID", data.get("correlation_id") == custom_cid)


def test_readiness_probe():
    print("\n── Phase 3: Readiness Probe (/health/ready) ──")
    res = client.get("/health/ready")
    
    _report("Readiness probe returns valid HTTP status (200 or 503)", res.status_code in (200, 530, 503))
    _report("X-Correlation-ID present in readiness probe response", "X-Correlation-ID" in res.headers)
    
    data = res.json()
    _report("Contains overall status ('ready' or 'unready')", data.get("status") in ("ready", "unready"))
    _report("Contains checks dict", "checks" in data)
    
    checks = data.get("checks", {})
    _report("Contains database check", "database" in checks)
    _report("Contains redis check", "redis" in checks)
    _report("Contains vector_store check", "vector_store" in checks)
    _report("Contains groq_api check", "groq_api" in checks)


def test_legacy_health_and_api_routes():
    print("\n── Phase 4: API Routes Tracing Integration ──")
    res = client.get("/health")
    _report("Legacy /health probe returns 200 OK", res.status_code == 200)
    _report("Legacy /health probe contains X-Correlation-ID header", "X-Correlation-ID" in res.headers)

    res_v1 = client.get("/api/v1/health/ready")
    _report("Versioned /api/v1/health/ready probe functional", res_v1.status_code in (200, 530, 503))
    _report("Versioned probe contains X-Correlation-ID header", "X-Correlation-ID" in res_v1.headers)


def main():
    print("=" * 65)
    print("  KHANX Production Request Tracing & Health Probe Test Suite")
    print("=" * 65)
    
    test_correlation_id_auto_generation()
    test_correlation_id_preservation()
    test_readiness_probe()
    test_legacy_health_and_api_routes()
    
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
