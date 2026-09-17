from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.requests import Request
from app.api.routes import auth, chat, documents, memory, approval, tasks, calendar, email, health
from app.core.config import settings
from app.core.limiter import limiter, custom_rate_limit_handler
from app.core.tracing_middleware import CorrelationIDMiddleware, CorrelationIDLogFilter, get_correlation_id
from slowapi.errors import RateLimitExceeded
from datetime import datetime, timezone
from functools import lru_cache
import os
import logging

# Configure logger tracing format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [cid:%(correlation_id)s] %(name)s: %(message)s"
)
for _h in logging.root.handlers:
    _h.addFilter(CorrelationIDLogFilter())

# ── Sentry Integration ────────────────────────────────────────────────────────
if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=1.0,
    )
    logging.getLogger("khanx.api").info("Sentry error monitoring initialized.")

app = FastAPI(
    title="KHANNAX API",
    description="Backend for KHANNAX — AI Chatbot powered by Groq + Supabase",
    version="1.0.0"
)

# ── Tracing Middleware ────────────────────────────────────────────────────────
app.add_middleware(CorrelationIDMiddleware)

# ── Rate Limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)

# ── Global 500 Exception Handler ──────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled 500 errors."""
    logger = logging.getLogger("khanx.api")
    cid = getattr(request.state, "correlation_id", get_correlation_id())
    logger.error(f"Unhandled 500 error on {request.method} {request.url} [cid:{cid}]: {exc}", exc_info=True)
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except Exception:
            pass
    res = JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "An internal error occurred. Please try again later.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": cid
        }
    )
    res.headers["X-Correlation-ID"] = cid
    return res

# ── HTTPS Redirect Middleware ──────────────────────────────────────────────────
if settings.FORCE_HTTPS:
    from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
    app.add_middleware(HTTPSRedirectMiddleware)

# ── Security Headers Middleware ───────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.FORCE_HTTPS:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response

# ── CORS Hardening ────────────────────────────────────────────────────────────
_origins_env = settings.ALLOWED_ORIGINS.strip()
if _origins_env:
    origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
else:
    origins = [
        "http://localhost",
        "http://localhost:8000",
        "http://localhost:5500",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "null",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With", "X-Correlation-ID", "x-correlation-id"],
    expose_headers=["X-Correlation-ID", "x-correlation-id"],
)

# ── Health Check Routers ──────────────────────────────────────────────────────
app.include_router(health.router,    prefix="/health",           tags=["Health"])
app.include_router(health.router,    prefix="/api/v1/health",    tags=["Health (v1)"])

# ── Versioned API Routers (/api/v1/) ──────────────────────────────────────────

app.include_router(auth.router,      prefix="/api/v1/auth",      tags=["Authentication (v1)"])
app.include_router(chat.router,      prefix="/api/v1/chat",      tags=["Chat (v1)"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents (v1)"])
app.include_router(memory.router,    prefix="/api/v1/memory",    tags=["Memory (v1)"])
app.include_router(approval.router,  prefix="/api/v1/approval",  tags=["Approval (v1)"])
app.include_router(tasks.router,     prefix="/api/v1/tasks",     tags=["Tasks (v1)"])
app.include_router(calendar.router,  prefix="/api/v1/calendar",  tags=["Calendar (v1)"])
app.include_router(email.router,     prefix="/api/v1/email",     tags=["Email (v1)"])

# Backwards compatibility legacy routes (/api/...)
app.include_router(auth.router,      prefix="/api/auth",      tags=["Authentication (legacy)"])
app.include_router(chat.router,      prefix="/api/chat",      tags=["Chat (legacy)"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents (legacy)"])
app.include_router(memory.router,    prefix="/api/memory",    tags=["Memory (legacy)"])
app.include_router(approval.router,  prefix="/api/approval",  tags=["Approval (legacy)"])
app.include_router(tasks.router,     prefix="/api/tasks",     tags=["Tasks (legacy)"])
app.include_router(calendar.router,  prefix="/api/calendar",  tags=["Calendar (legacy)"])
app.include_router(email.router,     prefix="/api/email",     tags=["Email (legacy)"])

# ── Health Check Endpoint ─────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health_check():
    """
    Comprehensive liveness health probe for container orchestration.
    Used by Kubernetes, Docker, Heroku, Render, AWS ECS.
    """
    return {
        "status": "ok",
        "service": "KHANNAX API",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "groq_configured": bool(settings.GROQ_API_KEY),
        "supabase_configured": bool(settings.SUPABASE_URL and settings.SUPABASE_KEY),
        "sentry_enabled": bool(settings.SENTRY_DSN),
        "environment": "production" if settings.FORCE_HTTPS else "development"
    }

@app.get("/health/readiness", tags=["Health"])
def readiness_check():
    """
    Active readiness probe verifying database connectivity and API key readiness.
    """
    from app.services.supabase_client import supabase
    db_ok = False
    try:
        res = supabase.table("profiles").select("id").limit(1).execute()
        db_ok = True
    except Exception as e:
        logging.getLogger("khanx.api").error(f"Readiness probe DB failure: {e}")

    if not db_ok:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "reason": "Database connection test failed",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )

    return {
        "status": "ready",
        "database": "connected",
        "groq_configured": bool(settings.GROQ_API_KEY),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ── Cached Config Endpoints (/api/v1/config & /api/config) ───────────────────
@lru_cache(maxsize=1)
def _get_cached_config_data():
    return {
        "supabase_url": settings.SUPABASE_URL,
        "supabase_anon_key": settings.SUPABASE_KEY
    }

@app.get("/api/v1/config", tags=["Config (v1)"])
@app.get("/api/config", tags=["Config (legacy)"])
def get_config():
    """Returns cached public Supabase configuration for frontend client initialization."""
    return _get_cached_config_data()

# ── Serve Frontend Static Files ───────────────────────────────────────────────
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/", response_class=FileResponse)
    def serve_index():
        return os.path.join(frontend_dir, "index.html")

    @app.get("/login", response_class=FileResponse)
    @app.get("/login.html", response_class=FileResponse)
    def serve_login():
        return os.path.join(frontend_dir, "login.html")

    @app.get("/index.html", response_class=FileResponse)
    def serve_index_html():
        return os.path.join(frontend_dir, "index.html")

    @app.get("/supabase.js", response_class=FileResponse)
    def serve_supabasejs():
        return os.path.join(frontend_dir, "supabase.js")

    @app.get("/logo.png", response_class=FileResponse)
    def serve_logo():
        return os.path.join(frontend_dir, "logo.png")
else:
    @app.get("/")
    def read_root():
        return {"message": "Welcome to KHANNAX API", "docs": "/docs"}
