"""
app/main.py

FastAPI application entry point.
Registers all routers and sets up CORS, lifespan events, and health check.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import upload, status, results, agent, auth, public, admin, superadmin
from app.api.routes.agent import resolve_model
from app.core.config import settings
from app.services import anomaly_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Discover the best available Gemini model once at boot.
    # All subsequent requests use the cached result with zero overhead.
    await resolve_model()

    # Pre-load IsolationForest models into memory once at startup.
    try:
        anomaly_service.load_models()
        logger.info("ML anomaly models loaded at startup.")
    except Exception as exc:
        logger.warning("Could not load ML models at boot: %s", exc)

    # Ensure new tables (organizations, users) exist in the database.
    from app.db.session import engine, SessionLocal
    from app.db.base import Base  # noqa: F401 -- triggers all model imports
    Base.metadata.create_all(bind=engine)

    # Automatically ensure demo users exist in development
    try:
        from app.api.routes.auth import seed_demo_users
        with SessionLocal() as db:
            seed_demo_users(db)
            logger.info("Demo accounts verified.")
    except Exception as exc:
        logger.warning("Could not verify demo users at startup: %s", exc)

    yield


app = FastAPI(
    title="Recalce",
    description="Automated bank reconciliation engine",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: Allow all local development origins (5173, 5174, 5175, etc.) and configured origins
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router,    prefix="/api/v1")
app.include_router(admin.router,   prefix="/api/v1")
app.include_router(superadmin.router, prefix="/api/v1")
app.include_router(upload.router,  prefix="/api/v1")
app.include_router(status.router,  prefix="/api/v1")
app.include_router(results.router, prefix="/api/v1")
app.include_router(public.router,  prefix="/api/v1")
app.include_router(agent.router,   prefix="/api/v1/agent")

# Static sample datasets
_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# Health
@app.get("/api/v1/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
