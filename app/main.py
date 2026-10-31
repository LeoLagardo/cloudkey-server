import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import engine, Base
from app.middleware.tenant_middleware import TenantMiddleware
from app.routes import api_router
from app.utils.exceptions import PMSException
from sqlalchemy.exc import IntegrityError

from app.scheduler import start_scheduler, stop_scheduler
from sqlalchemy import text


def _run_sqlite_migrations(connection):
    """Ensure newly introduced columns exist in existing SQLite database files."""
    if connection.dialect.name == "sqlite":
        def add_col(table: str, col: str, col_def: str):
            res = connection.execute(text(f"PRAGMA table_info({table})"))
            cols = [r[1] for r in res.fetchall()]
            if col not in cols:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))

        add_col("rate_plans", "meal_plan", "TEXT NOT NULL DEFAULT 'EP'")
        add_col("rate_plans", "no_of_meals", "INTEGER NOT NULL DEFAULT 0")
        add_col("rate_plans", "color_code", "VARCHAR(7) NOT NULL DEFAULT '#4F46E5'")
        add_col("rate_plans", "extra_adult_rate", "NUMERIC(12, 2) NOT NULL DEFAULT 0.00")
        add_col("rate_plans", "extra_child_rate", "NUMERIC(12, 2) NOT NULL DEFAULT 0.00")
        add_col("rate_plan_rates", "occupancy", "INTEGER")
        add_col("rate_plan_rates", "extra_adult_price", "NUMERIC(12, 2)")
        add_col("rate_plan_rates", "extra_child_price", "NUMERIC(12, 2)")
        add_col("reservation_room_rates", "occupancy", "INTEGER NOT NULL DEFAULT 1")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup (especially convenient for development/SQLite)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_sqlite_migrations)
    # Start APScheduler 1-minute poller for automated night audits
    start_scheduler()
    yield
    # Stop scheduler and cleanup database engine on shutdown
    stop_scheduler()
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Multi-tenant Property Management System (PMS) backend powered by FastAPI & Supabase.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware configuration
# NOTE: add_middleware is processed in reverse order (last added = outermost).
# CORSMiddleware must be outermost so it handles OPTIONS preflights before
# TenantMiddleware (a BaseHTTPMiddleware) can interfere.

# 1. CORS Middleware — added first so it wraps everything (outermost)
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 2. Custom Tenant & Correlation ID Middleware — added second (inner)
app.add_middleware(TenantMiddleware)


# Exception Handlers
@app.exception_handler(PMSException)
async def pms_exception_handler(request: Request, exc: PMSException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "detail": exc.detail,
            "status_code": exc.status_code,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "ConflictError",
            "detail": "A resource with unique properties already exists or violates integrity constraints.",
            "status_code": status.HTTP_409_CONFLICT,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


# Root & Health Check
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "database_connected": bool(settings.DATABASE_URL),
        "supabase_configured": bool(settings.SUPABASE_URL and settings.SUPABASE_KEY),
    }


@app.get("/", tags=["Health"])
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "docs": "/docs",
        "health": "/health",
        "version": "1.0.0",
    }


# Include API v1 routes
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
