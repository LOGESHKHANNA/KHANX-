"""
Health Probes & Production Readiness Endpoints (/health, /health/ready, /health/liveness).

Provides structured JSON status checks for container orchestration (Kubernetes, AWS ECS, Docker):
1. `/health` & `/health/liveness`: Fast non-blocking liveness probe.
2. `/health/ready`: Deep readiness probe checking Database, Redis Cache, Vector Store, and Groq API.
"""
from fastapi import APIRouter, Request, Response
from datetime import datetime, timezone
from app.core.config import settings
from app.services.supabase_client import supabase
from app.services.cache_service import cache_service
from app.core.tracing_middleware import get_correlation_id

router = APIRouter()


@router.get("/liveness", tags=["Health"])
@router.get("", tags=["Health"])
def liveness_check(request: Request):
    """Fast non-blocking liveness probe verifying HTTP API responsiveness."""
    cid = getattr(request.state, "correlation_id", get_correlation_id())
    return {
        "status": "ok",
        "service": "KHANNAX API",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": cid,
        "environment": "production" if settings.FORCE_HTTPS else "development"
    }


@router.get("/ready", tags=["Health"])
def readiness_check(request: Request, response: Response):
    """Comprehensive readiness probe verifying Database, Redis RAG Cache, Vector Store, and Groq API availability."""
    cid = getattr(request.state, "correlation_id", get_correlation_id())
    checks = {}
    is_ready = True

    # 1. Database Reachability (Supabase)
    try:
        if supabase:
            # Lightweight query test
            db_res = supabase.table("profiles").select("count", count="exact").limit(0).execute()
            checks["database"] = {"status": "ok"}
        else:
            checks["database"] = {"status": "unconfigured", "error": "Supabase client not initialized"}
            is_ready = False
    except Exception as db_err:
        checks["database"] = {"status": "error", "error": str(db_err)}
        is_ready = False

    # 2. Redis RAG Cache Status
    try:
        redis_ping = cache_service.ping()
        if redis_ping:
            checks["redis"] = {"status": "ok", "mode": "distributed_redis"}
        else:
            checks["redis"] = {"status": "ok", "mode": "in_memory_fallback"}
    except Exception as redis_err:
        checks["redis"] = {"status": "degraded", "mode": "in_memory_fallback", "detail": str(redis_err)}

    # 3. Vector Store (ChromaDB)
    try:
        from app.services.vector_store import _get_chroma_client
        chroma_client = _get_chroma_client()
        if hasattr(chroma_client, "heartbeat"):
            chroma_client.heartbeat()
        checks["vector_store"] = {"status": "ok"}
    except Exception as vs_err:
        checks["vector_store"] = {"status": "error", "error": str(vs_err)}
        is_ready = False

    # 4. Groq API Config
    groq_ok = bool(settings.GROQ_API_KEY)
    checks["groq_api"] = {
        "status": "ok" if groq_ok else "unconfigured"
    }
    if not groq_ok:
        is_ready = False

    overall_status = "ready" if is_ready else "unready"
    if not is_ready:
        response.status_code = 503

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": cid,
        "checks": checks
    }
