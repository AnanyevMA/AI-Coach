import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ai_sport_backend")

# Initialize Sentry SDK if DSN is configured
sentry_dsn = getattr(settings, "SENTRY_DSN", None) or os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=getattr(settings, "ENVIRONMENT", "production"),
        traces_sample_rate=getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 1.0),
        profiles_sample_rate=getattr(settings, "SENTRY_PROFILES_SAMPLE_RATE", 1.0),
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        send_default_pii=False,  # 152-FZ compliance: protect personal identity
    )
    logger.info("Sentry DSN integration initialized successfully.")

# Safe Prometheus Metrics Collector Registration (prevents duplicates during reload/test runs)
def _get_or_create_counter(name: str, documentation: str, labelnames=()):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return Counter(name, documentation, labelnames)


def _get_or_create_histogram(name: str, documentation: str, labelnames=(), buckets=Histogram.DEFAULT_BUCKETS):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return Histogram(name, documentation, labelnames, buckets=buckets)


def _get_or_create_gauge(name: str, documentation: str, labelnames=()):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return Gauge(name, documentation, labelnames)


START_TIME = time.time()

HTTP_REQUESTS_TOTAL = _get_or_create_counter(
    "http_requests_total",
    "Total number of HTTP requests processed",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = _get_or_create_histogram(
    "http_request_duration_seconds",
    "HTTP request duration / latency in seconds",
    ["method", "endpoint", "status_code"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

ACTIVE_SESSIONS_TOTAL = _get_or_create_gauge(
    "active_sessions_total",
    "Current count of active HTTP sessions / concurrent requests",
)

ACTIVE_SESSIONS = _get_or_create_gauge(
    "active_sessions",
    "Current count of active sessions",
)

PROCESS_UPTIME_SECONDS = _get_or_create_gauge(
    "process_uptime_seconds",
    "Application uptime in seconds",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application Lifespan Context Manager.
    Initializes database tables and resources on startup.
    """
    logger.info("Initializing AI Adaptive Coach v7.0 Async Backend...")
    async with engine.begin() as conn:
        # Create tables automatically for dev/sqlite environments if missing
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema initialized successfully.")
    
    yield
    
    logger.info("Shutting down AI Adaptive Coach v7.0 Backend...")
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_and_security_middleware(request: Request, call_next):
    """
    Middleware for Prometheus metrics collection, Sentry exception handling,
    active session tracking, and OWASP HTTP security headers injection.
    """
    ACTIVE_SESSIONS_TOTAL.inc()
    ACTIVE_SESSIONS.inc()
    start_time = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as exc:
        status_code = 500
        logger.error(f"Unhandled Exception intercepted: {exc}", exc_info=exc)
        if sentry_dsn:
            sentry_sdk.capture_exception(exc)
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "152_fz_privacy_protected": True},
        )
    finally:
        duration = time.perf_counter() - start_time
        ACTIVE_SESSIONS_TOTAL.dec()
        ACTIVE_SESSIONS.dec()

        endpoint = request.url.path
        method = request.method
        status_str = str(status_code)

        HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code=status_str).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint, status_code=status_str).observe(duration)

    # Security Headers Injection (OWASP Security Standard)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    return response


@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception):
    """Global exception handler for any uncaught exceptions to ensure Sentry capture and 500 JSON response."""
    logger.error(f"Global Exception Handler: {exc}", exc_info=exc)
    if sentry_dsn:
        sentry_sdk.capture_exception(exc)
    
    response = JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred."},
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Mount API V1 Router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount Static Files for PWA Athlete & B2B Coach Dashboard
PWA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "pwa_athlete"))
COACH_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "coach"))
if not os.path.exists(COACH_DIR):
    COACH_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "b2b_coach"))

if os.path.exists(PWA_DIR):
    app.mount("/pwa_static", StaticFiles(directory=PWA_DIR), name="pwa_static")
    
    @app.get("/pwa", response_class=FileResponse)
    @app.get("/pwa/", response_class=FileResponse)
    @app.get("/pwa/index.html", response_class=FileResponse)
    async def serve_pwa():
        return FileResponse(os.path.join(PWA_DIR, "index.html"), media_type="text/html")

if os.path.exists(COACH_DIR):
    app.mount("/coach_static", StaticFiles(directory=COACH_DIR), name="coach_static")
    
    @app.get("/coach", response_class=FileResponse)
    @app.get("/coach/", response_class=FileResponse)
    @app.get("/coach/index.html", response_class=FileResponse)
    async def serve_coach():
        return FileResponse(os.path.join(COACH_DIR, "index.html"), media_type="text/html")


@app.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus metrics scraping endpoint.
    Exposes request latency, HTTP status codes, total request count, active sessions, and uptime.
    """
    PROCESS_UPTIME_SECONDS.set(time.time() - START_TIME)
    metrics_data = generate_latest()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def root_health():
    """Root health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": "7.0.0",
        "prometheus_metrics": "/metrics",
    }


@app.get("/")
async def root_redirect():
    """Root redirect endpoint providing API metadata."""
    return {
        "project": settings.PROJECT_NAME,
        "version": "7.0.0",
        "docs": f"{settings.API_V1_STR}/docs",
        "pwa_athlete": "/pwa",
        "b2b_coach": "/coach",
        "metrics": "/metrics",
        "health": f"{settings.API_V1_STR}/health",
        "152_fz_compliant": True,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
